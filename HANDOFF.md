# Session Handoff — Context for continuing this work

This file captures what was established across the live-testing and
architecture sessions, so a fresh Claude Code session (e.g. in the cloud) has
accurate context. It supersedes the stale `*_OAUTH_*` / `BROWSER_AUTH_*` /
`ACTION_REQUIRED` notes, several of which describe approaches since proven dead.

## Current state

- Engine is solid. Suite: **691 passing / 1 failing** (the 1 is a deliberate
  design question — `PlaylistCard` hardcodes dark greys vs `app_config` theme
  constants; owner's call).
- Live match rate: **97.6%** across 83 real tracks; residual misses are genuine
  YouTube Music catalogue absences, not matcher faults.
- A full migration of a real playlist completes (verified 14/14 and 12/12 live).

## Branches (all pushed to origin)

- `master` — original baseline.
- `fix/migration-accuracy` — the 11 verified bug fixes.
- `prototype/extension-bridge` — **active branch**; contains everything above
  plus the extension/bridge prototype, `setup.sh`, `.env.example`, this file.

## Auth reality (the load-bearing facts — do not re-litigate)

- **YouTube Music has no usable OAuth.** The ytmusicapi device flow issues a
  valid token, but every authenticated call returns HTTP 400 — YT Music's
  internal API rejects tokens from custom Google Cloud clients, any client type.
  `_authenticate_oauth()` now raises with this explanation. Verified live.
- **The only working YT Music auth is browser cookies.** A session needs the
  full cookie set plus an `authorization: SAPISIDHASH <ts>_<sha1>` header, which
  is *computed from* the `__Secure-3PAPISID` cookie (not captured). `bridge/
  session.py` does this.
- **A signed-out session fails silently** — `get_library_playlists()` returns
  `[]` rather than raising. Identity is checked with `get_account_info()`.
- Spotify side is fine: spotipy OAuth, redirect URI must be `127.0.0.1`.
- ISRC search does nothing — YT Music has no `isrc:` operator (removed; halved
  per-track time to ~1.63s, so a 29.5k-track library is ~13h).

## Extension + bridge prototype (what/why/how)

Replaces the manual `headers.json` paste with a one-click capture.

- `extension/` — MV3. Reads music.youtube.com cookies via `chrome.cookies`
  (which can see httpOnly cookies a web page cannot) and POSTs them to the
  bridge with a pairing token.
- `bridge/session.py` — cookie set → ytmusicapi headers dict (TDD, 3 tests).
- `bridge/bridge.py` — loopback HTTP server on 127.0.0.1:8765, validates with
  `get_account_info()`, writes `headers.json`.
- `bridge/app.py` — demo harness: migrates one playlist on connect.
- Verified end to end in a real Chromium (login faked by injecting known-good
  cookies via CDP, NOT by automating a Google login): popup reports the account
  and a live migration runs. See `bridge/README.md` to run it.

## Dead ends (established with evidence — don't retry)

- **Embedded-browser login** (WebView/CEF/Electron): Google returns
  `disallowed_useragent`. Blocked since 2023.
- **Automated Chromium login** (Playwright/Puppeteer): detected, "browser may
  not be secure."
- **Reading another browser's cookies from a native app**: Chrome App-Bound
  Encryption (v127+, Windows) blocks it; only infostealer-class bypasses exist.
- **Bookmarklet → local bridge**: CSP is NOT the blocker (connect-src absent),
  but Private Network Access blocks a public https page from reaching
  127.0.0.1. An extension is exempt; a page is not. This is why the capture
  MUST be an extension.
- **YouTube Data API v3 for writes**: `playlistItems.insert` = 50 units,
  10,000/day ⇒ ~200 tracks/day ⇒ ~148 days for 29.5k tracks. Quota extension
  is gated behind a partner relationship, not obtainable by an OSS tool.
- **Standalone Android app capturing login**: no way to read another app's
  session; WebView login blocked.
- **iOS background migration**: iOS suspends backgrounded apps within minutes;
  a ~13h local job is not feasible regardless of stack.

## Recommended architecture (agreed direction)

Thin **capture extension** (published to Chrome Web Store + Firefox AMO — a
one-time install, then one click per run) + **background desktop app** (Python
+ Flet, already cross-platform for Windows/macOS/Linux) that holds the session
and runs the day-long job, surviving browser closure. Keep the engine in
Python — do NOT port to JS for an extension-only design, because a day-long job
can't live in a browser tab. Runs on the user's own machine/IP (keeps the
safety property; a hosted service would be the most ban-prone and would custody
users' credentials).

## Open items

- Architecture spec: extension↔app contract, the **401 re-capture flow**
  (session cookies rotate over a multi-hour job → pause, prompt quick
  re-capture, resume via the existing resumable engine), background-process
  behaviour per desktop OS, packaging.
- Research the **store-review risk** for a bulk-write extension (the one real
  unknown).
- Housekeeping: 3 test playlists in the owner's YT Music library
  (`[TEST] under my grave`, `[TEST2] we could stay up all night 🥀`,
  `[PROTO] under my grave`); rotate the Spotify client secret (exposed in a
  session transcript).

## Reference artifacts (claude.ai)

- Bug ledger: https://claude.ai/code/artifact/9953d876-c1c9-4a23-9748-27f98ca6c757
- Install-path decision doc: https://claude.ai/code/artifact/5298567a-0f0b-4dd7-bd64-7512f3328a47
