"""Cookies -> ytmusicapi headers (single source of truth).

Moved from the prototype ``bridge/session.py`` (which now re-exports this
module). ytmusicapi accepts the resulting dict directly, so nothing is written
to disk in plaintext.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ytmusicapi.helpers import get_authorization, sapisid_from_cookie

ORIGIN = "https://music.youtube.com"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)


class MissingSapisidError(ValueError):
    """Raised when the cookie set has no __Secure-3PAPISID (i.e. not signed in)."""


def _cookie_header(cookies: List[Dict[str, Any]]) -> str:
    """Join cookie objects (extra keys ignored) into one Cookie header, sorted by
    name so two captures of the same set are byte-identical (dedupe)."""
    pairs = sorted(
        ((c["name"], c.get("value", "")) for c in cookies if c.get("name")),
        key=lambda p: p[0],
    )
    return "; ".join(f"{n}={v}" for n, v in pairs)


def cookie_set_hash(cookies: List[Dict[str, Any]]) -> str:
    import hashlib
    return hashlib.sha256(_cookie_header(cookies).encode("utf-8")).hexdigest()


def build_headers(cookies: List[Dict[str, Any]], user_agent: Optional[str] = None) -> Dict[str, str]:
    """Turn a browser cookie set into the header dict ``YTMusic(auth=...)`` wants."""
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
        "user-agent": user_agent or DEFAULT_USER_AGENT,
    }
