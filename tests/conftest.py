"""Suite-wide guards."""

import os

# initialize_app_state() starts the capture hub; tests must never open an IPC
# listener or write run/ files under the real home directory.
os.environ.setdefault("PLAYLIST_MIGRATOR_NO_HUB", "1")
