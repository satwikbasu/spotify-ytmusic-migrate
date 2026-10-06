# UX FLOW — screen-by-screen spec for the seamless GUI (and its CLI twin)

> Implementation-ready, not code. Build against `docs/CONTEXT_CONTRACT.md` (§1 goal,
> §2 persona, §4 decisions, §6 invariants). Where this file names a
> `MigrationManager` call, that call exists today on
> `src/migrators/migration_manager.py` unless it is marked **NEW**. Anything marked
> **NEW** is a small facade addition the UI agent may request from the engine agent;
> it never requires the user to do anything extra.
>
> Hard rules for every screen (from §2 / §6): no typed tokens, no JSON edits, no
> DevTools, no terminal, no `.env` instructions, no "Google OAuth client" fields.
> Every error has a plain-language remedy with a button that performs it.

---

## 0. Vocabulary

| Term | Meaning |
|---|---|
| **Engine** | `MigrationManager` + `BackgroundWorker` + SQLite under `~/.playlist_migrator/`. Lives in the one app process the user runs. |
| **Extension** | The capture extension (Chrome / Edge / Firefox stores). Talks to the app via Native Messaging. Captures YouTube Music cookies (always) and, only when the user opts in, the Spotify web-session token (Option B). |
| **Connected as X** | A live identity check succeeded: Spotify `/me` (`display_name`, `product`), YouTube Music `get_account_info()` (channel/account name). A signed-out YT session returns `[]` silently, so identity is *always* checked via `get_account_info()`, never via "did a call return". |
| **Job** | One Spotify playlist → one row in `migrations`. Statuses: `queued`, `in_progress`, `paused_auth`, `completed`, `failed`. |
| **Batch** | The set of job ids returned by one `migrate_playlists()` call; read via `get_batch_progress(job_ids)`. |
| **Shard** | A destination YouTube Music playlist. A source playlist with > 5,000 tracks becomes `Name (1)`, `Name (2)`, … (`PlaylistMigrator._shard_name`). ≤ 5,000 keeps its own name. |

---

## 1. Full flow map

```
                 ┌──────────────────────────────────────────────┐
   app launch ──►│ S0  LAUNCH GATE (invisible)                   │
                 │  - engine.start()  (re-queues interrupted jobs)│
                 │  - load encrypted sessions, silent identity    │
                 │    checks for both services                    │
                 └──────┬───────────────────────┬────────────────┘
       no incomplete jobs │                     │ incomplete / paused_auth jobs exist
                          ▼                     ▼
                 ┌─────────────────┐   ┌─────────────────────────────┐
                 │ S1  CONNECT     │   │ S3  PROGRESS (resumed mode) │
                 │ Spotify ✓/✗     │   │ "Welcome back — picking up  │
                 │ YouTube Music ✓/✗│  │  where you left off"        │
                 └──────┬──────────┘   └─────────────────────────────┘
          both connected│
                        ▼
                 ┌─────────────────┐   Settings (gear icon, top-right,
                 │ S2  SELECT      │◄──  reachable from S1, S2, S4; never from S3
                 │ Everything /    │     while a job runs — see §6)
                 │ pick playlists  │
                 └──────┬──────────┘
            Start       │
                        ▼
                 ┌─────────────────┐
                 │ S3  PROGRESS    │──close window──► tray/menubar, keeps running
                 │ bars, banners,  │◄─"Show"──────────┘
                 │ pause / stop    │
                 └──────┬──────────┘
        batch all_done  │
                        ▼
                 ┌─────────────────┐
                 │ S4  RESULTS     │──"Migrate more"──► S2
                 └─────────────────┘
```

Transition conditions (the UI agent checks exactly these):

| From → To | Condition / engine call |
|---|---|
| S0 → S3 (resumed) | `engine.start()` re-queued ≥ 1 job, or `get_migration_status()['paused_auth_jobs'] > 0`. Job ids for the batch come from `get_all_jobs(status=...)` for `in_progress`, `queued`, `paused_auth` (see OPEN QUESTION 1). |
| S0 → S1 | Otherwise. Cards pre-populated from stored sessions: connected if the silent identity check passed. |
| S1 → S2 | Both cards in `connected` state. `app_state['spotify_client']`, `['youtube_client']` set. Button "Choose what to move" enabled. |
| S2 → S3 | ≥ 1 selectable playlist checked (or "Everything" on). `migrate_playlists(playlists, progress_callback)` → `job_ids`. |
| S3 → S4 | `get_batch_progress(job_ids)['all_done'] is True` (every job `completed` or `failed`). `paused_auth` or throttled is **not** done. |
| S3 → S2 | User confirms "Stop migration" → `cancel_all(force=True)`, `stop()`. |
| S4 → S2 | "Migrate more". |
| any → Settings | Gear icon. Returns to the screen it came from. Disabled while `is_migration_active`. |

