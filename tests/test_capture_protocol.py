"""Framing, message builders and redaction for the capture bridge."""

import io
import struct

import pytest

from src.capture import protocol
from src.capture.constants import MAX_MESSAGE_BYTES


def test_frame_round_trip_is_little_endian_length_prefixed():
    frame = protocol.encode_frame({"v": 1, "type": "ping", "t": 5})
    (n,) = struct.unpack("<I", frame[:4])
    assert n == len(frame) - 4
    assert protocol.read_frame(io.BytesIO(frame)) == {"v": 1, "type": "ping", "t": 5}


def test_clean_eof_is_none_and_truncation_is_error():
    assert protocol.read_frame(io.BytesIO(b"")) is None
    with pytest.raises(protocol.ProtocolError) as e:
        protocol.read_frame(io.BytesIO(b"\x05\x00"))
    assert e.value.code == "bad_frame"
    with pytest.raises(protocol.ProtocolError):
        protocol.read_frame(io.BytesIO(struct.pack("<I", 10) + b"{}"))


def test_oversize_rejected_both_directions():
    with pytest.raises(protocol.ProtocolError) as e:
        protocol.read_frame(io.BytesIO(struct.pack("<I", MAX_MESSAGE_BYTES + 1)))
    assert e.value.code == "too_large"
    with pytest.raises(protocol.ProtocolError):
        protocol.encode_frame({"type": "x", "blob": "a" * (MAX_MESSAGE_BYTES + 1)})


def test_non_object_and_bad_json_rejected():
    for body in (b"[1]", b"not json", b"\xff\xfe"):
        with pytest.raises(protocol.ProtocolError) as e:
            protocol.read_frame(io.BytesIO(struct.pack("<I", len(body)) + body))
        assert e.value.code == "bad_frame"


def test_unknown_type():
    with pytest.raises(protocol.ProtocolError) as e:
        protocol.message_type({"type": "nope"}, protocol.EXTENSION_TYPES)
    assert e.value.code == "unknown_type"
    assert protocol.message_type({"type": "hello"}, protocol.EXTENSION_TYPES) == "hello"


def test_builders_carry_version_and_drop_none():
    m = protocol.identity_failed("r1", "rate_limited", 60)
    assert m == {"v": 1, "type": "identity_failed", "request_id": "r1",
                 "code": "rate_limited", "retry_after_s": 60}
    assert "retry_after_s" not in protocol.identity_failed("r1", "signed_out")
    assert protocol.capture_request("r", "reauth")["purpose"] == "reauth"
    assert protocol.hello_ack("1", False)["app_connected"] is False


def test_redact_strips_cookie_values_and_authorization():
    msg = {"type": "cookies", "cookies": [{"name": "SID", "value": "SECRETVAL"}],
           "headers": {"authorization": "SAPISIDHASH 123_abc"}}
    out = protocol.redact(msg)
    assert "SECRETVAL" not in out and "123_abc" not in out
    text = protocol.redact("cookie: SID=SECRETVAL; HSID=OTHER\nauthorization: SAPISIDHASH 1_x")
    assert "SECRETVAL" not in text and "OTHER" not in text and "1_x" not in text
    assert "SECRET2" not in protocol.redact("__Secure-3PAPISID=SECRET2; x=1")
