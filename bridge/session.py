"""Reconstruct a YTMusic browser session from cookies handed over by the extension.

The extension calls chrome.cookies.getAll() for music.youtube.com and sends the
raw cookie objects. A working ytmusicapi browser session needs two things: the
full Cookie header, and an ``authorization: SAPISIDHASH <ts>_<sha1>`` header
derived from the __Secure-3PAPISID cookie. Google's own JS computes that hash
per request; ytmusicapi ships the same helper, which we reuse here.
"""

from __future__ import annotations

from typing import Any, Dict, List

from ytmusicapi.helpers import get_authorization, sapisid_from_cookie

ORIGIN = "https://music.youtube.com"


class MissingSapisidError(ValueError):
    """Raised when the cookie set has no __Secure-3PAPISID (i.e. not signed in)."""


def _cookie_header(cookies: List[Dict[str, Any]]) -> str:
    """Join chrome.cookies objects into a single Cookie request header."""
    return "; ".join(f"{c['name']}={c['value']}" for c in cookies if c.get("name"))


def build_headers(cookies: List[Dict[str, Any]]) -> Dict[str, str]:
    """Turn a browser cookie set into the header dict YTMusic("headers.json") wants."""
    cookie_header = _cookie_header(cookies)
    try:
        sapisid = sapisid_from_cookie(cookie_header)
    except KeyError as exc:
        raise MissingSapisidError(
            "No __Secure-3PAPISID cookie found - the session is not signed in to "
            "music.youtube.com."
        ) from exc

    return {
        "cookie": cookie_header,
        "authorization": get_authorization(sapisid + " " + ORIGIN),
        "origin": ORIGIN,
        "x-origin": ORIGIN,
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9",
        "content-type": "application/json",
        "user-agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        ),
    }