Header: no "Step n of 5" counter (there are no five steps). Show a small three-dot
stepper **Connect · Choose · Move** on S1–S3 only.

---

## 2. S1 — CONNECT

**Title:** "Connect your two accounts"
**Subtitle:** "Spotify is where your music is now. YouTube Music is where it's going. Nothing leaves this computer."

Two cards, stacked. Below them one primary button, **"Choose what to move →"**, disabled until both cards are `connected`. No "Continue" wording.

### 2.1 Card states (shared by both cards)

| State | Status line | Button | Notes |
|---|---|---|---|
| `not_connected` | "Not connected" (muted) | **Connect Spotify** / **Connect YouTube Music** (primary) | |
| `connecting` | "Waiting for you in your browser…" + spinner | **Cancel** (text) | Spotify: waiting for the PKCE redirect. YT: waiting for the extension's Native Messaging reply. |
| `connected` | "✓ Connected as **{name}**" (+ "Premium" pill for Spotify) | **Disconnect** (text) | Name from `/me` or `get_account_info()`. |
| `error` | One-sentence problem + one-sentence remedy (see §7) | **Try again** (primary) + optional remedy button | Never shows a stack trace, HTTP code, or file path. |

Disconnect asks "Disconnect {service}? Your migration history stays." → deletes the encrypted session under `~/.playlist_migrator/credentials/` and returns the card to `not_connected`.

### 2.2 Spotify card — Option A is the default: "Connect Spotify" wizard (BYO Client ID + PKCE)

Clicking **Connect Spotify** opens a modal wizard inside the app (not a browser-only flow). It is a one-time chore; after success the Client ID is stored and the button becomes a true one-click login forever.

**Step A0 — Why (only on first run)**
- Heading: "One-time setup (about 2 minutes)"
- Body: "Spotify only lets apps talk to a handful of people each — so instead of sharing one app with everyone, you'll create your own private one. It's free, and nobody else can use it. You'll need Spotify Premium."
- Buttons: **Let's do it** (primary) · "I don't have Premium" (text → jumps to §2.3 Option B card, pre-explained) · Cancel.

**Step A1 — Open the dashboard**
- Heading: "1. Create your app on Spotify"
- The app **opens** `https://developer.spotify.com/dashboard/create` in the default browser when the step appears (`webbrowser.open`), and shows an **Open it again** button.
- Checklist in the app, mirroring the Spotify form, each with a copy button:
  - "App name — anything, e.g. `My Playlist Mover`" **[Copy]**
  - "Redirect URI — paste this exactly:" `http://127.0.0.1/callback` **[Copied ✓]** (pre-copied to the clipboard the moment the step appears; the pill says "Copied to clipboard — just paste it"). Port-less; the app binds a dynamic loopback port at login time so port mismatch is impossible.
  - "Which API/SDKs — tick **Web API**"
  - "Agree to the terms, click **Save**"
- Button: **Done — I created it →**

