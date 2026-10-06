"""Wire protocol: Native Messaging framing, message builders, redaction.

Stdlib only so the native-messaging host can start in well under a second.
Framing: 4-byte little-endian length + UTF-8 JSON, 1 MB cap. All messages are
JSON objects with ``type`` and ``v``. Pickle is never used.
"""

import json
import re
import struct
from typing import Any, BinaryIO, Dict, Optional

from .constants import MAX_MESSAGE_BYTES, PROTOCOL_VERSION

V = PROTOCOL_VERSION

EXTENSION_TYPES = ("hello", "cookies", "signed_out", "error", "ping")
HOST_TO_EXTENSION_TYPES = (
    "hello_ack", "app_unavailable", "capture_request", "identity_confirmed",
    "identity_failed", "pong", "error", "bye",
)
IDENTITY_FAIL_CODES = ("signed_out", "rejected", "network", "rate_limited")


class ProtocolError(Exception):
    """Malformed or oversize message. ``code`` is one of bad_frame/too_large/unknown_type."""

    def __init__(self, code: str, message: str = ""):
        super().__init__(message or code)
        self.code = code


# --- framing ---------------------------------------------------------------

def dumps(obj: Dict[str, Any]) -> bytes:
    data = json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    if len(data) > MAX_MESSAGE_BYTES:
        raise ProtocolError("too_large", f"message is {len(data)} bytes")
    return data


def loads(data: bytes) -> Dict[str, Any]:
    if len(data) > MAX_MESSAGE_BYTES:
        raise ProtocolError("too_large")
    try:
        obj = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise ProtocolError("bad_frame", "invalid JSON") from exc
    if not isinstance(obj, dict):
        raise ProtocolError("bad_frame", "message must be a JSON object")
    return obj


def encode_frame(obj: Dict[str, Any]) -> bytes:
    body = dumps(obj)
    return struct.pack("<I", len(body)) + body


def _read_exact(stream: BinaryIO, n: int) -> bytes:
    buf = b""
    while len(buf) < n:
        chunk = stream.read(n - len(buf))
        if not chunk:
            break
        buf += chunk
    return buf


def read_frame(stream: BinaryIO) -> Optional[Dict[str, Any]]:
    """Read one framed message. ``None`` on clean EOF (port disconnected)."""
    header = _read_exact(stream, 4)
    if not header:
        return None
    if len(header) < 4:
        raise ProtocolError("bad_frame", "truncated length prefix")
    (length,) = struct.unpack("<I", header)
    if length > MAX_MESSAGE_BYTES:
        raise ProtocolError("too_large", f"frame of {length} bytes")
    body = _read_exact(stream, length)
    if len(body) < length:
        raise ProtocolError("bad_frame", "truncated body")
    return loads(body)


def write_frame(stream: BinaryIO, obj: Dict[str, Any]) -> None:
    stream.write(encode_frame(obj))
    stream.flush()


def message_type(msg: Dict[str, Any], allowed) -> str:
    t = msg.get("type")
    if not isinstance(t, str) or t not in allowed:
        raise ProtocolError("unknown_type", f"unknown type {t!r}")
    return t


# --- host/app -> extension builders ----------------------------------------

def _m(type_: str, **fields) -> Dict[str, Any]:
    msg = {"v": V, "type": type_}
    msg.update({k: val for k, val in fields.items() if val is not None})
    return msg


def hello_ack(app_version: str, app_connected: bool, port_id: Optional[str] = None):
    return _m("hello_ack", app_version=app_version, app_connected=app_connected, port_id=port_id)


def app_unavailable(retry_after_s: int = 60):
    return _m("app_unavailable", retry_after_s=retry_after_s)


def capture_request(request_id: str, purpose: str = "connect"):
    return _m("capture_request", request_id=request_id, purpose=purpose)


def identity_confirmed(request_id: Optional[str], account_name: str):
    return _m("identity_confirmed", request_id=request_id, account_name=account_name)


def identity_failed(request_id: Optional[str], code: str, retry_after_s: Optional[int] = None):
    return _m("identity_failed", request_id=request_id, code=code, retry_after_s=retry_after_s)


def pong(t):
    return _m("pong", t=t)


def error(code: str, message: str = "", request_id: Optional[str] = None):
    return _m("error", code=code, message=message, request_id=request_id)


def bye(reason: str):
    return _m("bye", reason=reason)


# --- host <-> app IPC envelopes --------------------------------------------

def port_opened(argv):
    return _m("port_opened", argv=list(argv))


def port_ack(port_id: str, app_version: str):
    return _m("port_ack", port_id=port_id, app_version=app_version)


def port_closed(port_id: Optional[str], reason: str):
    return _m("port_closed", port_id=port_id, reason=reason)


def from_extension(port_id: Optional[str], payload: Dict[str, Any]):
    return _m("from_extension", port_id=port_id, payload=payload)


def to_extension(payload: Dict[str, Any]):
    return _m("to_extension", payload=payload)


def close(reason: str):
    return _m("close", reason=reason)


# --- redaction --------------------------------------------------------------

REDACTED = "[redacted]"
_SENSITIVE_KEYS = {"cookie", "cookies", "authorization", "value", "headers", "set-cookie"}
_TEXT_PATTERNS = [
    (re.compile(r"(?i)(authorization|cookie)\s*[:=]\s*[^\r\n]+"), r"\1: " + REDACTED),
    (re.compile(r"SAPISIDHASH\s+\S+"), "SAPISIDHASH " + REDACTED),
    (re.compile(r"(?i)\b(__Secure-[13]P(?:API)?SID(?:TS|CC)?|SAPISID|APISID|SSID|HSID|SID|SIDCC|LOGIN_INFO)=[^;\s]+"),
     r"\1=" + REDACTED),
]


def redact(obj: Any) -> str:
    """Return a log-safe string for ``obj``; never contains cookie values or auth headers."""
    def walk(o):
        if isinstance(o, dict):
            return {k: (REDACTED if str(k).lower() in _SENSITIVE_KEYS else walk(v)) for k, v in o.items()}
        if isinstance(o, (list, tuple)):
            return [walk(i) for i in o]
        return o

    text = obj if isinstance(obj, str) else json.dumps(walk(obj), default=str)
    for pat, repl in _TEXT_PATTERNS:
        text = pat.sub(repl, text)
    return text
