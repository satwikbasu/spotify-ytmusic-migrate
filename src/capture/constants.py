"""Centralised identifiers for the capture bridge.

Everything marked PLACEHOLDER is swapped when the extension is published
(EXTENSION_BRIDGE_PROTOCOL.md section 11, open question 1). Nothing here is a
secret: the Chromium dev ``key`` is a *public* key whose derived id is stable
for unpacked loads.
"""

HOST_NAME = "com.playlist_migrator.capture"
HOST_DESCRIPTION = (
    "Hands your YouTube Music sign-in to the Playlist Migrator app on this computer."
)
PROTOCOL_VERSION = 1
MAX_MESSAGE_BYTES = 1024 * 1024  # 1 MB, both directions and on IPC

# --- Chromium family -------------------------------------------------------
# Public key for the extension manifest ("key" field) and the id Chromium
# derives from it (sha256 of the DER key, first 16 bytes, hex -> a..p).
DEV_CHROMIUM_EXTENSION_KEY = (
    "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAtgc0kbonEWF/CFsmt5kzjG5hRqEHrxLFmaMGls52"
    "FyljW7G77FMXZLeg/0IU7lCWl0BI6W9uJtxXwpZnghJssclIR3tSUQgfGSA+GVoGFozao1+eqFaCht3qfWod"
    "9jXGhz6svASsl97Fz2mTJ/8Zyo5Fi94tmMvGiL6BA4PQJv7NHOLxdB5JTyvXa3WiVxFMFE1uhpzAx2AuaJw4"
    "QyNtTj5zyQJ9G62ftAkNqpZ5INWtHckFXRQaaGLMvvqC3eSGX4FveG8/YfEjx7Sr3CeUGMzbMnS+S/3BriqF"
    "GBztzoe7U+JnScS0A1KL6/c6Rl5o0aiEhgtkghvepnuXSVuvtwIDAQAB"
)
DEV_CHROMIUM_EXTENSION_ID = "hbokpdiobdfeajdegeboolhagjbhmkim"
# PLACEHOLDER store ids: well-formed (32 chars a-p) but not real. Replace once
# the Chrome Web Store / Edge Add-ons listings exist.
CHROME_WEB_STORE_ID = "a" * 32  # PLACEHOLDER
EDGE_ADDONS_ID = "b" * 32  # PLACEHOLDER

# --- Firefox ---------------------------------------------------------------
FIREFOX_GECKO_ID = "capture@playlist-migrator.app"  # PLACEHOLDER until AMO

CHROMIUM_ALLOWED_EXTENSION_IDS = (
    CHROME_WEB_STORE_ID,
    EDGE_ADDONS_ID,
    DEV_CHROMIUM_EXTENSION_ID,
)
FIREFOX_ALLOWED_EXTENSIONS = (FIREFOX_GECKO_ID,)

# --- Files under ~/.playlist_migrator -------------------------------------
SESSION_FILE_NAME = "youtube_session.enc"
RUN_DIR_NAME = "run"
SOCKET_NAME = "capture.sock"
KEY_FILE_NAME = "capture.key"
INFO_FILE_NAME = "capture.json"
NATIVE_HOSTS_DIR_NAME = "native_hosts"
