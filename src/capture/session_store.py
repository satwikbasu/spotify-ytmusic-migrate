"""Fernet-encrypted store for the captured YouTube Music session.

``~/.playlist_migrator/credentials/youtube_session.enc`` replaces the old
plaintext ``headers.json``. Uses the app's master key and ``encrypt_data`` /
``decrypt_data`` from ``src.utils.encryption``.
"""

import json
import logging
import os
import time
from typing import Dict, Optional, Tuple

from . import paths

logger = logging.getLogger(__name__)


class SessionStore:
    def __init__(self, path: Optional[str] = None, key: Optional[bytes] = None,
                 key_path: Optional[str] = None):
        self.path = path or paths.session_path()
        self._key = key
        self._key_path = key_path or paths.master_key_path()

    def _get_key(self) -> bytes:
        if self._key is None:
            from src.utils.encryption import generate_key, load_key, save_key
            try:
                self._key = load_key(self._key_path)
            except FileNotFoundError:
                self._key = generate_key()
                save_key(self._key, self._key_path)
        return self._key

    def exists(self) -> bool:
        return os.path.exists(self.path)

    def save(self, headers: Dict[str, str], account_name: str = "") -> None:
        from src.utils.encryption import encrypt_data
        doc = {"v": 1, "headers": headers, "account_name": account_name, "saved_at": time.time()}
        paths.write_private(self.path, encrypt_data(json.dumps(doc), self._get_key()))
        logger.info("YouTube session saved (encrypted)")

    def load_full(self) -> Optional[dict]:
        if not os.path.exists(self.path):
            return None
        try:
            from src.utils.encryption import decrypt_data
            with open(self.path, "rb") as fh:
                doc = json.loads(decrypt_data(fh.read(), self._get_key()))
            if not isinstance(doc.get("headers"), dict):
                return None
            return doc
        except Exception as exc:  # corrupt / wrong key: treat as no session
            logger.warning("Stored YouTube session unreadable (%s)", type(exc).__name__)
            return None

    def load(self) -> Optional[Tuple[Dict[str, str], str]]:
        doc = self.load_full()
        if doc is None:
            return None
        return doc["headers"], doc.get("account_name", "")

    def clear(self) -> None:
        try:
            os.remove(self.path)
        except FileNotFoundError:
            pass
