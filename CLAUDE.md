# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> **Continuing earlier work?** Read `HANDOFF.md` first — it captures the live-testing
> findings, the auth reality, the extension/bridge prototype, and the dead ends that the
> stale root `*_OAUTH_*` / `BROWSER_AUTH_*` notes get wrong.

## What this is

A local desktop app (Python + Flet) that migrates Spotify playlists to YouTube Music. Design goals from `spec.md`: survive bulk migrations (50k+ tracks) without hitting rate limits or getting accounts banned, run entirely on the user's machine, and resume interrupted work.

## Commands

```bash
# The committed venv/ is a Windows venv (Scripts/, not bin/) and cannot be used
# from WSL or Linux. Create a native one there:
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python main.py                    # run the app (Flet desktop window)

python -m pytest tests/                          # full suite
python -m pytest tests/test_track_matcher.py     # one file
python -m pytest tests/test_track_matcher.py::TestMatchTrack::test_exact_match -v   # one test
python -m pytest --cov=src --cov=config tests/   # coverage
```

`flet` must stay pinned to the 0.28 line. The 0.8x releases reorganised the API and the
code will not import against them.

There is no linter or formatter configured, and no pytest config file — pytest is invoked as `python -m pytest` from the repo root so `src/` and `config/` resolve as top-level packages.

## Configuration

Credentials come from environment variables loaded from a `.env` in the repo root (`main.py` calls `load_dotenv()`): `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET`, `SPOTIFY_REDIRECT_URI`, `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`.

`config/app_config.py` is a flat module of constants (no class), covering window/theme values, paths, thresholds, and quota limits. All runtime state lives under `~/.playlist_migrator/`: `cache.db`, `app.log`, and `credentials/`.

Spotify's redirect URI must use `127.0.0.1`, not `localhost` — Spotify rejects `localhost` as of Nov 2025.

## Architecture

Layers, bottom-up. Each layer only knows the one below it.

**Auth (`src/auth/`)** — `TokenManager` is the facade the UI uses; it wraps `SpotifyAuthenticator` and `YouTubeAuthenticator` and encrypts token files at rest with Fernet (`src/utils/encryption.py`), decrypting to a temp file only when a client is constructed.

YouTube auth is the fragile part and has been rewritten several times (see the `YOUTUBE_*`/`BROWSER_AUTH_*` markdown files at the repo root for the history). `YouTubeAuthenticator.authenticate()` uses browser-cookie auth — a `headers.json`/`browser.json` in the repo root produced by `ytmusicapi browser`. OAuth is **not** a working fallback: the device flow issues a valid token, but YouTube Music's internal API rejects tokens from custom Google Cloud clients with HTTP 400, so `_authenticate_oauth()` now raises with that explanation. Browser headers need an `authorization: SAPISIDHASH …` header; a capture taken from a non-XHR request won't have one, and ytmusicapi will misread the file as OAuth. Note that a signed-out session returns `[]` from `get_library_playlists` rather than raising, so identity is checked with `get_account_info()`. Note the app deliberately uses ytmusicapi (internal web API, no quota) rather than YouTube Data API v3.

**Services** — `SpotifyFetcher` (paginated playlist/track fetch), `YouTubeSearcher` (search), `TrackMatcher` (rapidfuzz scoring against `DEFAULT_MATCH_THRESHOLD`, default 75).

**Migration (`src/migrators/`)** — `PlaylistMigrator` migrates one playlist: create the YT playlist, then per track search → match → batch-add. `MigrationManager` is the facade above it, wiring the clients, `RateLimiter`, `CacheManager`, `BackgroundWorker`, and `Notifier` together and exposing start/stop/pause and status to the UI. The UI should talk to `MigrationManager`, never to `PlaylistMigrator` directly.

**Persistence (`src/utils/cache_manager.py`)** — one SQLite DB with `playlists`, `tracks`, and `match_cache` tables. `BackgroundWorker` adds its own `migrations` job table to the same DB, which is what makes migrations resumable across app restarts (`resume_incomplete_migrations()`).

**Rate limiting (`src/utils/rate_limiter.py`)** — enforces daily and per-minute caps, and `handle_429()` applies exponential backoff honouring `Retry-After`. Any new API call path must go through it; bypassing it is the thing that gets accounts banned.

**UI (`src/ui/`)** — every screen subclasses `BaseScreen` (`build()` is abstract) and navigates via `self.navigate_to(OtherScreen, ...)`. Screens share a plain `app_state` dict for cross-screen data (clients, selected playlists, results). Flow: Welcome → PlaylistSelection → MigrationProgress → Results, with Settings reachable from Welcome. Screen-to-screen imports are done inside the navigation method to avoid import cycles — keep that pattern. Reusable widgets (`AppButton`, `PlaylistCard`, `ProgressBar`, `StatusBanner`, …) live in `src/ui/components.py`; see `src/ui/README.md` and `src/ui/base_screen_README.md`.

## Repo hygiene note

The root directory holds a pile of scratch scripts (`test_*.py`, `debug_oauth_response.py`, `diagnose_oauth_client.py`) and troubleshooting notes from the YouTube auth debugging. These are not part of the suite — the real tests are all under `tests/`. Don't extend the root scripts; add tests in `tests/`.
