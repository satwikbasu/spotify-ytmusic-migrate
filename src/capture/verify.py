"""Identity verification of a captured session, always through ``RateLimiter``.

A signed-out ytmusicapi session returns ``[]`` from library calls instead of
raising, so identity is only confirmed by ``get_account_info()`` returning a
real account (EXTENSION_BRIDGE_PROTOCOL.md section 3.3).
"""

import logging
import threading
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)

_fallback_limiter = None


def _get_fallback_limiter():
    """A real RateLimiter for callers that have no engine yet (cold start)."""
    global _fallback_limiter
    if _fallback_limiter is None:
        from src.utils.rate_limiter import RateLimiter
        _fallback_limiter = RateLimiter(daily_limit=None, per_minute_limit=40,
                                        min_interval=1.0, jitter=0.5)
    return _fallback_limiter


@dataclass
class VerifyResult:
    ok: bool
    code: Optional[str] = None  # signed_out | rate_limited | network | rejected
    account_name: str = ""
    retry_after_s: Optional[int] = None


def default_client_factory(headers: Dict[str, str]):
    from ytmusicapi import YTMusic
    return YTMusic(auth=headers)


def verify_identity(client: Any, rate_limiter=None) -> VerifyResult:
    from src.utils.errors import is_auth_error

    limiter = rate_limiter or _get_fallback_limiter()
    limiter.check_limit()
    try:
        account = client.get_account_info()
    except Exception as exc:
        text = str(exc)
        if is_auth_error(exc):
            return VerifyResult(False, "signed_out")
        if "429" in text or "rate limit" in text.lower():
            retry = int(getattr(limiter, "backoff_seconds", 60) or 60)
            # Register the backoff on the shared limiter without blocking the hub.
            threading.Thread(target=limiter.handle_429, name="verify-429", daemon=True).start()
            return VerifyResult(False, "rate_limited", retry_after_s=retry)
        try:
            import requests
            net = (requests.exceptions.RequestException,)
        except ImportError:  # pragma: no cover
            net = ()
        if isinstance(exc, net + (ConnectionError, TimeoutError, OSError)):
            return VerifyResult(False, "network")
        return VerifyResult(False, "rejected")
    finally:
        try:
            limiter.record_request()
        except Exception:  # pragma: no cover - accounting must not mask result
            logger.debug("record_request failed", exc_info=True)

    if not isinstance(account, dict):
        return VerifyResult(False, "signed_out")
    name = account.get("accountName") or account.get("channelHandle")
    if not name:
        return VerifyResult(False, "signed_out")
    return VerifyResult(True, account_name=str(name))
