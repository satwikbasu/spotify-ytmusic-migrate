# CONTEXT CONTRACT — read this FIRST, every time

> This is the single source of truth for what this product is, what it must feel
> like, what has been decided (with evidence), and the invariants no change may
> break. Any agent — human or AI — working on this repo reads this file, plus
> `CLAUDE.md` and `HANDOFF.md`, before writing anything. If a change contradicts
> this file, the change is wrong unless this file is updated first with a reason.

---

## 1. The one-sentence goal (the thing we optimise for)

A non-technical person migrates their entire music library (up to ~50,000 tracks)
from Spotify to YouTube Music by: **click "Login with Spotify" → click "Connect
YouTube Music" → select playlists (or "Everything") → click Start → walk away.**
The job runs **passively in the background for hours**, entirely **on the user's
own machine**, and **resumes** if interrupted.

**Primary success metric: the UX feels that seamless.** Not code elegance, not
reuse of what exists. When a decision trades "reuse the current code" against
"the user does one fewer manual step," the user wins.

## 2. Who the user is (design to this persona, not to ourselves)

- Cannot open DevTools. Cannot copy/paste a token or edit a JSON file. Will not
  run a terminal command or a Python script by hand.
- Will install a signed desktop app by double-clicking, and will install a
  browser extension from an official store with one click.
- Will tolerate a **one-time** setup chore if it is guided, visual, and
  validated with clear error messages — but every avoidable step is a failure.
- Expects to close the laptop lid / walk away and come back to a finished job.

## 3. Platform reality (verified — do not re-litigate; see HANDOFF.md + research)

- **Desktop only: Windows / macOS / Linux.** No native mobile app. (iOS suspends
  background apps; Android can't capture another app's session and has no
  Chromium extensions.) A phone's only realistic role is a *monitor* companion
  later — not the engine, not capture.
- **YouTube Music auth = browser cookie capture via an extension. No exception.**
  No usable OAuth; embedded/automated browser logins are blocked by Google.
  There is **no "without extension" path** for a non-technical user.
- The engine stays **Python** (cross-platform, holds the session, runs the
  day-long job, survives browser closure). Do NOT port the engine to JS.

## 4. Architecture decisions (DECIDED — with evidence)

### 4.1 YouTube Music capture: extension → Native Messaging → engine
- A thin **capture extension** (Chrome Web Store + Edge Add-ons + Firefox AMO)
  reads `music.youtube.com` cookies via `chrome.cookies` and hands them to the
  desktop engine via **browser Native Messaging** (stdio host spawned by the
  browser), NOT a localhost HTTP port + typed pairing token.
  - Kills the copy/paste pairing token, the `Access-Control-Allow-Origin: *`
    surface, and the Private-Network-Access concerns in one move.
  - Keep a long-lived `connectNative` port so the engine can ask the extension
    to **silently re-read cookies** when a 401/403 appears mid-job (zero clicks
    while the browser is open). Fall back to a one-click re-capture prompt when
    the browser is closed.
- Coverage: Chrome, Edge, Brave, other Chromium, Firefox on desktop. **Safari**
  only via a separate Apple-signed Mac app wrapper (defer). ChromeOS: no.
- The installer registers the native-host manifest for every detected browser
  and **re-registers on each app launch** (browser may be installed after app).

### 4.2 Spotify ingestion: Option A preferred, Option B opt-in fallback
Spotify's API caps a public app at ~5 users per Client ID and restricts higher
quota to businesses with ≥250k MAU — so a shared public Client ID **cannot ship
publicly**. Therefore:

