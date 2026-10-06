"""Tiny JSON-backed user settings store.

Holds the few values the user should only ever have to enter once, most
importantly their own Spotify Client ID (CONTEXT_CONTRACT.md section 4.2,
Option A). It lives under ``~/.playlist_migrator/`` (``app_config.APP_DATA_DIR``),
never in the repo. A Client ID is a public identifier, not a secret (PKCE uses
no client secret), so the file is plain JSON; tokens stay Fernet-encrypted by
``TokenManager``.

Shape of ``user_config.json``::

    {"spotify_client_id": "<32 lowercase hex characters>"}
"""

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, Optional

from config import app_config

logger = logging.getLogger(__name__)

CONFIG_FILE_NAME = "user_config.json"
SPOTIFY_CLIENT_ID_KEY = "spotify_client_id"

_CLIENT_ID_RE = re.compile(r"^[0-9a-f]{32}$")


def config_path() -> Path:
    """Path of the settings file (resolved on every call so tests can redirect it)."""
    return Path(app_config.APP_DATA_DIR) / CONFIG_FILE_NAME


def clean_client_id(value: Optional[str]) -> str:
    """Trim surrounding whitespace from a pasted Client ID."""
    return (value or "").strip()


def is_valid_client_id(value: Optional[str]) -> bool:
    """True when the trimmed value is exactly 32 lowercase hex characters."""
    return bool(_CLIENT_ID_RE.match(clean_client_id(value)))


def load() -> Dict[str, Any]:
    """Read all settings. A missing or corrupt file yields an empty dict."""
    try:
        with open(config_path(), "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as e:
        logger.warning("Could not read user config, ignoring it: %s", e)
        return {}


def _save(data: Dict[str, Any]) -> None:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


def get(key: str, default: Any = None) -> Any:
    """Return one stored value, or ``default``."""
    return load().get(key, default)


def set(key: str, value: Any) -> None:  # noqa: A001 - mirrors dict-style API
    """Store one value (atomic write)."""
    data = load()
    data[key] = value
    _save(data)


def remove(key: str) -> None:
    """Delete one value if present."""
    data = load()
    if key in data:
        del data[key]
        _save(data)


def clear() -> None:
    """Delete the settings file entirely."""
    try:
        config_path().unlink()
    except FileNotFoundError:
        pass
    except OSError as e:
        logger.warning("Could not delete user config: %s", e)


def get_spotify_client_id() -> Optional[str]:
    """The saved Spotify Client ID, or None if none is saved or it is malformed."""
    value = get(SPOTIFY_CLIENT_ID_KEY)
    if isinstance(value, str) and is_valid_client_id(value):
        return clean_client_id(value)
    return None


def set_spotify_client_id(value: str) -> str:
    """Validate, trim and save the Spotify Client ID.

    Raises:
        ValueError: If the value is not 32 lowercase hex characters.
    """
    cleaned = clean_client_id(value)
    if not is_valid_client_id(cleaned):
        raise ValueError("Spotify Client ID must be 32 lowercase letters/numbers")
    set(SPOTIFY_CLIENT_ID_KEY, cleaned)
    return cleaned
