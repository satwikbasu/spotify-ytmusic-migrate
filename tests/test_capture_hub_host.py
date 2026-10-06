"""End to end (no browser): extension frames -> host -> hub -> verify -> store,
plus the app-initiated manual re-capture path and IPC security."""

import io
import json
import os
import stat
import struct
import sys
import threading
import time
from multiprocessing.connection import Client
from unittest.mock import MagicMock

import pytest
from cryptography.fernet import Fernet

from src.capture import protocol
from src.capture.host import run_host
from src.capture.hub import CaptureHub
from src.capture.session_store import SessionStore

pytestmark = pytest.mark.skipif(sys.platform.startswith("win"), reason="AF_UNIX test path")

COOKIES = [{"name": "SID", "value": "s"}, {"name": "__Secure-3PAPISID", "value": "abc/DEF"}]


class FakeExtension:
    """Plays the browser: owns the host's stdin/stdout pipes."""

    def __init__(self, run_dir, **host_kw):
        r_in, w_in = os.pipe()
        r_out, w_out = os.pipe()
        self.to_host = os.fdopen(w_in, "wb")
        self.from_host = os.fdopen(r_out, "rb")
        self.exit_codes = []
        self.rc = []
        t = threading.Thread(target=lambda: self.rc.append(run_host(
            os.fdopen(r_in, "rb"), os.fdopen(w_out, "wb", buffering=0), argv=["chrome-extension://x/"],
            run_dir=run_dir, exit_fn=self.exit_codes.append, **host_kw)), daemon=True)
        t.start()
        self.thread = t

    def send(self, msg):
        protocol.write_frame(self.to_host, msg)

    def recv(self, timeout=5):
        box = []
        t = threading.Thread(target=lambda: box.append(protocol.read_frame(self.from_host)), daemon=True)
        t.start()
        t.join(timeout)
        assert box, "timed out waiting for host output"
        return box[0]

    def close(self):
        self.to_host.close()
        self.thread.join(5)
        self.from_host.close()


@pytest.fixture
def env(tmp_path_factory):
    run_dir = str(tmp_path_factory.mktemp("r"))
    store = SessionStore(path=str(tmp_path_factory.mktemp("c") / "youtube_session.enc"), key=Fernet.generate_key())
    limiter = MagicMock()
    client = MagicMock()
    client.get_account_info.return_value = {"accountName": "Ann"}
    factory = MagicMock(return_value=client)
    hub = CaptureHub(run_dir=run_dir, store=store, rate_limiter=limiter, client_factory=factory)
    hub.start()
    yield hub, run_dir, store, limiter, client, factory
    hub.stop()


def _hello(ext):
    ext.send({"v": 1, "type": "hello", "extension_id": "x", "browser": "chrome", "capabilities": ["cookies"]})
    ack = ext.recv()
    assert ack["type"] == "hello_ack" and ack["app_connected"] is True and ack["port_id"]
    return ack


def test_cookie_round_trip_to_identity_confirmed_and_persisted(env):
    hub, run_dir, store, limiter, client, factory = env
    events = []
    hub.subscribe(lambda e, d: events.append(e))
    ext = FakeExtension(run_dir)
    _hello(ext)
    ext.send({"v": 1, "type": "cookies", "request_id": None, "reason": "request",
              "captured_at": 1, "cookies": COOKIES})
    msg = ext.recv()
    assert msg["type"] == "identity_confirmed" and msg["account_name"] == "Ann"
    headers = factory.call_args.args[0]
    assert headers["authorization"].startswith("SAPISIDHASH ") and "SID=s" in headers["cookie"]
    limiter.check_limit.assert_called()           # RateLimiter on the identity call
    limiter.record_request.assert_called()
    assert store.load()[1] == "Ann"               # persisted encrypted
    assert "identity_confirmed" in events
    # ping is answered by the host itself
    ext.send({"v": 1, "type": "ping", "t": 7})
    assert ext.recv() == {"v": 1, "type": "pong", "t": 7}
    ext.close()
    assert ext.rc == [0]


def test_manual_recapture_request_app_to_extension_and_back(env):
    hub, run_dir, store, limiter, client, factory = env
    ext = FakeExtension(run_dir)
    _hello(ext)
    out = []
    threading.Thread(target=lambda: out.append(hub.request_capture("connect", timeout_s=5)), daemon=True).start()
    req = ext.recv()
    assert req["type"] == "capture_request" and req["purpose"] == "connect"
    ext.send({"v": 1, "type": "cookies", "request_id": req["request_id"], "reason": "request",
              "captured_at": 1, "cookies": COOKIES})
    assert ext.recv()["type"] == "identity_confirmed"
    deadline = time.time() + 5
    while not out and time.time() < deadline:
        time.sleep(0.01)
    assert out[0].ok and out[0].account_name == "Ann" and out[0].client is client
    ext.close()


