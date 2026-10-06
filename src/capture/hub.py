"""App-side capture hub: host<->app IPC, verification, storage, engine wiring.

IPC: ``multiprocessing.connection`` over AF_UNIX (mac/Linux) or AF_PIPE
(Windows) under ``~/.playlist_migrator/run/``. A per-launch random authkey is
written 0600 to ``capture.key``; the Listener's built-in HMAC challenge gates
every connection. JSON via send_bytes/recv_bytes only (never pickle).
"""

import hashlib
import json
import logging
import os
import secrets
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from multiprocessing.connection import Listener
from typing import Any, Callable, Dict, List, Optional

from . import paths, protocol
from .constants import (INFO_FILE_NAME, KEY_FILE_NAME, MAX_MESSAGE_BYTES,
                        SOCKET_NAME)
from .session import MissingSapisidError, build_headers, cookie_set_hash
from .session_store import SessionStore
from .verify import default_client_factory, verify_identity

logger = logging.getLogger(__name__)

IS_WINDOWS = sys.platform.startswith("win")


def pipe_address(username: Optional[str] = None) -> str:
    """Per-user named pipe address (Windows)."""
    who = username or os.environ.get("USERNAME") or os.environ.get("USER") or "user"
    return r"\\.\pipe\playlist_migrator-capture-" + hashlib.sha256(who.encode()).hexdigest()[:16]


@dataclass
class CaptureResult:
    ok: bool
    account_name: str = ""
    client: Any = None
    code: Optional[str] = None  # no_extension|signed_out|rejected|network|rate_limited|timeout
    browser: Optional[str] = None
    retry_after_s: Optional[int] = None


class Port:
    """One live host connection."""

    def __init__(self, conn, argv):
        self.id = str(uuid.uuid4())
        self.conn = conn
        self.argv = list(argv or [])
        self.browser = "unknown"
        self.extension_id = ""
        self.user_agent: Optional[str] = None
        self.since = time.time()
        self.last_seen = self.since
        self._lock = threading.Lock()

    def send(self, obj: Dict[str, Any]) -> None:
        with self._lock:
            self.conn.send_bytes(protocol.dumps(obj))

    def to_extension(self, payload: Dict[str, Any]) -> None:
        self.send(protocol.to_extension(payload))

    def info(self) -> Dict[str, Any]:
        return {"port_id": self.id, "browser": self.browser,
                "extension_id": self.extension_id, "since": self.since,
                "last_seen": self.last_seen}


