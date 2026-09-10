"""Prototype entry point: run the bridge, then migrate one playlist on connect.

Spotify auth is taken from the cached token created during earlier testing
(scratchpad/.spotify_cache). YouTube auth arrives live from the extension. This
is a demo harness, not the production app flow.
"""

from __future__ import annotations

import logging
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv(str(Path(__file__).resolve().parent.parent / ".env"))

import spotipy
from spotipy.oauth2 import SpotifyOAuth
from ytmusicapi import YTMusic

from bridge import bridge
from src.auth.spotify_auth import SpotifyAuthenticator
from src.fetchers.spotify_fetcher import SpotifyFetcher
from src.matchers.track_matcher import TrackMatcher
from src.migrators.playlist_migrator import PlaylistMigrator
from src.searchers.youtube_searcher import YouTubeSearcher
from src.utils.cache_manager import CacheManager
from src.utils.rate_limiter import RateLimiter

logger = logging.getLogger("bridge.app")

# The playlist to migrate in this demo; override with DEMO_PLAYLIST.
DEMO_PLAYLIST = os.environ.get("DEMO_PLAYLIST", "under my grave")
SPOTIFY_CACHE = os.environ.get(
    "SPOTIFY_CACHE",
    "/tmp/claude-0/-root-spotify-yt-migrate/"
    "d4316209-035c-47ee-b202-cfde780c7592/scratchpad/.spotify_cache",
)


def _spotify() -> spotipy.Spotify:
    return spotipy.Spotify(auth_manager=SpotifyOAuth(
        client_id=os.environ["SPOTIFY_CLIENT_ID"],
        client_secret=os.environ["SPOTIFY_CLIENT_SECRET"],
        redirect_uri=os.environ["SPOTIFY_REDIRECT_URI"],
        scope=SpotifyAuthenticator.REQUIRED_SCOPES,
        cache_path=SPOTIFY_CACHE,
        open_browser=False,
    ))


def migrate_on_connect(account_name: str) -> None:
    """Runs in a background thread once the extension delivers a valid session."""
    try:
        bridge.STATE["migration"] = {"status": "starting", "playlist": DEMO_PLAYLIST}
        sp = _spotify()
        rl = RateLimiter(per_minute_limit=120, daily_limit=10000)
        cm = CacheManager(db_path=os.path.join(tempfile.mkdtemp(), "bridge_demo.db"))
        fetcher = SpotifyFetcher(sp, rl, cm)

        playlists = fetcher.get_user_playlists(use_cache=False)
        target = next((p for p in playlists if p.get("name") == DEMO_PLAYLIST), None)
        if target is None:
            bridge.STATE["migration"] = {"status": "error",
                                         "error": f"playlist {DEMO_PLAYLIST!r} not found"}
            return
        tracks = fetcher.get_playlist_tracks(target["id"])

        yt = YTMusic(str(bridge.HEADERS_PATH))
        migrator = PlaylistMigrator(
            ytmusic_client=yt,
            youtube_searcher=YouTubeSearcher(ytmusic_client=yt, rate_limiter=rl),
            track_matcher=TrackMatcher(threshold=75),
            cache_manager=cm,
            rate_limiter=rl,
        )
        bridge.STATE["migration"] = {"status": "running", "playlist": DEMO_PLAYLIST,
                                     "total": len(tracks)}
        report = migrator.migrate_playlist(f"[PROTO] {DEMO_PLAYLIST}", tracks)
        bridge.STATE["migration"] = {
            "status": "complete",
            "playlist": report["playlist_name"],
            "matched": report["matched_tracks"],
            "total": report["total_tracks"],
            "url": report["playlist_url"],
        }
        logger.info("migration complete: %s/%s -> %s",
                    report["matched_tracks"], report["total_tracks"], report["playlist_url"])
    except Exception as exc:  # noqa: BLE001
        logger.exception("migration failed")
        bridge.STATE["migration"] = {"status": "error", "error": str(exc)[:300]}


if __name__ == "__main__":
    bridge.run(migration_hook=migrate_on_connect)
