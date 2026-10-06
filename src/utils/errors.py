"""Engine-level exception types shared across layers.

Kept free of in-repo imports so it can be imported from anywhere (searcher,
migrator, worker, manager, UI) without creating cycles.
"""

import re
from typing import Optional

from ytmusicapi.exceptions import YTMusicError, YTMusicServerError, YTMusicUserError


class YouTubeAuthError(Exception):
    """The YouTube Music session is no longer valid.

    Raised (never swallowed) by ``YouTubeSearcher`` and ``PlaylistMigrator``
    when a ytmusicapi call fails because the browser-cookie session has
    expired, rotated, or been signed out — HTTP 401/403 from the backend, a
    "please provide authentication" error, or a *silent* sign-out where the
    backend answers 200 but no longer knows who we are.

    ``BackgroundWorker`` reacts by parking the job as ``paused_auth`` (not
    ``failed``) so it can be continued from the saved resume state once a
    refreshed client has been injected via ``MigrationManager.
    reauthenticate_youtube()`` (contract §4.3 auth-failure handling, fed by
    the §4.1 extension re-capture).
    """

    def __init__(self, message: str = "YouTube Music session is no longer valid",
                 cause: Optional[BaseException] = None):
        super().__init__(message)
        self.cause = cause


# "Server returned HTTP 401: Unauthorized." / "HTTP 403: Forbidden."
_HTTP_AUTH_STATUS = re.compile(r"\bHTTP\s*(401|403)\b")
_HTTP_RATE_STATUS = re.compile(r"\bHTTP\s*429\b")


def is_auth_error(exc: BaseException) -> bool:
    """Classify a ytmusicapi exception as a session/auth failure.

    ytmusicapi surfaces backend failures as ``YTMusicServerError`` with the
    HTTP status in the message (``"Server returned HTTP 401: Unauthorized"``)
    and an unauthenticated client as ``YTMusicUserError("Please provide
    authentication ...")``. 429s are deliberately *not* auth errors — those
    belong to the ``RateLimiter``.
    """
    if isinstance(exc, YouTubeAuthError):
        return True
    if not isinstance(exc, YTMusicError):
        return False

    text = str(exc)
    if _HTTP_RATE_STATUS.search(text):
        return False
    if isinstance(exc, YTMusicUserError) and 'authentication' in text.lower():
        return True
    if isinstance(exc, YTMusicServerError):
        if _HTTP_AUTH_STATUS.search(text):
            return True
        lowered = text.lower()
        if 'unauthorized' in lowered or 'forbidden' in lowered:
            return True
    return False