class CaptureHub:
    RECAPTURE_TIMEOUT_S = 10

    def __init__(self, run_dir: Optional[str] = None, store: Optional[SessionStore] = None,
                 rate_limiter=None, client_factory: Callable = default_client_factory,
                 app_version: str = "dev", address: Optional[str] = None):
        self.run_dir = run_dir or paths.run_dir()
        self.store = store or SessionStore()
        self._rate_limiter = rate_limiter
        self.client_factory = client_factory
        self.app_version = app_version
        self._address_override = address

        self._listener: Optional[Listener] = None
        self._accept_thread: Optional[threading.Thread] = None
        self._ports: Dict[str, Port] = {}
        self._pending: Dict[str, dict] = {}
        self._lock = threading.RLock()
        self._subscribers: List[Callable] = []
        self._manager = None
        self._outage_ts: Optional[float] = None
        self.last_good_browser: Optional[str] = None
        self.last_good_hash: Optional[str] = None
        self.client = None
        self.account_name = ""
        self.address: Optional[str] = None
        self._stopping = False

    # ---- lifecycle --------------------------------------------------------

    def start(self) -> None:
        paths.private_dir(self.run_dir)
        key = secrets.token_bytes(32)
        paths.write_private(os.path.join(self.run_dir, KEY_FILE_NAME), key)
        if self._address_override:
            self.address, family = self._address_override, ("AF_PIPE" if IS_WINDOWS else "AF_UNIX")
        elif IS_WINDOWS:
            self.address, family = pipe_address(), "AF_PIPE"
        else:
            self.address, family = os.path.join(self.run_dir, SOCKET_NAME), "AF_UNIX"
        if family == "AF_UNIX":
            try:  # stale socket from a crashed run (takeover: newest app wins)
                os.unlink(self.address)
            except FileNotFoundError:
                pass
            old = os.umask(0o177)  # socket created 0600
            try:
                self._listener = Listener(self.address, family, authkey=key)
            finally:
                os.umask(old)
            try:
                os.chmod(self.address, 0o600)
            except OSError:
                pass
        else:
            self._listener = Listener(self.address, family, authkey=key)
        info = {"v": 1, "address": self.address, "pid": os.getpid(), "app_version": self.app_version}
        paths.write_private(os.path.join(self.run_dir, INFO_FILE_NAME), json.dumps(info).encode())
        self._stopping = False
        self._accept_thread = threading.Thread(target=self._accept_loop, name="capture-accept", daemon=True)
        self._accept_thread.start()
        logger.info("CaptureHub listening")

    def stop(self) -> None:
        self._stopping = True
        with self._lock:
            ports = list(self._ports.values())
        for p in ports:
            try:
                p.send({"v": 1, "type": "close", "reason": "app_quit"})
            except Exception:
                pass
            try:
                p.conn.close()
            except Exception:
                pass
        if self._listener is not None:
            try:
                self._listener.close()
            except Exception:
                pass
            self._listener = None
        for name in (KEY_FILE_NAME, INFO_FILE_NAME, SOCKET_NAME):
            try:
                os.unlink(os.path.join(self.run_dir, name))
            except OSError:
                pass

    # ---- accept / read loops ---------------------------------------------

    def _accept_loop(self) -> None:
        while not self._stopping and self._listener is not None:
            try:
                conn = self._listener.accept()  # HMAC challenge happens here
            except Exception as exc:
                if self._stopping or self._listener is None:
                    return
                logger.warning("IPC accept/handshake failed: %s", type(exc).__name__)
                continue
            threading.Thread(target=self._serve, args=(conn,), name="capture-port", daemon=True).start()

    def _serve(self, conn) -> None:
        port = None
        reason = "eof"
        try:
            first = protocol.loads(conn.recv_bytes(MAX_MESSAGE_BYTES))
            if first.get("type") != "port_opened":
                raise protocol.ProtocolError("bad_frame", "expected port_opened")
            port = Port(conn, first.get("argv"))
            with self._lock:
                self._ports[port.id] = port
            port.send(protocol.port_ack(port.id, self.app_version))
            self._emit("port_opened", **port.info())
            while True:
                msg = protocol.loads(conn.recv_bytes(MAX_MESSAGE_BYTES))
                port.last_seen = time.time()
                t = msg.get("type")
                if t == "from_extension":
                    self._on_extension_message(port, msg.get("payload") or {})
                elif t == "port_closed":
                    reason = msg.get("reason", "eof")
                    break
        except (EOFError, OSError):
            reason = "eof"
        except protocol.ProtocolError as exc:
            reason = exc.code
        except Exception:
            logger.exception("capture port crashed")
            reason = "internal"
        finally:
            if port is not None:
                with self._lock:
                    self._ports.pop(port.id, None)
                self._emit("port_closed", port_id=port.id, reason=reason, browser=port.browser)
            try:
                conn.close()
            except Exception:
                pass

    # ---- extension messages ----------------------------------------------

    def _on_extension_message(self, port: Port, msg: Dict[str, Any]) -> None:
        logger.debug("from extension: %s", protocol.redact(msg))
        try:
            t = protocol.message_type(msg, protocol.EXTENSION_TYPES)
        except protocol.ProtocolError as exc:
            port.to_extension(protocol.error(exc.code, "unknown message type"))
            return
        if t == "hello":
            port.browser = str(msg.get("browser") or "unknown")
            port.extension_id = str(msg.get("extension_id") or "")
            ua = msg.get("user_agent")
            port.user_agent = ua if isinstance(ua, str) and ua else None
            port.to_extension(protocol.hello_ack(self.app_version, True, port.id))
            self._emit("hello", **port.info())
        elif t == "cookies":
            self._on_cookies(port, msg)
        elif t == "signed_out":
            self._resolve(msg.get("request_id"),
                          CaptureResult(False, code="signed_out", browser=port.browser))
            port.to_extension(protocol.identity_failed(msg.get("request_id"), "signed_out"))
            self._emit("identity_failed", code="signed_out", browser=port.browser)
        elif t == "error":
            self._resolve(msg.get("request_id"),
                          CaptureResult(False, code="rejected", browser=port.browser))
        # ping is answered by the host; nothing to do here.

    def _on_cookies(self, port: Port, msg: Dict[str, Any]) -> None:
        rid = msg.get("request_id")
        cookies = msg.get("cookies")
        if msg.get("reason") == "changed" and rid is None:
            self._handle_push(port, msg)  # DEFERRED seam
            return
        if not isinstance(cookies, list):
            res = CaptureResult(False, code="rejected", browser=port.browser)
        else:
            res = self.process_cookies(cookies, browser=port.browser, user_agent=port.user_agent)
        self._resolve(rid, res)
        if res.ok:
            port.to_extension(protocol.identity_confirmed(rid, res.account_name))
        else:
            port.to_extension(protocol.identity_failed(rid, res.code or "rejected", res.retry_after_s))

    def _handle_push(self, port: Port, msg: Dict[str, Any]) -> None:
        # TODO(deferred): silent cookies.onChanged push (spec section 4.1/4.2):
        # hash-dedupe via cookie_set_hash, <=1 identity check/60 s and only while
        # auth_required, otherwise save unverified + pending_client. Not built in
        # the thin slice; pushes are ignored.
        logger.debug("ignoring cookies push (deferred)")

    # ---- verification pipeline -------------------------------------------

    def _limiter(self):
        return self._rate_limiter

    def process_cookies(self, cookies: List[dict], browser: Optional[str] = None,
                        user_agent: Optional[str] = None) -> CaptureResult:
        """cookies -> headers -> client -> get_account_info (RateLimiter) -> store -> engine."""
        try:
            headers = build_headers(cookies, user_agent=user_agent)
        except MissingSapisidError:
            self._emit("identity_failed", code="signed_out", browser=browser)
            return CaptureResult(False, code="signed_out", browser=browser)
        return self.verify_headers(headers, browser=browser, cookie_hash=cookie_set_hash(cookies))

    def verify_headers(self, headers: Dict[str, str], browser: Optional[str] = None,
                       cookie_hash: Optional[str] = None) -> CaptureResult:
        try:
            client = self.client_factory(headers)
        except Exception:
            return CaptureResult(False, code="rejected", browser=browser)
        v = verify_identity(client, self._limiter())
        if not v.ok:
            self._emit("identity_failed", code=v.code, browser=browser)
            return CaptureResult(False, code=v.code, browser=browser, retry_after_s=v.retry_after_s)
        self.store.save(headers, v.account_name)
        self.client, self.account_name = client, v.account_name
        self.last_good_browser = browser or self.last_good_browser
        self.last_good_hash = cookie_hash
        if self._manager is not None:
            try:
                self._manager.accept_captured_client(client)
            except Exception:
                logger.exception("engine rejected captured client")
        self._emit("identity_confirmed", account_name=v.account_name, browser=browser)
        return CaptureResult(True, v.account_name, client, browser=browser)

    # ---- ports / requests -------------------------------------------------

    def ports(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [p.info() for p in self._ports.values()]

    def has_live_port(self) -> bool:
        with self._lock:
            return bool(self._ports)

    def _pick_port(self) -> Optional[Port]:
        with self._lock:
            ports = list(self._ports.values())
        if not ports:
            return None
        preferred = [p for p in ports if p.browser == self.last_good_browser]
        return max(preferred or ports, key=lambda p: p.last_seen)

    def _resolve(self, rid: Optional[str], result: CaptureResult) -> None:
        with self._lock:
            slot = self._pending.get(rid) if rid else None
        if slot is not None:
            slot["result"] = result
            slot["event"].set()

    def request_capture(self, purpose: str = "connect", timeout_s: Optional[float] = None) -> CaptureResult:
        """App -> host -> extension: ask for a fresh read and wait for the verified result."""
        port = self._pick_port()
        if port is None:
            return CaptureResult(False, code="no_extension")
        rid = str(uuid.uuid4())
        slot = {"event": threading.Event(), "result": None}
        with self._lock:
            self._pending[rid] = slot
        try:
            port.to_extension(protocol.capture_request(rid, purpose))
            # verification itself may wait on the RateLimiter; allow for it
            if not slot["event"].wait(timeout_s or self.RECAPTURE_TIMEOUT_S):
                return CaptureResult(False, code="timeout", browser=port.browser)
            return slot["result"]
        except OSError:
            return CaptureResult(False, code="no_extension")
        finally:
            with self._lock:
                self._pending.pop(rid, None)

    def connect_youtube(self, on_done: Optional[Callable[[CaptureResult], None]] = None):
        """Manual one-click connect/re-capture; async when ``on_done`` is given."""
        def run():
            res = self.request_capture("connect")
            if on_done:
                on_done(res)
            return res
        if on_done is None:
            return run()
        threading.Thread(target=run, name="capture-connect", daemon=True).start()

    # ---- engine wiring ----------------------------------------------------

    def attach_engine(self, manager) -> None:
        self._manager = manager
        self._rate_limiter = getattr(manager, "rate_limiter", self._rate_limiter)
        manager.set_auth_required_handler(self._on_auth_required)
        if self.client is not None:
            pass  # TODO(later round): lazy pending_client swap

    def _on_auth_required(self, playlist_name: str = "") -> bool:
        """Silent re-capture attempt. True = handled (suppress the OS notification)."""
        self._outage_ts = time.time()
        # 1. cached-first: only a session saved after the failure is worth trying.
        doc = self.store.load_full()
        if doc and doc.get("saved_at", 0) > self._outage_ts:
            if self.verify_headers(doc["headers"]).ok:
                self._emit("reauth_succeeded", via="cache")
                return True
        # 2. ask the live extension.
        res = self.request_capture("reauth")
        if res.ok:
            self._emit("reauth_succeeded", via="extension", browser=res.browser)
            return True
        # 3. prompt path (UI round): caller falls back to notification.
        return False

    # ---- events -----------------------------------------------------------

    def subscribe(self, cb: Callable[[str, Dict[str, Any]], None]) -> Callable[[], None]:
        with self._lock:
            self._subscribers.append(cb)

        def unsubscribe():
            with self._lock:
                if cb in self._subscribers:
                    self._subscribers.remove(cb)
        return unsubscribe

    def _emit(self, event: str, **data) -> None:
        with self._lock:
            subs = list(self._subscribers)
        for cb in subs:
            try:
                cb(event, data)
            except Exception:
                logger.exception("capture subscriber failed")
