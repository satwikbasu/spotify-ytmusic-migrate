"""Native-messaging host: a dumb stdio <-> IPC relay (stdlib only).

Spawned by the browser as ``<app> --native-host``. Writes nothing to stdout
except framed messages; logs go to stderr. Holds no cookies beyond relaying,
never touches the network, never writes files.
"""

import json
import logging
import os
import sys
import threading
from multiprocessing.connection import Client
from typing import Callable, List, Optional

from . import protocol
from .constants import INFO_FILE_NAME, KEY_FILE_NAME, MAX_MESSAGE_BYTES
from .paths import run_dir as default_run_dir

log = logging.getLogger("capture.host")
CONNECT_TIMEOUT_S = 2.0


def _pid_alive(pid: int) -> bool:
    if sys.platform.startswith("win"):
        return True  # no cheap check; the connect attempt is the real test
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def discover(run_dir: str):
    """Return (address, authkey, app_version) or None when the app isn't running."""
    try:
        with open(os.path.join(run_dir, INFO_FILE_NAME), "r", encoding="utf-8") as fh:
            info = json.load(fh)
        with open(os.path.join(run_dir, KEY_FILE_NAME), "rb") as fh:
            key = fh.read()
        if not _pid_alive(int(info["pid"])):
            return None
        return info["address"], key, info.get("app_version", "")
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _connect(run_dir: str, connect: Callable):
    found = discover(run_dir)
    if not found:
        return None
    address, key, _ = found
    try:
        return connect(address, authkey=key)
    except Exception as exc:  # refused / auth failed / timeout
        log.info("app IPC unavailable: %s", type(exc).__name__)
        return None


def run_host(stdin, stdout, argv: Optional[List[str]] = None, run_dir: Optional[str] = None,
             connect: Callable = Client, exit_fn: Callable[[int], None] = os._exit) -> int:
    run_dir = run_dir or default_run_dir()
    out_lock = threading.Lock()

    def send_out(msg):
        with out_lock:
            protocol.write_frame(stdout, msg)

    try:
        conn = _connect(run_dir, connect)
        if conn is None:
            # Wait for the extension's hello so it gets a definite answer.
            try:
                protocol.read_frame(stdin)
            except protocol.ProtocolError:
                pass
            send_out(protocol.hello_ack("", False))
            send_out(protocol.app_unavailable(60))
            return 0

        conn.send_bytes(protocol.dumps(protocol.port_opened(argv or [])))
        ack = protocol.loads(conn.recv_bytes(MAX_MESSAGE_BYTES))
        port_id = ack.get("port_id")

        def ipc_to_stdout():
            try:
                while True:
                    msg = protocol.loads(conn.recv_bytes(MAX_MESSAGE_BYTES))
                    if msg.get("type") == "to_extension":
                        send_out(msg.get("payload") or {})
                    elif msg.get("type") == "close":
                        send_out(protocol.bye(msg.get("reason", "app_quit")))
                        exit_fn(0)
                        return
            except (EOFError, OSError, protocol.ProtocolError):
                try:
                    send_out(protocol.error("ipc_lost", "lost connection to the app"))
                except Exception:
                    pass
                exit_fn(1)

        threading.Thread(target=ipc_to_stdout, name="ipc-reader", daemon=True).start()

        reason = "eof"
        while True:
            try:
                msg = protocol.read_frame(stdin)
            except protocol.ProtocolError as exc:
                reason = exc.code
                send_out(protocol.error(exc.code, "bad frame from browser"))
                break
            if msg is None:
                break
            if msg.get("type") == "ping":
                send_out(protocol.pong(msg.get("t")))
                continue
            conn.send_bytes(protocol.dumps(protocol.from_extension(port_id, msg)))
        try:
            conn.send_bytes(protocol.dumps(protocol.port_closed(port_id, reason)))
            conn.close()
        except (OSError, protocol.ProtocolError):
            pass
        return 0 if reason == "eof" else 1
    except (BrokenPipeError, OSError):
        return 1


def main(argv: Optional[List[str]] = None) -> int:
    logging.basicConfig(stream=sys.stderr, level=logging.WARNING)
    argv = list(sys.argv[1:] if argv is None else argv)
    if sys.platform.startswith("win"):  # binary stdio on Windows
        import msvcrt
        msvcrt.setmode(sys.stdin.fileno(), os.O_BINARY)
        msvcrt.setmode(sys.stdout.fileno(), os.O_BINARY)
    # Browser args (extension origin etc.) follow the --native-host flag.
    rest = [a for a in argv if a != "--native-host"]
    return run_host(sys.stdin.buffer, sys.stdout.buffer, argv=rest)
