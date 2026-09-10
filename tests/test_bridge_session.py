"""Tests for the bridge's cookie -> headers.json reconstruction."""

import json
import pytest

from bridge.session import build_headers, MissingSapisidError


def _cookie_list():
    """A minimal browser cookie set as chrome.cookies.getAll would return it."""
    return [
        {"name": "__Secure-3PAPISID", "value": "abc123DEF456/gHiJkL"},
        {"name": "SAPISID", "value": "abc123DEF456/gHiJkL"},
        {"name": "SID", "value": "sid-value"},
        {"name": "HSID", "value": "hsid-value"},
    ]


def test_build_headers_produces_a_cookie_and_authorization_header():
    """The reconstructed headers must carry every cookie plus a SAPISIDHASH auth."""
    headers = build_headers(_cookie_list())

    # every cookie name is present in the assembled Cookie header
    for c in _cookie_list():
        assert f"{c['name']}={c['value']}" in headers["cookie"]

    assert headers["authorization"].startswith("SAPISIDHASH ")
    # SAPISIDHASH format is "<unix_ts>_<40-char sha1 hex>"
    payload = headers["authorization"].split(" ", 1)[1]
    ts, _, digest = payload.partition("_")
    assert ts.isdigit()
    assert len(digest) == 40 and all(c in "0123456789abcdef" for c in digest)


def test_build_headers_sets_the_music_origin():
    headers = build_headers(_cookie_list())
    assert headers["origin"] == "https://music.youtube.com"
    assert headers["x-origin"] == "https://music.youtube.com"


def test_build_headers_rejects_a_cookie_set_with_no_sapisid():
    """Without __Secure-3PAPISID there is no signed-in session to authorize."""
    with pytest.raises(MissingSapisidError):
        build_headers([{"name": "SID", "value": "x"}])
