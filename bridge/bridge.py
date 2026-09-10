"""Local HTTP bridge between the browser extension and the migration engine.

Flow:
  1. Extension reads music.youtube.com cookies and POSTs them to /yt-session.
  2. Bridge rebuilds a YTMusic browser session, validates it with
     get_account_info(), and writes headers.json for the engine.
  3. Bridge kicks off a migration of one playlist and reports progress.

This is a prototype: single user, loopback only, one pairing token. Not
hardened for anything beyond a local demo.
"""

from __future__ import annotations

import json
import logging
import os
import secrets
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ytmusicapi import YTMusic

from bridge.session import build_headers, MissingSapisidError

logger = logging.getLogger("bridge")

HOST, PORT = "127.0.0.1", 8765
REPO_ROOT = Path(__file__).resolve().parent.parent
HEADERS_PATH = REPO_ROOT / "headers.json"

# A pairing token printed at startup; the extension must echo it. Stops arbitrary
# web pages on the machine from POSTing cookies at the loopback port.
PAIRING_TOKEN = os.environ.get("BRIDGE_TOKEN") or secrets.token_urlsafe(12)

# Shared connection state, read back by /status.
STATE: Dict[str, Any] = {"connected": False, "account": None, "migration": None}
_migration_hook = None  # set by run(); called (account) -> None after connect


class Handler(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "content-type, x-bridge-token")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")

    def _json(self, code: int, body: Dict[str, Any]):
        payload = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self._cors()
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        if self.path == "/status":
            self._json(200, STATE)
        elif self.path == "/ping":
            self._json(200, {"ok": True, "service": "yt-migrate-bridge"})
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/yt-session":
            return self._json(404, {"error": "not found"})

        if self.headers.get("x-bridge-token") != PAIRING_TOKEN:
            return self._json(403, {"error": "bad or missing pairing token"})

        try:
            length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(length) or b"{}")
            cookies = data.get("cookies", [])
        except Exception as exc:  # noqa: BLE001
            return self._json(400, {"error": f"bad request body: {exc}"})

        try:
            headers = build_headers(cookies)
        except MissingSapisidError as exc:
            return self._json(400, {"error": str(exc)})

        # Validate the session really is signed in before trusting it.
        try:
            HEADERS_PATH.write_text(json.dumps(headers, indent=2), encoding="utf-8")
            yt = YTMusic(str(HEADERS_PATH))
            account = yt.get_account_info()
        except Exception as exc:  # noqa: BLE001
            logger.warning("session validation failed: %s", exc)
            return self._json(
                401,
                {"error": "YouTube Music rejected the session - sign in first.",
                 "detail": str(exc)[:200]},
            )

        name = account.get("accountName") if isinstance(account, dict) else None
        STATE.update(connected=True, account=name)
        logger.info("connected as %s; headers.json written", name)

        if _migration_hook is not None:
            threading.Thread(target=_migration_hook, args=(name,), daemon=True).start()

        self._json(200, {"connected": True, "account": name})

    def log_message(self, *_):  # silence default stderr spam
        pass


def run(migration_hook=None):
    """Start the bridge. migration_hook(account_name) runs after a good connect."""
    global _migration_hook
    _migration_hook = migration_hook
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Bridge listening on http://{HOST}:{PORT}")
    print(f"Pairing token: {PAIRING_TOKEN}")
    print("Waiting for the extension to POST /yt-session ...")
    server.serve_forever()


if __name__ == "__main__":
    run()