- **Option A (DEFAULT): BYO Client ID wizard, Authorization Code + PKCE.**
  The user creates their own Spotify app once and pastes their Client ID (no
  secret with PKCE). As of July 2026 quota is counted **per developer account**,
  so each user gets their own full quota; the 5-user cap is a non-issue because
  the user is the only user of their own app. **Requires the user to have
  Spotify Premium** (hard gate — detect it and message clearly).
  - Wizard must minimise friction: open the dashboard URL for them, pre-copy the
    redirect URI to the clipboard, register it **port-less**
    (`http://127.0.0.1/callback`) + bind a dynamic port so port mismatch is
    impossible, validate the pasted Client ID (`^[0-9a-f]{32}$`, trimmed, green
    check), then an immediate `/me` test call with human-readable diagnosis
    (non-Premium vs. wrong redirect URI).
- **Option B (DEFERRED — do NOT build yet): web-session capture.** The same
  extension would capture the live `open.spotify.com` Bearer token in-page.
  **DECISION (owner):** defer Option B and ship Option A only for now, because
  of extension-store-review risk and because the in-page capture is unverified
  (needs local testing). For now, a Free-tier / no-Premium user gets a clear
  "a Spotify Premium account is required right now; Free support is coming in a
  future update" message — NOT a broken flow and NOT a dead end. Revisit B after
  the web-token capture is tested locally. Keep the architecture open to it.
- Flow: Connect Spotify → detect Premium (`/me` `product`) → A wizard. No-Premium
  → the "Premium required for now" message (no B card yet).

