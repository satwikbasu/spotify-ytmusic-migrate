"""build_headers moves + encrypted session store + identity verification."""

import os
import stat
from unittest.mock import MagicMock

import pytest
from cryptography.fernet import Fernet

from src.capture.session import MissingSapisidError, build_headers, cookie_set_hash
from src.capture.session_store import SessionStore
from src.capture.verify import verify_identity

COOKIES = [
    {"name": "SID", "value": "s", "domain": ".youtube.com", "httpOnly": True},
    {"name": "__Secure-3PAPISID", "value": "abc/DEF", "secure": True},
]


def test_headers_sorted_deterministic_and_extra_keys_ignored():
    a = build_headers(COOKIES)
    b = build_headers(list(reversed(COOKIES)))
    assert a["cookie"] == b["cookie"] == "SID=s; __Secure-3PAPISID=abc/DEF"
    assert a["authorization"].startswith("SAPISIDHASH ")
    assert cookie_set_hash(COOKIES) == cookie_set_hash(list(reversed(COOKIES)))
    assert build_headers(COOKIES, user_agent="UA/1")["user-agent"] == "UA/1"


def test_signed_out_cookie_set_raises():
    with pytest.raises(MissingSapisidError):
        build_headers([{"name": "SID", "value": "s"}])


def test_bridge_prototype_still_imports_from_single_source():
    from bridge.session import build_headers as old
    assert old is build_headers


def test_store_round_trip_encrypted_and_0600(tmp_path):
    store = SessionStore(path=str(tmp_path / "creds" / "youtube_session.enc"), key=Fernet.generate_key())
    assert store.load() is None
    store.save({"cookie": "SID=PLAINSECRET"}, "Ann")
    raw = open(store.path, "rb").read()
    assert b"PLAINSECRET" not in raw
    assert store.load() == ({"cookie": "SID=PLAINSECRET"}, "Ann")
    if os.name == "posix":
        assert stat.S_IMODE(os.stat(store.path).st_mode) == 0o600
    store.clear()
    assert store.load() is None and not store.exists()
    store.clear()  # idempotent


def test_store_wrong_key_or_corrupt_is_none(tmp_path):
    p = str(tmp_path / "s.enc")
    SessionStore(path=p, key=Fernet.generate_key()).save({"cookie": "x"}, "A")
    assert SessionStore(path=p, key=Fernet.generate_key()).load() is None


def _limiter():
    return MagicMock()


def test_verify_ok_goes_through_rate_limiter():
    c, lim = MagicMock(), _limiter()
    c.get_account_info.return_value = {"accountName": "Ann"}
    r = verify_identity(c, lim)
    assert r.ok and r.account_name == "Ann"
    lim.check_limit.assert_called_once()
    lim.record_request.assert_called_once()


@pytest.mark.parametrize("value", [[], {}, None, {"x": 1}])
def test_verify_signed_out_trap(value):
    c = MagicMock()
    c.get_account_info.return_value = value
    assert verify_identity(c, _limiter()).code == "signed_out"


def test_verify_classifies_errors():
    from ytmusicapi.exceptions import YTMusicServerError
    cases = [
        (YTMusicServerError("Server returned HTTP 401: Unauthorized."), "signed_out"),
        (ConnectionError("down"), "network"),
        (YTMusicServerError("Server returned HTTP 500: boom"), "rejected"),
    ]
    for exc, code in cases:
        c = MagicMock()
        c.get_account_info.side_effect = exc
        assert verify_identity(c, _limiter()).code == code
    c = MagicMock()
    c.get_account_info.side_effect = YTMusicServerError("Server returned HTTP 429: slow")
    lim = _limiter()
    lim.backoff_seconds = 60
    r = verify_identity(c, lim)
    assert r.code == "rate_limited" and r.retry_after_s == 60