def test_signed_out_paths(env):
    hub, run_dir, *_ = env
    ext = FakeExtension(run_dir)
    _hello(ext)
    ext.send({"v": 1, "type": "cookies", "request_id": "r", "reason": "request", "cookies": [{"name": "SID", "value": "s"}]})
    m = ext.recv()
    assert m["type"] == "identity_failed" and m["code"] == "signed_out"
    ext.close()


def test_signed_out_trap_from_empty_account_info(env):
    hub, run_dir, store, limiter, client, factory = env
    client.get_account_info.return_value = []
    ext = FakeExtension(run_dir)
    _hello(ext)
    ext.send({"v": 1, "type": "cookies", "request_id": "r", "reason": "request", "cookies": COOKIES})
    assert ext.recv()["code"] == "signed_out"
    assert store.load() is None          # nothing stored for an unconfirmed identity
    ext.close()


def test_no_port_and_unknown_type(env):
    hub, run_dir, *_ = env
    assert hub.request_capture().code == "no_extension"
    ext = FakeExtension(run_dir)
    _hello(ext)
    ext.send({"v": 1, "type": "bogus"})
    m = ext.recv()
    assert m["type"] == "error" and m["code"] == "unknown_type"
    ext.close()


def test_app_unavailable_when_hub_not_running(tmp_path_factory):
    ext = FakeExtension(str(tmp_path_factory.mktemp("empty")))
    ext.send({"v": 1, "type": "hello"})
    assert ext.recv()["app_connected"] is False
    assert ext.recv()["type"] == "app_unavailable"
    ext.close()
    assert ext.rc == [0]


def test_oversize_frame_gives_error_and_nonzero_exit(env):
    hub, run_dir, *_ = env
    ext = FakeExtension(run_dir)
    _hello(ext)
    ext.to_host.write(struct.pack("<I", 2 * 1024 * 1024))
    ext.to_host.flush()
    assert ext.recv()["code"] == "too_large"
    ext.thread.join(5)
    assert ext.rc == [1]


def test_hub_quit_sends_bye(env):
    hub, run_dir, *_ = env
    ext = FakeExtension(run_dir)
    _hello(ext)
    hub.stop()
    assert ext.recv()["type"] == "bye"
    deadline = time.time() + 5
    while not ext.exit_codes and time.time() < deadline:
        time.sleep(0.01)
    assert ext.exit_codes == [0]


def test_ipc_files_are_private_and_hmac_gates_connections(env):
    hub, run_dir, *_ = env
    assert stat.S_IMODE(os.stat(run_dir).st_mode) == 0o700
    for name in ("capture.key", "capture.json", "capture.sock"):
        assert stat.S_IMODE(os.stat(os.path.join(run_dir, name)).st_mode) == 0o600, name
    info = json.load(open(os.path.join(run_dir, "capture.json")))
    assert info["address"].startswith(run_dir) and info["pid"] == os.getpid()
    from multiprocessing import AuthenticationError
    with pytest.raises((AuthenticationError, EOFError, OSError)):
        Client(info["address"], authkey=b"wrong-key-wrong-key")
    # a correct key still works afterwards (accept loop survived the bad client)
    key = open(os.path.join(run_dir, "capture.key"), "rb").read()
    c = Client(info["address"], authkey=key)
    c.send_bytes(protocol.dumps(protocol.port_opened([])))
    assert protocol.loads(c.recv_bytes())["type"] == "port_ack"
    c.close()
    hub.stop()
    assert not os.path.exists(os.path.join(run_dir, "capture.key"))


def test_hub_logs_do_not_leak_cookies(env, caplog):
    hub, run_dir, *_ = env
    caplog.set_level("DEBUG")
    ext = FakeExtension(run_dir)
    _hello(ext)
    ext.send({"v": 1, "type": "cookies", "request_id": None, "reason": "request",
              "cookies": [{"name": "__Secure-3PAPISID", "value": "TOPSECRETVALUE"}]})
    ext.recv()
    ext.close()
    assert "TOPSECRETVALUE" not in caplog.text