### 4.3 Engine behaviour for a real 50k job
- **Shard destination playlists at 5,000 items** (YouTube's hard playlist cap).
  10k→2 playlists, 50k→≥10. The engine must create/name/track shards.
- **Incremental writes:** flush adds to YouTube in batches of 50–100 as matches
  accumulate — do NOT wait until all tracks are searched to write anything.
- **Real resumability:** persist the YT `playlist_id`(s) and the index of the
  last *added* track on the `migrations` row; on restart, reload tracks from the
  `tracks` table and skip matched/added ones. ("Resume" must actually resume —
  today it marks interrupted jobs failed.)
- **Throttling:** budget ~2 s/track with jitter (50k ≈ ~28 h — plan multi-day
  resumable, not "overnight"). Route BOTH ytmusicapi errors
  (`429`/`RESOURCE_EXHAUSTED`) and Spotify `429` (`Retry-After`,
  `reason: QUOTA_EXCEEDED`) through the existing `RateLimiter`. Replace the
  Data-API-style daily cap + silent 1-hour `sleep` with a visible
  "throttled until HH:MM" state. Persist rate counters to SQLite (survive
  restart). **Never bypass the rate limiter** — that is the ban vector.
- **Background survival:** closing the window with an active job hides to a
  tray/menubar icon instead of exiting; request OS sleep-inhibition during a job
  (Windows `SetThreadExecutionState`, macOS `caffeinate`, Linux `systemd-inhibit`).
- **Auth-failure handling:** a distinct auth exception from the searcher/migrator
  → `BackgroundWorker` sets `paused_auth` → `Notifier` → silent re-capture or
  one-click prompt → `set_client()` swaps the client → resume.
- **Select All means everything:** include **private playlists** (we already
  request the scope) and a synthetic **Liked Songs** playlist
  (`current_user_saved_tracks`). The current "public playlists only" filter is a
  bug against the goal.
- **Multi-playlist completion** must signal correctly (today completion math only
  works for a single playlist).

### 4.6 Owner decisions (locked — build to these)
- **Liked Songs:** a **toggle** controls whether Liked Songs is migrated as an
  ordinary destination playlist named "Liked Songs" (sharded like any other) or
  **skipped entirely**. Do NOT `rate_song` each track (that would halve
  throughput). Default: include it (toggle on).
- **Returning user with both accounts connected:** land on the **Connect screen
  first** (both shown connected, prominent Continue), for reassurance — not
  straight to Select.
- **Failed tracks:** **persist per-track failure detail** (track name + reason)
  in the DB so "View failed" and a saved report list the actual songs even after
  a resume/restart — not counts only.
- **Spotify Option B:** deferred (see §4.2). Ship Option A only for now.

### 4.4 Both GUI and CLI
- `MigrationManager` is the facade. Add a `--cli` entry point beside the Flet GUI
  sharing the same `~/.playlist_migrator/` state, auth, and resumable DB. Both
  front ends drive the same engine.

### 4.5 Distribution (owner tasks, but design for them)
- Windows: code-sign + build reputation (or ship via Store); macOS: Developer ID
  + **notarization**; Linux: AppImage/deb/Flatpak. Flet `build`/`pack` per OS.
  Extension published to all three stores with all extension IDs listed in the
  native-host manifest's `allowed_origins`/`allowed_extensions`.

## 5. What exists today (starting point — salvage only where it helps UX)

- **Engine is the strong part** and largely reusable: `TrackMatcher` (rapidfuzz,
  ~97.6% live match rate), `SpotifyFetcher`, `YouTubeSearcher`, `PlaylistMigrator`,
  `MigrationManager`, `CacheManager` (SQLite), `RateLimiter`, `BackgroundWorker`,
  Fernet `encryption`.
- **Prototype, incomplete:** `extension/` (MV3, localhost POST + typed pairing
  token — to be replaced by Native Messaging), `bridge/` (loopback HTTP demo —
  to be replaced), writes plaintext `headers.json` to repo root (must become
  encrypted under `~/.playlist_migrator/credentials/`).
- **Known gaps vs. goal (the punch list):** app and capture are two unconnected
  programs; typed pairing token; dev-mode-only extension; no 401/re-capture flow;
  "resume" marks jobs failed; writes only after full search; wrong daily cap +
  silent sleep; closing window kills job; multi-playlist completion broken; Google
  OAuth creds demanded but useless; Spotify needs secret (→ PKCE); private + Liked
  excluded; cookies stored in plaintext in repo root.
- **Flet is pinned to 0.28** and must stay there (0.8x reorganised the API).

## 6. INVARIANTS — breaking any of these is a defect

1. Develop on branch `prototype/extension-bridge`. Commit with clear messages.
   Never push elsewhere without explicit permission.
2. `flet` stays on the 0.28 line.
3. Every API call path goes through `RateLimiter`. No exceptions.
4. Runs locally on the user's machine; the owner hosts nothing and never
   custodies user credentials. No telemetry, no relay, no outbound call except to
   Spotify and YouTube Music.
5. Secrets/sessions are encrypted at rest (Fernet, under
   `~/.playlist_migrator/credentials/`). Nothing sensitive in the repo root.
6. Real tests live under `tests/`, run as `python -m pytest` from repo root. Do
   not extend the root scratch scripts.
7. No model identifier in any committed artifact (commit messages, code, docs).
8. Treat HANDOFF.md's "dead ends" as settled. Do not re-attempt them.
9. UX-first: when in doubt, remove a user step.

## 7. Context-loss review rubric (the orchestrator applies this to EVERY handback)

A deliverable is REJECTED and sent back if any of these is true:
- [ ] It re-introduces a step the user must do manually that §1/§4 removed
      (typed token, JSON edit, terminal command, DevTools).
- [ ] It re-opens a settled dead end (§3, HANDOFF.md).
- [ ] It violates an invariant (§6).
- [ ] It optimises code reuse/elegance at the cost of a user step (§1).
- [ ] It silently drops scope the goal requires (private playlists, Liked Songs,
      sharding at 5k, resume, background survival, throttling visibility).
- [ ] It assumes an API/limit without the evidence in this file or a fresh doc
      fetch (Spotify quota model, YT playlist cap, Native Messaging limits).
- [ ] It bypasses `RateLimiter` or custodies credentials off-machine.
- [ ] It is not wired into the single app the user runs (no "also run this
      second program" designs).

A deliverable is ACCEPTED only when it advances §1 without tripping the rubric,
has tests under `tests/` where code changed, and updates this file if it changed
a decision.