**Step A2 — Paste the Client ID**
- Heading: "2. Paste your Client ID"
- Body: "On your new app's page, click **Settings**. Copy the **Client ID** (a 32-character code) and paste it here. You do NOT need the Client Secret."
- Field: single `AppTextField`, label "Client ID", monospace, paste-friendly. Validation runs on every change after trimming whitespace: regex `^[0-9a-f]{32}$`.
  - Valid → green check, helper "Looks right", **Connect →** enabled.
  - Looks like a secret (32 hex but user pasted from the Secret row — we can't tell; so no special case) — see OPEN QUESTION 2.
  - Wrong length / characters → red helper: "That doesn't look like a Client ID — it should be exactly 32 letters and numbers. Make sure you copied **Client ID**, not the app name or the secret." **Connect** disabled.
- Button: **Connect →**

**Step A3 — Log in (browser) and test**
- Card state `connecting`; wizard body: "Spotify opened in your browser. Log in and click **Agree**. We'll finish here automatically."
- Engine: Authorization Code + PKCE with the stored Client ID, loopback listener on `127.0.0.1:<dynamic port>/callback`, scopes incl. private playlists + `user-library-read` (Liked Songs). On token receipt the app immediately calls `/me` through `RateLimiter`.
- `/me` diagnosis (all human-readable; the raw error goes to `app.log` only):

| `/me` result | Shown |
|---|---|
| 200, `product == "premium"` (or `premium_*`) | Wizard closes. Card → `connected`: "✓ Connected as **{display_name}** · Premium". Toast: "Spotify connected. Next time this is one click." |
| 200, `product` is `free`/`open` | Card `error`: "This Spotify account is on the Free plan. Spotify only lets Premium accounts use personal apps." Buttons: **Try a different account** · **Use the unofficial way instead** (→ §2.3) |
| Browser returned `INVALID_CLIENT: Invalid redirect URI` (or auth never arrives and the loopback saw a mismatch error) | Card `error`: "Spotify didn't accept the redirect address. In your app's Settings on the Spotify dashboard, the Redirect URI must be exactly `http://127.0.0.1/callback`." Buttons: **Copy address again** · **Open my app settings** · **Try again** |
| `invalid_client` (bad Client ID) | "Spotify doesn't recognise that Client ID. Check you copied the whole code from your app's Settings page." Button: **Fix Client ID** (back to A2, field pre-filled) |
| User closed the browser / 3-minute timeout | Card → `not_connected`; toast "Spotify login was cancelled. Click Connect Spotify to try again." |
| 403 "User not registered in the Developer Dashboard" (dev-mode user allow-list) | "Spotify says this account isn't allowed to use the app yet. Open your app's **User Management** page and add the email of the Spotify account you're logging into." Buttons: **Open User Management** · **Try again**. (Only possible if the dashboard account ≠ the listening account.) |
| Network failure | See §7 "Network down". |

Storage: Client ID is **not a secret** but is stored alongside the token in the Fernet-encrypted credentials file under `~/.playlist_migrator/credentials/`, never in the repo root or `.env`. Returning users never see A0–A2 again unless they choose "Use a different Spotify app" in Settings (§6).

### 2.3 Spotify card — Option B: "Unofficial" web-session capture (explicit opt-in fallback)

Shown as a **secondary card** *under* the Spotify card, collapsed by default, only when (a) the user clicked "I don't have Premium", (b) `/me` reported Free, or (c) the user cancelled/abandoned the wizard at A1/A2 (not A3). Header is always labeled:

> **Advanced · Unofficial** — "Connect through the Spotify web player instead"

Body copy (exact):
"This reads the login that Spotify's own web player is already using in your browser — the same way the extension connects YouTube Music. It works with Free accounts, but it isn't an official Spotify method: it can stop working without notice and may be against Spotify's terms. Use it only if the normal way isn't an option for you."

Checkbox: "I understand this is unofficial and could break." → enables **Connect via web player**.

Flow:
1. Requires the extension (same first-run gate as §2.4). If missing → §2.4 install state first.
2. The app opens `https://open.spotify.com` in the browser; copy in card: "Log in to Spotify in the tab that just opened. We'll finish here automatically." The extension observes the Bearer token the real web player mints **in-page** (never cookies + our own TOTP) and sends it through Native Messaging.
3. The app validates with `/me` (plain-language diagnosis as in A3 — Free is fine here). Card → `connected`: "✓ Connected as **{display_name}** · via web player (unofficial)" with an amber pill.
4. Token expiry mid-job reuses the same `paused_auth` → silent re-capture → one-click prompt path as YouTube (§4.3), labeled "Spotify" in the banner.

Never pre-select Option B. Never show it before Option A has been offered.

### 2.4 YouTube Music card — extension + one-click connect

**Normal state (extension installed, app paired):**
- Button **Connect YouTube Music** → the app opens `https://music.youtube.com` in the default browser (if no tab is open) and asks the extension over the Native Messaging port to read the cookies. Status: "Waiting for you in your browser… If you're already signed in to YouTube Music, this takes a second."
- Bridge builds the `ytmusicapi` headers (incl. `authorization: SAPISIDHASH` computed from `__Secure-3PAPISID`), verifies with `get_account_info()` via `RateLimiter`, encrypts the session under `~/.playlist_migrator/credentials/`, and the card → `connected`: "✓ Connected as **{account name}**".
- `get_account_info()` empty/`[]` or raises → card `error`: "You're not signed in to YouTube Music in your browser. Sign in there, then click Connect again." Buttons: **Open YouTube Music** · **Try again**.

**First-run state (extension not detected):** replaces the button area with an inline mini-wizard; the card title reads "YouTube Music — one-time setup (1 minute)".
- Copy: "YouTube Music doesn't offer a login for apps like this one, so we use a small browser extension to borrow the login you already have. It only reads your YouTube Music sign-in — nothing else — and sends it straight to this app on your computer."
- Detected browsers listed as buttons (whatever the installer registered the native-host manifest for; re-registered on each launch): **Add to Chrome** · **Add to Edge** · **Add to Firefox** · (Brave/other Chromium → "Add to Brave" opens the Chrome Web Store link). Safari: not shown; if Safari is the only browser, see §7 "No supported browser".
- After the store page opens: "Click **Add** in the store, then come back here. We'll notice automatically." The app polls the Native Messaging host for a first `hello`; on receipt the card flips to the normal state and auto-starts the connect (no second click).
- 2-minute timeout → stays in first-run state with "Still waiting for the extension… **Check again**" (text button).

**Re-capture while a job runs (wired to `reauthenticate_youtube`):**
- Trigger: `get_migration_status()['auth_required']` / `get_batch_progress()['auth_required']` true (jobs parked `paused_auth`), surfaced by `Notifier.notify_auth_required`.
- **Silent path** (browser open, extension port alive): the app asks the extension to re-read cookies with no UI at all; on success it builds a fresh client and calls `engine.reauthenticate_youtube(new_client)`. The Progress banner (§4.3) shows "Reconnected automatically" for 5 s, then clears. Zero clicks.
- **Prompt path** (browser closed / port dead / silent attempt returned signed-out): Progress banner + OS notification: "YouTube Music signed you out. Click **Reconnect** — it takes a second." The button opens `music.youtube.com` and runs the normal capture, then calls `reauthenticate_youtube`. Progress is saved; copy must say so ("Nothing is lost").

---

## 3. S2 — SELECT

**Title:** "What should we move?"
**Loading state:** full-card skeleton rows + "Reading your Spotify library…" (uses `SpotifyFetcher.get_user_playlists(use_cache=True)`, through `RateLimiter`).

### 3.1 The "Everything" switch (default position: ON for first-run users)
- Top of the list, large toggle row: **"Everything"** — subtitle: "All {N} playlists, including private ones, plus your Liked Songs ({M} songs). Total: {T:,} songs."
- When ON: every card below is checked and dimmed (not interactive); Start says **Start moving everything**.
- When OFF: cards become interactive; "Select all / none" text buttons appear; search field appears.

### 3.2 Playlist cards (`PlaylistCard`)
- Row 1 (pinned first): **Liked Songs** with a heart icon, subtitle "{M} songs · becomes a playlist called 'Liked Songs' on YouTube Music" (YT Music has no importable likes; see OPEN QUESTION 4).
- Each card: checkbox · cover · name · "{n} songs" · badges:
  - **Private** (lock icon) when `public == False`, **Collaborative** when collaborative.
  - **Will be split into K playlists** (amber, info icon) when `tracks_count > 5000`, K = ceil(n/5000). Tooltip/`i` sheet: "YouTube Music playlists hold at most 5,000 songs, so this one becomes 'Name (1)', 'Name (2)', …".
  - **Empty** (muted) when `tracks_count == 0`; checkbox disabled; excluded from "Everything".
  - **Already moved** (green check) when a `completed` job exists for this `playlist_id` — still selectable (re-migrating creates a new destination playlist; say so in the tooltip).
- Search filters by name; "Select all" applies to the filtered view.

### 3.3 Footer / Start button
- Summary line: "{P} playlists · {T:,} songs · about {estimate}" where estimate = T × ~2 s (jittered budget, contract §4.3) rendered as: < 1 h → "{m} minutes"; < 24 h → "{h} hours"; else "{d} days — it runs in the background and resumes if interrupted". Never alarmist; always followed by "You can close the window; we'll keep going."
- **Start** states:
  - **Disabled** — nothing selected, or library still loading, or every selected playlist is empty. Helper under button: "Pick at least one playlist".
  - **Enabled** — label **Start moving {P} playlist(s)** (or **Start moving everything**).
  - Large-run confirm (T > 10,000 **or** P > 50): sheet "This is a big library — roughly {estimate}. The app keeps working in the background and picks up where it left off if your computer restarts. Ready?" → **Start** / **Not yet**. Not a warning tone.
- On Start: `app_state['selected_playlists']` = chosen objects → S3, which calls `migrate_playlists()`.

Empty library: see §7 "No playlists".

---

## 4. S3 — PROGRESS

Fed by `get_batch_progress(job_ids)` + `get_migration_status()` on a 1 s poll (already in the screen) and the per-track `progress_callback` for the "right now" line. Totals and completion come **only** from the batch dict.

**Title:** "Moving your music" (resumed mode: "Welcome back — picking up where you left off").

### 4.1 Layout, top to bottom
1. **Overall bar** — `processed_tracks / total_tracks`, label "{done:,} of {total:,} songs · {pct}%". Under it: "{completed_jobs} of {total_jobs} playlists finished".
2. **Right now** — "{playlist_name}: *{track_name}*" from the callback; plus "Playlist {i} of {N}".
3. **Counters** — "Matched {matched_tracks:,}" (green) · "Couldn't find {failed_tracks:,}" (muted, not red — these are catalogue absences 97% of the time).
4. **Time** — "About {ETA} left" from measured rate; before 50 tracks: "Working out how long this will take…". If ETA > 12 h: "About {h} hours — this will keep running overnight and resume if interrupted." If > 48 h: "About {d} days. It's safe to leave this running or restart your computer — it resumes by itself."
5. **Per-playlist list** (collapsible, collapsed when N > 10) — one line per job from `batch['jobs']`: status chip (Waiting · Moving · Needs reconnect · Done · Stopped) · name · "{matched}/{total}" · "split into {len(youtube_playlist_ids)}" when > 1.
6. **Wait banner holder** (one at a time; priority auth > throttle > paused):

| Condition (engine) | Banner (type) | Action |
|---|---|---|
| `auth_required` (service = YouTube) | error: "YouTube Music signed you out — click Reconnect to continue. Your progress is saved; nothing is lost." | **Reconnect YouTube Music** → §2.4 re-capture → `reauthenticate_youtube` |
| `auth_required` (service = Spotify, Option B) | error: "Spotify signed you out — click Reconnect to continue. Nothing is lost." | **Reconnect Spotify** |
| silent re-capture just succeeded | success (5 s): "Reconnected automatically." | — |
| `throttle.throttled`, reason `rate` | warning: "Taking a short break until **{HH:MM}** — YouTube Music asked us to slow down. This is normal; it continues by itself." | — |
| `throttle.throttled`, reason `quota` | warning: "Daily limit reached — continuing at **{HH:MM}** (midnight). The app keeps running; you don't need to do anything." | — |
| `is_paused` | info: "Paused. Click Resume when you're ready." | **Resume** |

The ETA line reads "Waiting for you to reconnect" / "Paused" / "Resuming at {HH:MM}" while a banner is up.

7. **Background note** (always visible, info): "You can close this window — the migration keeps running in the background and we'll notify you when it's done."
8. **Buttons** — **Pause** / **Resume** (`pause_migrations()` / `resume_migrations()`; pause takes effect after the current playlist — say so: "Pausing after this playlist…") and **Stop** (text, destructive).

### 4.2 Stop (cancel) dialog — never says "all progress will be lost" (it isn't)
"Stop moving music? Playlists already finished stay on YouTube Music. Anything half-finished stays half-finished — you can run it again later and the finished songs won't be duplicated."
Buttons: **Stop** (destructive) · **Keep going**. Confirm → `cancel_all(force=True)`, `stop()`, → S2.

### 4.3 Closing the window / tray behaviour (`main.py`)
- Close with active job → window hides to tray/menubar (`pystray`), or minimizes when no tray. First time only, a non-modal toast: "Still running in the background. Find me in the system tray." Tray menu: **Show** · **Quit (stops migration)**.
- OS notifications (`Notifier`): batch started, each playlist done (muted after 5 when N > 10), reconnect needed, throttled > 15 min, batch complete.
- Sleep inhibition is on while a job is active; the app never asks the user to change power settings. If inhibition is unavailable (Linux without systemd), show once in the background note: "Tip: keep your computer from sleeping while this runs."

### 4.4 Completion
When `all_done`: hold the 100% state ~2 s, then → S4 with `build_results(batch)`.

---

## 5. S4 — RESULTS

**Title:** "Done!" (all jobs `completed`) · "Done, with a few gaps" (some tracks failed) · "Finished, but {k} playlist(s) stopped early" (some jobs `failed`).

**Summary card**
- "{total_jobs} playlists moved · {matched:,} of {total:,} songs ({pct}%)"
- When `playlists_created != total_jobs`: "Created {playlists_created} YouTube Music playlists — large playlists were split into parts of up to 5,000 songs."
- "{failed_tracks:,} songs couldn't be found on YouTube Music" — helper: "Usually these simply aren't in YouTube Music's catalogue."
- "Took {duration}" (and, if resumed, "across {sessions} sessions" — OPEN QUESTION 5).

**Per-playlist list** — name · "{matched}/{total}" · "split into K" · "stopped early: {plain error}" for `failed` jobs · **Open on YouTube Music** (first shard; a split playlist shows a small "(1) (2) (3)" link row).

**Next actions**
- **Open YouTube Music** (primary) → `https://music.youtube.com/library/playlists`
- **Save a report** → CSV via file picker (today's `_export_csv_report`; see OPEN QUESTION 6 on missing per-track rows)
- **Retry the {k} that stopped early** (only when `failed_jobs > 0`) → S3 with those playlists; the engine skips already-added tracks.
- **Migrate more playlists** → S2.

---

## 6. SETTINGS (gear icon; non-technical surface only)

Remove entirely: Google/YouTube OAuth client ID/secret fields, "Rate limit delay", "Daily operation limit", the `settings.json` "Save" button model (settings apply on change), the placeholder GitHub links. Nothing here may refer to `.env`, `headers.json`, or environment variables.

| Section | Control | Copy / behaviour |
|---|---|---|
| **Accounts** | Spotify row: "Connected as {name} · Premium / via web player (unofficial)" · **Disconnect** · **Use a different Spotify app…** (re-opens wizard A1 with the current Client ID shown read-only + "Copy", and a field to replace it) | Client ID lives in the encrypted credentials store; this is the only place it's visible. |
| | YouTube Music row: "Connected as {name}" · **Disconnect** · **Reconnect** (runs capture) · extension status line "Extension: connected in Chrome, Firefox" / "not detected — **Install**" | |
| **Matching** | Slider "How strict should song matching be?" 60–95, default 75 (`DEFAULT_MATCH_THRESHOLD`), labels **Looser** ⟷ **Stricter**; helper: "Stricter means fewer wrong songs but more gaps. 75 is right for almost everyone." Reset link. | Applied to the next migration started. |
| **Notifications** | Switch "Tell me when a migration finishes or needs me" (default on) | `Notifier` |
| **Appearance** | Light / Dark / Match system | |
| **Storage** | "History and cache: {size}" · **Clear cache** (match cache only; keeps history) · **Delete everything and start over** (double-confirm; clears credentials, history, cache) | Copy for delete: "This removes your saved logins, history and settings from this computer. Your playlists on Spotify and YouTube Music are not touched." |
| **About** | App name, version, "Everything runs on this computer. Nothing is sent anywhere except Spotify and YouTube Music." · **Open log folder** (for support — opens `~/.playlist_migrator/` in the file manager, never asks the user to read it) | |

Settings is unreachable from S3 while a job runs (gear disabled, tooltip "Finish or stop the migration first").

---

## 7. ERROR & EMPTY STATES CATALOG

Every message: ≤ 2 sentences, no codes, no paths, a button that does the remedy. Raw detail → `app.log` only.

| # | Where | Trigger (engine/detection) | Message | Remedy button(s) |
|---|---|---|---|---|
| E1 | S1 Spotify | `/me product` not premium | "This Spotify account is on the Free plan. Spotify only lets Premium accounts use personal apps." | **Try a different account** · **Use the unofficial way instead** |
| E2 | S1 Spotify | `INVALID_CLIENT: Invalid redirect URI` | "Spotify didn't accept the redirect address. In your app's Settings it must be exactly `http://127.0.0.1/callback`." | **Copy address** · **Open my app settings** · **Try again** |
| E3 | S1 Spotify | regex fail on Client ID | "That doesn't look like a Client ID — it should be exactly 32 letters and numbers." | (inline, Connect disabled) |
| E4 | S1 Spotify | `invalid_client` | "Spotify doesn't recognise that Client ID. Check you copied the whole code from your app's Settings page." | **Fix Client ID** |
| E5 | S1 Spotify | 403 user not in allow-list | "Spotify says this account isn't allowed to use the app yet. Add this account's email on your app's User Management page." | **Open User Management** · **Try again** |
| E6 | S1 Spotify | timeout / browser closed | "Spotify login was cancelled." | **Connect Spotify** |
| E7 | S1 YT | extension not detected (no NM hello) | "To connect YouTube Music you need our small browser extension — a one-minute, one-click install." | **Add to Chrome / Edge / Firefox** |
| E8 | S1 YT | no supported browser found | "We couldn't find Chrome, Edge, Brave or Firefox on this computer. Install one of them to connect YouTube Music (Safari isn't supported yet)." | **Get Chrome** · **Check again** |
| E9 | S1 YT / S3 | `get_account_info()` empty or raises | "You're not signed in to YouTube Music in your browser. Sign in there, then click Connect." | **Open YouTube Music** · **Try again** |
| E10 | S1 YT | extension installed but native host unreachable (manifest missing) | "The extension can't reach this app. Restarting the app usually fixes it." | **Restart app** (re-registers manifests on launch) |
| E11 | S3 | `auth_required` (YT) | "YouTube Music signed you out — click Reconnect to continue. Nothing is lost." | **Reconnect YouTube Music** |
| E12 | S3 | `auth_required` (Spotify, Option B) | "Spotify signed you out — click Reconnect to continue. Nothing is lost." | **Reconnect Spotify** |
| E13 | S3 | `throttle.reason == 'rate'` | "Taking a short break until {HH:MM} — YouTube Music asked us to slow down. This is normal." | — |
| E14 | S3 | `throttle.reason == 'quota'` (Spotify `QUOTA_EXCEEDED` or daily cap) | "Daily limit reached — continuing at {HH:MM}. You don't need to do anything." | — |
| E15 | S2 | zero playlists and zero liked songs | "Your Spotify library looks empty — no playlists or liked songs. Add some music on Spotify, then come back." | **Refresh** · **Open Spotify** |
| E16 | S2 | playlists exist, all empty | "All your playlists are empty, so there's nothing to move yet." | **Refresh** |
| E17 | S2 | search no match | "No playlists match '{q}'." | **Clear search** |
| E18 | any | network down (DNS/connection error from either client) | "Can't reach the internet right now. We'll keep trying — nothing is lost." (S3: banner, engine retries via `RateLimiter` backoff) / (S1/S2: inline with **Try again**) | **Try again** |
| E19 | S3 | a job `failed` (non-auth, non-throttle) | Per-playlist line: "Stopped early — {plain reason}. You can retry it from the results page." | **Retry** on S4 |
| E20 | S4 | `failed_tracks > 0` | "{n} songs couldn't be found on YouTube Music — usually they just aren't in its catalogue." | **Save a report** |
| E21 | S0 | credentials file unreadable / decryption fails | Card shows `not_connected` silently with toast "Please connect {service} again." | **Connect** |
| E22 | S2/S3 | Spotify `playlist_items` 403 on a specific playlist (e.g. editorial list no longer readable) | Line: "Spotify won't let us read this playlist. Skipped." | — |

Empty **first-run** state of S1 is not an error: both cards `not_connected`, headline as in §2.

---

## 8. FIRST-RUN vs RETURNING

| | Brand-new user | Returning, nothing in flight | Returning, job interrupted (crash/restart/sleep) | Returning, job parked `paused_auth` |
|---|---|---|---|---|
| S0 | `start()` finds nothing; no stored sessions | Stored sessions decrypt; silent `/me` + `get_account_info()` | `start()` re-queues `in_progress`/`queued` rows → they continue from last written track | `start()` leaves them parked; `auth_required` true |
| Lands on | S1 with both cards `not_connected`; Spotify wizard A0 explains the one-time chore; YT shows first-run install state if extension absent | S1 with both cards `connected` (one click: "Choose what to move") — or straight to S2 (OPEN QUESTION 3) | S3 resumed mode: "Welcome back — picking up where you left off", bar already partly filled from job rows | S3 resumed mode with E11 banner immediately: "Reconnect YouTube Music to continue" |
| Needs clicks | Install extension (1), Spotify wizard (≈4), Connect YT (1), Select (1–2), Start (1) | 2 (Choose, Start) | 0 | 1 (Reconnect) |
| Copy differences | "one-time setup" phrasing everywhere | none | Time line says "Resumed — {done} songs were already moved" | Same + banner |

Sessions that fail the silent identity check at S0 land on S1 with that card `not_connected` and a gentle toast (E21) — never an error dialog on launch.

---

## 9. CLI PARITY (`--cli`, contract §4.4)

Same engine, same `~/.playlist_migrator/` state, same encrypted credentials. The CLI is for the owner and power users; it is **not** the non-technical path and must not become a prerequisite for the GUI. Mapping:

| GUI screen | CLI |
|---|---|
| S1 Connect Spotify (A) | `app --cli connect spotify` → prints the same wizard steps as text, opens dashboard, copies redirect URI, prompts for Client ID (validated with the same regex), runs PKCE, prints `/me` diagnosis (E1–E6 text). |
| S1 Option B | `connect spotify --web-session` (prints the same unofficial disclaimer; requires `--i-understand`). |
| S1 Connect YT | `connect youtube` → opens music.youtube.com, waits on the Native Messaging port, prints "Connected as {name}" or E7–E10 text. |
| S2 | `migrate --all` (Everything) · `migrate --list` (prints table with Private / Liked / "splits into K" columns) · `migrate --playlist <id|name>…` |
| S3 | Live single-line progress (`processed/total`, ETA) from `get_batch_progress`; banners become lines: `[waiting] throttled until HH:MM`, `[action needed] YouTube Music signed you out — run: app --cli reconnect youtube` (or silent re-capture if the browser is open). `Ctrl-C` = pause-and-exit (job rows stay resumable); `--daemon` keeps running after the terminal closes. |
| Resume | `app --cli resume` (= `start()`; prints what was re-queued) |
| S4 | Summary table + `--report out.csv` |
| Settings | `config threshold 75`, `config notifications off`, `disconnect spotify|youtube`, `reset --everything` |

The CLI never prints tokens, cookies or headers; same no-secret-in-terminal rule as the GUI.

---

## 10. Invariant & rubric self-check (contract §6 / §7)

- No typed token, JSON edit, DevTools or terminal step anywhere in S0–S4 or Settings (the only paste is a non-secret Client ID into a validated field; the redirect URI is pasted *into Spotify's form*, pre-copied for the user). ✓
- YouTube Music: extension + Native Messaging only; no OAuth, no "without extension" path; Safari deferred. ✓
- Spotify: Option A default with the low-friction wizard; Option B explicit, labeled, opt-in, after A. ✓
- Scope kept: private playlists, Liked Songs, shard at 5k with split messaging, real resume on relaunch, background/tray survival, visible throttle state. ✓
- Every call path named goes through `RateLimiter` (the UI only calls the facade). ✓
- Settings drops the dead Google OAuth fields and anything `.env`-shaped. ✓
- Local-only, encrypted at rest under `~/.playlist_migrator/credentials/`. ✓
- Single app; the extension is a store install, not a "second program to run". ✓

---

## 11. OPEN QUESTIONS (decide; do not invent)

1. **Resumed-batch job ids.** `start()` re-queues interrupted jobs but returns nothing to the UI, and `migrate_playlists()` is not called on resume. The Progress screen needs the id list for `get_batch_progress`. Proposal: **NEW** `MigrationManager.get_active_job_ids()` (= rows with status in `queued`/`in_progress`/`paused_auth`), or make `start()` return the resumed ids. Engine owner to pick.
2. **Client ID vs Client Secret confusion.** Both are 32 hex chars; the regex cannot distinguish them. Mitigation in copy ("you do NOT need the secret") plus E4 on `invalid_client`. Should the wizard additionally show a screenshot/illustration of the Settings page? (Asset needed.)
3. **Returning user with both accounts connected:** land on S1 (one extra click, shows identities for reassurance) or skip to S2 with a compact "Connected as … / …" header? Spec assumes S1; UX-first rule suggests S2.
4. **Liked Songs destination.** YouTube Music "liked" is a separate concept with no bulk-like API in ytmusicapi that we trust at 50k scale. Spec puts Liked Songs into a normal playlist named "Liked Songs" (sharded if > 5k). Confirm, or investigate `rate_song` per track (another API call per track → halves throughput).
5. **Duration across sessions.** `start_time` is per process; a resumed job's "Took {duration}" is wrong. Needs `created_at`/`completed_at` on the job row (likely exists in `migrations`) surfaced via `get_batch_progress`.
6. **Per-track report rows.** `build_results` notes per-track failure detail is not persisted, so "Save a report" and "View failed" are count-only after resume. Persist failed track titles on the `tracks` table (status column) or drop the per-track report promise.
7. **Option B visibility trigger.** Show the unofficial card only after a Free diagnosis / explicit "I don't have Premium" (spec), or also after a plain cancel at A1/A2? Spec says yes to the latter; owner may prefer stricter gating for ToS risk.
8. **Store review risk** (HANDOFF open item) could force the extension to be "cookies only" with no Spotify in-page observer; if so Option B is GUI-impossible and E1 loses its second button. Decide before building the Option B card.
9. **Progress-screen Settings access**: spec disables the gear during a job to avoid threshold/account changes mid-run. Acceptable, or allow read-only?
