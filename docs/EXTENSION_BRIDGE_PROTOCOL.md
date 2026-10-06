# EXTENSION ↔ APP BRIDGE PROTOCOL — Native Messaging capture of the YouTube Music session

> Implementation-ready contract for the capture extension and the desktop app.
> Build against `docs/CONTEXT_CONTRACT.md` (§4.1 capture architecture, §4.3
> auth-failure handling, §6 invariants) and `docs/UX_FLOW.md` §2.4 / §4.1 / §7
> (E7–E11). It **replaces** the prototype in `extension/` + `bridge/` (loopback
> HTTP on 127.0.0.1:8765 + typed pairing token). Everything the prototype got
> right is kept: `chrome.cookies` capture, `bridge/session.py::build_headers`,
> validation with `get_account_info()`, and the engine seam
> `MigrationManager.reauthenticate_youtube()`.
>
> Settled facts this spec does not re-litigate (HANDOFF.md): no YouTube OAuth;
> no embedded/automated browser login; no reading another browser's cookie jar
> from the app; a web page cannot reach loopback (Private Network Access) but an
> extension can; the extension is mandatory. A signed-out ytmusicapi session
> returns `[]` instead of raising, so identity is **only** confirmed with
> `get_account_info()`.

---

## 0. Vocabulary

| Term | Meaning |
|---|---|
| **Extension** | The MV3 capture extension installed from the Chrome Web Store / Edge Add-ons / Firefox AMO. Reads `music.youtube.com` cookies. The only code that runs inside the browser. |
| **Host** | The Native Messaging host: a short-lived process the *browser* spawns (`runtime.connectNative`). Talks to the browser over stdin/stdout, and to the App over a local IPC connection. It is the **same executable as the App**, started with `--native-host` (see §5.1) — never a second program the user runs. |
| **App** | The resident Flet desktop process (`main.py`) that owns the engine (`MigrationManager`, `BackgroundWorker`, SQLite). It runs a local IPC listener (`CaptureHub`, §2.4) that Hosts connect to. |
| **Port** | One `connectNative` connection = one Host process = one IPC connection to the App. Lives as long as the extension's background context keeps it open. |
| **Capture** | One cookie set read via `cookies.getAll` for `music.youtube.com`, converted by `build_headers()` into a ytmusicapi headers dict, validated by `get_account_info()`. |
| **Session store** | The Fernet-encrypted file `~/.playlist_migrator/credentials/youtube_session.enc` holding the latest validated headers dict (replaces `headers.json` in the repo root). |

---

## 1. Architecture

### 1.1 Components and message flow

```
 BROWSER (user's real Chrome/Edge/Brave/Firefox, user already signed in)
 ┌──────────────────────────────────────────────────────────────────┐
 │  Extension (MV3, store-installed)                                 │
 │   background.js                                                   │
 │    • runtime.connectNative("com.playlist_migrator.capture")       │
 │    • cookies.getAll({url:"https://music.youtube.com"})            │
 │    • cookies.onChanged (domain endsWith "youtube.com") → debounce │
 │   popup.html — status only (Connected / App not running / …)      │
 └───────────────┬───────────────────────────────────────────────────┘
                 │ Native Messaging: stdin/stdout, 4-byte LE length + UTF-8 JSON
                 │ (host→browser message ≤ 1 MB)
 ┌───────────────▼───────────────────────────────────────────────────┐
 │  Host  = <app executable> --native-host   (spawned BY the browser) │
 │   src/bridge/native_host.py                                        │
 │    • frames/deframes stdio                                          │
 │    • connects to App IPC endpoint (authkey from a 0600 file)       │
 │    • pure relay + liveness; holds NO cookies beyond relaying,       │
 │      never touches the network, never writes files                 │
 └───────────────┬───────────────────────────────────────────────────┘
                 │ IPC: multiprocessing.connection (AF_UNIX socket on macOS/Linux,
                 │      AF_PIPE named pipe on Windows), HMAC challenge w/ authkey,
                 │      JSON via send_bytes/recv_bytes ONLY (never pickle)
 ┌───────────────▼───────────────────────────────────────────────────┐
 │  App (resident; the one program the user runs)                     │
 │   src/bridge/capture_hub.py   CaptureHub (Listener thread)         │
 │    • registry of live Ports (browser, extension id, last seen)     │
 │    • build_headers() → YTMusic(auth=headers)                       │
 │    • identity check: get_account_info() THROUGH RateLimiter        │
 │    • encrypt → ~/.playlist_migrator/credentials/youtube_session.enc│
 │    • MigrationManager.reauthenticate_youtube(new_client)           │
 │    • events → Welcome screen card / Progress banner / Notifier     │
 │   src/bridge/host_registry.py — writes native-host manifests       │
 │     for every detected browser on EVERY launch                     │
 └────────────────────────────────────────────────────────────────────┘
```

### 1.2 Why this shape (CONTEXT_CONTRACT §4.1)

| Prototype problem | Native Messaging answer |
|---|---|
| User must copy a pairing token from the app window into the popup (typed token — forbidden by §2/§6.9). | The browser itself authenticates the two ends: it only spawns the Host for extension IDs listed in the host manifest, and the Host is only reachable through that manifest. Nothing for the user to type. |
| `Access-Control-Allow-Origin: *` on a loopback HTTP server; any local page or process could probe `127.0.0.1:8765`. | No HTTP, no port, no CORS. The IPC endpoint is a filesystem-permissioned socket/pipe plus an HMAC challenge keyed by a 0600 file (§2.4). |
| Fixed port 8765 can collide / be firewalled; Windows Firewall prompts. | No listening TCP socket at all. |
| Extension needed a `http://127.0.0.1:8765/*` host permission (store-review red flag). | Permissions shrink to `cookies`, `nativeMessaging`, (`alarms`) + host permission for `https://music.youtube.com/*` (§7). |
| Capture only when the user clicks the popup; no way for the engine to ask for fresh cookies. | A long-lived port is bidirectional: the engine can *request* a re-read, and the extension can *push* refreshed cookies on `cookies.onChanged` (§4). |
| Plaintext `headers.json` in the repo root. | Encrypted session store under `~/.playlist_migrator/credentials/` (invariant §6.5). |

The Host is deliberately dumb. All policy (validation, storage, engine calls, UI) lives in the App, which is the only process that has the engine, the `RateLimiter`, and the Fernet key.

---

## 2. Message protocol

### 2.1 Framing

**Browser ↔ Host (Native Messaging, both Chromium and Firefox):** each message is a 32-bit unsigned length in *native byte order* (little-endian on every supported desktop platform) followed by that many bytes of UTF-8 JSON. The host reads stdin in a loop until EOF (EOF = port disconnected). **Host → browser messages are limited to 1 MB**; browser → host messages may be up to 4 GB in Chromium (1 MB is the number to design for in both directions — our largest message, a cookie set, is a few KB). The Host must write **nothing else** to stdout; logging goes to stderr (the browser discards it) and to `~/.playlist_migrator/app.log` via the shared logger.

**Host ↔ App (IPC):** `multiprocessing.connection` byte messages (`send_bytes` / `recv_bytes`). Each is one UTF-8 JSON document. Pickle (`send`/`recv`) is **forbidden** on this channel. Max accepted message: 1 MB; anything larger is dropped and the connection closed.

All messages are JSON objects with a required `type` field and a required `v` (protocol version, integer, currently `1`). Unknown `type` → reply `error` with `code: "unknown_type"`; unknown fields are ignored (forward compatibility).

### 2.2 Extension → Host (relayed to App unchanged, with envelope — §2.5)

| `type` | Fields | When |
|---|---|---|
| `hello` | `v: 1`, `extension_id: str` (runtime.id), `extension_version: str`, `browser: "chrome"\|"edge"\|"brave"\|"chromium"\|"firefox"\|"unknown"` (best effort from `navigator.userAgentData.brands` / UA), `capabilities: ["cookies","onchanged"]` | First message after `connectNative`. Must arrive within 5 s or the Host closes the port. |
| `cookies` | `v`, `request_id: str\|null` (echo of the `capture_request` that caused it; `null` for a push), `reason: "request"\|"changed"\|"startup"`, `captured_at: int` (ms epoch), `cookies: [{name, value, domain, path, secure, httpOnly, expirationDate?}]` | Result of a capture. Full set for `https://music.youtube.com` (§3.1); never a diff. |
| `signed_out` | `v`, `request_id`, `reason` | Capture ran but no `__Secure-3PAPISID` cookie (or none with `domain` ending `.youtube.com`). The extension never sends a cookie set it already knows is useless. |
| `error` | `v`, `request_id?`, `code: "cookies_denied"\|"internal"`, `message: str` (no cookie values ever) | Extension-side failure. |
| `ping` | `v`, `t: int` | Every 25 s while connected (keeps the MV3 service worker's activity visible; see §4.4). Host answers `pong` itself without involving the App. |

### 2.3 Host → Extension (originating from the App unless noted)

| `type` | Fields | When |
|---|---|---|
| `hello_ack` | `v`, `app_version: str`, `app_connected: bool`, `port_id: str` (uuid4 assigned by the App) | Reply to `hello`. `app_connected: false` is sent **by the Host alone** when the App's IPC endpoint is unreachable (App not running) — then the Host also sends `app_unavailable` and exits 0. |
| `app_unavailable` | `v`, `retry_after_s: 60` | App not running. Extension shows "Open the app" in the popup and retries `connectNative` on an alarm (§4.4). |
| `capture_request` | `v`, `request_id: str` (uuid4), `purpose: "connect"\|"reauth"\|"verify"` | App wants a fresh read. Extension answers `cookies` or `signed_out` with the same `request_id`. |
| `identity_confirmed` | `v`, `request_id`, `account_name: str` | App validated the capture with `get_account_info()`. Popup shows "Connected as {name}". |
| `identity_failed` | `v`, `request_id`, `code: "signed_out"\|"rejected"\|"network"\|"rate_limited"`, `retry_after_s?: int` | Validation failed. Popup copy per code (§6.4). |
| `pong` | `v`, `t` | Host-local reply to `ping`. |
| `error` | `v`, `request_id?`, `code`, `message` | Protocol errors (`bad_frame`, `too_large`, `unknown_type`, `ipc_lost`). |
| `bye` | `v`, `reason: "app_quit"\|"replaced"` | App is shutting down or a newer App instance took over the endpoint. The extension drops the port and goes to the §4.4 reconnect loop. |

### 2.4 Host ↔ App IPC endpoint and how it is secured without a typed token

**Endpoint** (owned by the App, created by `CaptureHub.start()` on App launch, torn down on quit):

| OS | Address | Protection |
|---|---|---|
| macOS / Linux | `AF_UNIX` socket `~/.playlist_migrator/run/capture.sock` | `run/` created `0700`; socket `0600`; stale socket file removed on start. |
| Windows | `AF_PIPE` named pipe `\\.\pipe\playlist_migrator-capture-<hex(sha256(user_sid_or_username))[:16]>` | Per-user pipe name; HMAC challenge below is the actual gate. |

**Authkey:** `CaptureHub.start()` generates 32 random bytes (`secrets.token_bytes(32)`) and writes them to `~/.playlist_migrator/run/capture.key` with mode `0600` (on Windows, `run/` and the file are created with an ACL granting only the current user — use `icacls`-equivalent via `ctypes`/`win32security`, or at minimum rely on `%USERPROFILE%` default inheritance which already excludes other non-admin users). `multiprocessing.connection.Listener(address, authkey=key)` then performs its built-in **HMAC-SHA256 challenge/response** on every accepted connection; a client that cannot read the key file cannot complete the handshake. The key is regenerated on every App start, so it never outlives the process that minted it.

**Why this is not "a token":** the user never sees, copies or types it. The two ends are the same OS user on the same machine, and the OS already enforces that boundary (file mode / ACL). This satisfies §2 (no typed token) and §6.4 (local-only).

**Endpoint discovery by the Host:** the Host reads `~/.playlist_migrator/run/capture.json` (`{"v":1,"address":"...","pid":<app pid>,"app_version":"..."}`, mode 0600). If the file is missing, the pid is dead, or the connect/handshake fails within 2 s → `app_unavailable`.

**Single App instance:** if a second App instance starts, it must detect the live `capture.json` pid and either exit (hand focus to the first) or take over the endpoint after the first has quit. Takeover sends `bye reason:"replaced"` to all ports first. (Related: the tray/background-survival work in UX_FLOW §4.3 already needs a single-instance guard; share it.)

### 2.5 Host → App envelope and App → Host commands

Everything from the extension is relayed to the App wrapped as:

```json
{"v":1,"type":"from_extension","port_id":"<uuid4>","browser":"chrome",
 "extension_id":"<id>","payload":{ ...the extension message verbatim... }}
```

Plus Host-originated lifecycle messages: `{"type":"port_opened", "port_id", "argv": [...]}` (first thing after IPC handshake; `argv` is what the browser passed — Chromium passes the extension origin, Firefox passes the manifest path and extension id — used only for logging/registry), `{"type":"port_closed","port_id","reason":"eof"|"bad_frame"|"too_large"}`.

App → Host: `{"v":1,"type":"to_extension","payload":{...}}` (relayed verbatim to stdout) and `{"type":"close","reason":"app_quit"|"replaced"}` (Host sends `bye` and exits 0).

`port_id` is minted by the App on `port_opened` and returned in the reply so the Host can stamp it into `hello_ack`.

### 2.6 Sequence: first connect

```
Ext                     Host                         App (CaptureHub)                  UI
 │ connectNative ──────► spawn                           │                              │
 │                        │── IPC connect+HMAC ─────────►│                              │
 │                        │── port_opened ──────────────►│ registry += port             │
 │ hello ────────────────►│── from_extension(hello) ────►│ mark browser/ext            │─► E7 state clears,
 │◄──────── hello_ack ────│◄── to_extension(hello_ack) ──│                              │   card → normal
 │                        │                              │◄── user clicks Connect ──────│
 │◄──── capture_request ──│◄── to_extension(cap_req) ────│  (or auto-start after hello) │
 │ cookies ──────────────►│── from_extension(cookies) ──►│ build_headers → YTMusic      │
 │                        │                              │ RateLimiter.wait; get_account_info()
 │                        │                              │ ok → encrypt session store   │
 │◄── identity_confirmed ─│◄── to_extension(...) ────────│ app_state['youtube_client']  │─► "Connected as X"
```

---

## 3. Cookie capture

### 3.1 What the extension reads

`chrome.cookies.getAll({ url: "https://music.youtube.com" })` (Firefox: `browser.cookies.getAll`). This returns every cookie that would be sent on a request to that URL — including **httpOnly** cookies, which `document.cookie` cannot see — because the extension holds `cookies` plus the `https://music.youtube.com/*` host permission. Send the full returned list; do not whitelist in the extension (Google renames/adds cookies; the App decides). The App only *requires*:

| Cookie | Role | httpOnly (typical) |
|---|---|---|
| `__Secure-3PAPISID` | Source of `authorization: SAPISIDHASH <ts>_<sha1(ts + " " + sapisid + " " + origin)>`, computed per client by `ytmusicapi.helpers.get_authorization` in `build_headers`. **Required**; absent ⇒ signed out. | no |
| `SAPISID`, `APISID`, `__Secure-1PAPISID` | Same family; ytmusicapi falls back through them. | no |
| `SID`, `HSID`, `SSID`, `__Secure-1PSID`, `__Secure-3PSID` | Session identity. | HSID/SSID/`__Secure-*PSID` yes |
| `__Secure-1PSIDTS`, `__Secure-3PSIDTS`, `SIDCC`, `__Secure-1PSIDCC`, `__Secure-3PSIDCC` | **Rotating** session tokens — these are what change over a multi-hour job and what makes a stored cookie set go stale (the §4 trigger). | yes |
| `LOGIN_INFO` | YouTube login state. | yes |
| `VISITOR_INFO1_LIVE`, `YSC`, `PREF`, `SOCS`, `CONSENT` | Visitor/consent context; harmless to include, keeps requests looking like the browser's. | mixed |

Partitioned (CHIPS) cookies: pass `partitionKey: {}`? **No** — the top-level `music.youtube.com` context is unpartitioned; a `getAll` without `partitionKey` returns unpartitioned cookies, which is what a first-party request uses. Flag for local verification (§8).

### 3.2 Cookies → headers (reuse)

`bridge/session.py::build_headers(cookies)` moves to `src/bridge/session.py` unchanged in behaviour (3 tests in `tests/test_bridge_session.py` move with it). It joins `name=value` pairs into one `cookie` header, computes `authorization` via ytmusicapi's own helper, and sets `origin`/`x-origin` to `https://music.youtube.com`. One addition: `build_headers` must accept the extension's richer cookie objects (extra keys ignored) and must **sort cookies by name** before joining so two captures of the same set hash identically (§4.2 dedupe).

**Client construction:** `YTMusic(auth=headers_dict)` — ytmusicapi accepts the dict directly; no temp file, nothing on disk in plaintext. The `user-agent` in `build_headers` should be replaced by the browser's real UA when the extension supplies it (`hello.user_agent`, optional field) so the session's fingerprint matches the cookies' issuer; fall back to the current constant.

### 3.3 Identity confirmation (mandatory; the signed-out trap)

A cookie set with `__Secure-3PAPISID` present can still be stale (rotated PSIDTS) or signed out. ytmusicapi does **not** raise on a signed-out browser session: `get_library_playlists()` returns `[]`. Therefore:

1. `RateLimiter.wait_if_needed()` (same instance as the engine's — one budget).
2. `account = client.get_account_info()`.
3. Success ⇔ no exception **and** `account` is a non-empty dict with `accountName` (or `channelHandle`). Anything else is `identity_failed code:"signed_out"`.
4. `is_auth_error(exc)` (`src/utils/errors.py`) → `signed_out`; HTTP 429 → `rate_limited` with `retry_after_s` from `RateLimiter.handle_429()`; connection errors → `network`; other → `rejected`.

Only after step 3 does the App (a) encrypt the headers into the session store, (b) set `app_state['youtube_client']`, (c) call `reauthenticate_youtube` if jobs are parked.

### 3.4 Session store (replaces `headers.json`)

`src/auth/youtube_session_store.py`: `save(headers: dict, account_name: str)` / `load() -> (headers, account_name) | None` / `clear()`, Fernet-encrypted via `src/utils/encryption.py`, path `config.app_config.YOUTUBE_SESSION_PATH = CREDENTIALS_DIR/youtube_session.enc`. `TokenManager.get_youtube_client()` / `is_youtube_authenticated()` / `clear_youtube_token()` read this store; `YouTubeAuthenticator`'s `headers.json`/`browser.json` repo-root lookups and the dead `_authenticate_oauth*` paths are deleted (CONTEXT_CONTRACT §5 punch list). The S0 silent identity check (UX_FLOW §8) = `load()` → `YTMusic(auth=…)` → §3.3 steps.

---

## 4. Silent re-capture (CONTEXT_CONTRACT §4.3 payoff)

### 4.1 The two directions

**Pull (engine asks):** a `YouTubeAuthError` in `YouTubeSearcher`/`PlaylistMigrator` → `BackgroundWorker` parks the job `paused_auth`, sets `auth_required`, calls `Notifier.notify_auth_required()`. The App's `CaptureHub` observes this (the `MigrationManager` fires a callback `on_auth_required` — **NEW**, one line in `BackgroundWorker._park_auth_paused` → manager → hub; or the hub polls `is_auth_required()` on its existing 1 s UI tick) and runs:

```
reauth():
  1. cached-first: headers = session_store.load(); if newer than the last
     failure → build client → §3.3 verify. (Covers "the extension already pushed
     fresh cookies while we were mid-request".) Success → step 4.
  2. for each live Port (prefer the browser that produced the last good capture):
       send capture_request{purpose:"reauth"}; wait ≤ 10 s for cookies/signed_out.
       cookies → §3.3 verify. Success → step 4.
  3. no live port, or every port answered signed_out / verify failed
       → PROMPT PATH (§4.3).
  4. new_client verified → session_store.save → MigrationManager.reauthenticate_youtube(new_client)
       → UI banner "Reconnected automatically." (5 s) → Notifier.notify_resumed (optional).
```

`reauthenticate_youtube` does the rest (swaps the client into migrator + searcher via `set_client`, re-queues `paused_auth` jobs through the normal resume path). The hub never touches `PlaylistMigrator` directly.

**Push (extension notices rotation):** the extension subscribes to `cookies.onChanged` and, when `changeInfo.cookie.domain` ends with `youtube.com` and `changeInfo.cause` is `explicit`/`overwrite` (ignore `expired`/`evicted`/`expired_overwrite` for the *trigger*, but always send the full current set), debounces **2 s** (rotations arrive as bursts of several cookies), re-reads the full set, and sends `cookies{reason:"changed"}`. On receipt the App:

- hashes the sorted `name=value` list; identical to the last stored hash → ignore.
- if `auth_required` is true → run `reauth()` step 1 with these cookies (this is the zero-click resume: the browser rotated the session, the extension pushed it, the job continues without anyone noticing).
- else → `session_store.save(headers)` **without** an identity check (no API spend while nothing is wrong) and swap the client lazily: set `pending_client` so the next `YouTubeAuthError` is handled by step 1 instantly. Never call `reauthenticate_youtube` when no job is parked (it would log a spurious resume).

### 4.2 Throttling the push path

`onChanged` can fire dozens of times a minute while the user browses YouTube. Rules: 2 s debounce in the extension; identical-hash dedupe in the App; at most **one** identity check per 60 s triggered by pushes, and only while `auth_required`. Identity checks always go through `RateLimiter` (invariant §6.3).

### 4.3 Prompt path (browser closed / port dead / signed out)

Exactly UX_FLOW §2.4 "Prompt path" and E11: Progress banner + OS notification "YouTube Music signed you out — click **Reconnect** to continue. Your progress is saved; nothing is lost." The button:

1. If no live Port: `webbrowser.open("https://music.youtube.com")` (launching the browser starts the extension's background context, which reconnects within seconds — §4.4) and wait ≤ 60 s for a `hello`.
2. Send `capture_request{purpose:"reauth"}`; on `signed_out` show E9 ("You're not signed in to YouTube Music in your browser. Sign in there, then click Connect.") with **Open YouTube Music** · **Try again**.
3. On success → `reauthenticate_youtube` → banner clears.

If the extension is no longer installed (no hello within 60 s and the browser is open) → E7 install state inline in the banner.

### 4.4 Keeping the port alive

- **Chromium:** MV3 service workers are terminated after ~30 s idle, but an **open Native Messaging port counts as activity in Chrome ≥ 116** — the worker stays alive while the port is connected, and Chrome also keeps it alive for in-flight extension API calls. The extension additionally sends `ping` every 25 s (belt and braces; cheap) and registers a `chrome.alarms` alarm (`"reconnect"`, period 1 min) that calls `connectNative` if the port is closed. This is why `alarms` is in the permission list (no install-time warning). Verify the ≥116 behaviour locally (§8).
- **Firefox:** MV3 background is an event page (`background.scripts`, non-persistent); `connectNative` ports keep it alive; same alarm fallback.
- On `onDisconnect` (`runtime.lastError` = "Specified native messaging host not found" / "Access to the specified native messaging host is forbidden" / "Native host has exited"): record the text in `storage.session` for the popup (maps to E10 "The extension can't reach this app. Restarting the app usually fixes it."), then back off 5 s → 15 s → 60 s (alarm).
- `runtime.onInstalled` and `runtime.onStartup` → `connectNative` immediately (this is what makes the Welcome card flip "automatically" after store install — UX_FLOW §2.4 first-run).
- App quit → `bye` → extension waits for the alarm; no error shown in the popup until the user opens it ("The app isn't running. Open it to connect.").

---

## 5. Native-host manifest registration (per browser, per OS)

### 5.1 The host executable

The host **is the App binary**: `main.py` checks `sys.argv[1:2] == ["--native-host"]` *before importing flet* and runs `src.bridge.native_host.main()`, which must start in well under 1 s (import only `json`, `struct`, `sys`, `os`, `multiprocessing.connection`, `logging`). Packaged builds: `<install dir>/PlaylistMigrator.exe --native-host` (Windows), `/Applications/Playlist Migrator.app/Contents/MacOS/PlaylistMigrator --native-host`, `<AppImage/deb path>/playlist-migrator --native-host`.

Browsers only accept an executable in `path`; on Windows it must be `.exe` or `.bat`/`.cmd`. Browsers do **not** pass extra arguments from the manifest, so the registration util writes a tiny launcher next to the manifest: Windows `capture-host.bat` containing `@echo off` + `"<exe>" --native-host %*`; POSIX `capture-host.sh` (`#!/bin/sh`, `exec "<exe>" --native-host "$@"`, mode 0755). In a dev checkout the launcher calls `"<venv python>" "<repo>/main.py" --native-host`. (If the Flet-packed binary can be made to accept the flag directly, the launcher is still kept for Windows and simply points at the exe — one code path.)

Host name: `com.playlist_migrator.capture` (lowercase alphanumerics, dots, underscores; no `-`).

### 5.2 Manifest content

Chromium family (`com.playlist_migrator.capture.json`):

```json
{
  "name": "com.playlist_migrator.capture",
  "description": "Hands your YouTube Music sign-in to the Playlist Migrator app on this computer.",
  "path": "<absolute path to launcher>",
  "type": "stdio",
  "allowed_origins": [
    "chrome-extension://<CHROME_WEB_STORE_ID>/",
    "chrome-extension://<EDGE_ADDONS_ID>/",
    "chrome-extension://<DEV_PINNED_ID>/"
  ]
}
```

Firefox (same filename, different allow-list key):

```json
{
  "name": "com.playlist_migrator.capture",
  "description": "…",
  "path": "<absolute path to launcher>",
  "type": "stdio",
  "allowed_extensions": ["capture@playlist-migrator.app"]
}
```

Notes: `path` must be absolute on macOS/Linux; on Windows it may be relative to the manifest's directory but we always write absolute. Firefox requires `browser_specific_settings.gecko.id` in the extension manifest to equal the `allowed_extensions` entry. The Chromium dev ID is pinned by adding a `"key"` field to `manifest.json` so unpacked loads get a stable ID; the store ID will differ and is added once known (OPEN QUESTION 1). Edge Add-ons assigns its own ID — Edge still uses the `chrome-extension://` scheme in `allowed_origins`.

### 5.3 Install locations (user-level only — no admin, no system dirs)

| Browser | Windows (registry key; default value = absolute manifest path) | macOS (`~/Library/Application Support/…/NativeMessagingHosts/<name>.json`) | Linux (`~/.config/…/NativeMessagingHosts/<name>.json`) |
|---|---|---|---|
| Chrome | `HKCU\Software\Google\Chrome\NativeMessagingHosts\com.playlist_migrator.capture` | `Google/Chrome/` | `google-chrome/` (also `google-chrome-beta/`, `google-chrome-unstable/` if present) |
| Chromium | `HKCU\Software\Chromium\NativeMessagingHosts\…` | `Chromium/` | `chromium/` |
| Edge | `HKCU\Software\Microsoft\Edge\NativeMessagingHosts\…` | `Microsoft Edge/` | `microsoft-edge/` |
| Brave | `HKCU\Software\BraveSoftware\Brave-Browser\NativeMessagingHosts\…` | `BraveSoftware/Brave-Browser/` | `BraveSoftware/Brave-Browser/` |
| Vivaldi (best-effort) | `HKCU\Software\Vivaldi\NativeMessagingHosts\…` | `Vivaldi/` | `vivaldi/` |
| Firefox | `HKCU\Software\Mozilla\NativeMessagingHosts\com.playlist_migrator.capture` | `Mozilla/NativeMessagingHosts/` | `~/.mozilla/native-messaging-hosts/` |

The manifest JSON files themselves live in `~/.playlist_migrator/native_hosts/<browser>/com.playlist_migrator.capture.json` (one per family because Firefox's differs) and the per-browser locations above are the registry pointer (Windows) or a copy (macOS/Linux — a copy, not a symlink, because sandboxed browsers may not follow links out of their profile tree).

**Sandboxed browsers (Linux):** Flatpak Firefox reads `~/.var/app/org.mozilla.firefox/.mozilla/native-messaging-hosts/`; Flatpak Chrome `~/.var/app/com.google.Chrome/config/google-chrome/NativeMessagingHosts/`; Snap Chromium `~/snap/chromium/common/.config/chromium/NativeMessagingHosts/` — but a confined Snap/Flatpak browser may be unable to **execute** a host outside its sandbox at all. Register anyway; E8/E10 copy covers the failure; see OPEN QUESTION 4.

### 5.4 Registration behaviour (`src/bridge/host_registry.py`)

- `register_all() -> list[RegisteredBrowser]` runs **on every App launch** (before the Welcome screen renders) and after a packaged App updates its install path. Idempotent: rewrite the manifest if its `path` or allow-list differs; otherwise no-op.
- **Detect** a browser by: (Windows) `HKLM/HKCU\Software\Clients\StartMenuInternet` entries + known install paths; (macOS) `/Applications/<name>.app` or `~/Applications/`; (Linux) `shutil.which` for `google-chrome`, `chromium`, `microsoft-edge`, `brave-browser`, `firefox` + the profile dirs above existing. **Also register for a browser whose profile directory exists even if the binary isn't found** (portable installs), and always register for all of Chrome/Edge/Firefox on Windows — writing an unused HKCU key is harmless and removes a whole class of E10.
- Return value feeds UX_FLOW §2.4: the "Add to Chrome / Edge / Firefox" buttons are those detected browsers; Brave/other Chromium → Chrome Web Store link; nothing detected → E8.
- `unregister_all()` for "Delete everything and start over" (Settings) and the uninstaller.
- Pure functions `manifest_for(browser_family, launcher_path, ids)` and `locations_for(os_name, browser)` are unit-testable headlessly; the filesystem/registry writes take an injectable root (`home=`, `winreg` shim) for tests.

---

## 6. Install / connect UX wiring (UX_FLOW §2.4, §7)

### 6.1 Card states driven by `CaptureHub` events

`CaptureHub` exposes a thread-safe snapshot and a subscriber callback (UI subscribes on `WelcomeScreen.show()`, unsubscribes on hide):

```python
class CaptureHub:
    def start(self) -> None                      # listener thread, writes run/capture.json + key
    def stop(self) -> None                       # bye to all ports, remove run/ files
    def ports(self) -> list[PortInfo]            # browser, extension_id, since, last_seen
    def has_live_port(self) -> bool
    def request_capture(self, purpose, timeout_s=10) -> CaptureResult   # blocking helper, prefers last-good browser
    def connect_youtube(self, on_done) -> None   # async: request → verify → store → on_done(result)
    def subscribe(self, cb) -> Unsubscribe       # events: port_opened/closed, cookies_pushed, identity_confirmed/failed, reauth_succeeded
    def attach_engine(self, manager: MigrationManager) -> None   # enables §4 reauth()
```

`CaptureResult = {ok: bool, account_name?: str, client?: YTMusic, code?: "no_extension"|"signed_out"|"rejected"|"network"|"rate_limited"|"timeout", browser?: str}`.

### 6.2 `welcome_screen._handle_connect(is_spotify=False)` becomes

```
if not hub.has_live_port():
    card → FIRST-RUN state (title "YouTube Music — one-time setup (1 minute)",
           copy from UX_FLOW §2.4, buttons for hub.registry.detected_browsers()
           → webbrowser.open(store_url[browser]); "Click Add in the store, then
           come back here. We'll notice automatically.")
    subscribe: on port_opened within 120 s → flip to normal state AND auto-start
               connect (no second click). After 120 s: "Still waiting for the
               extension… Check again" (text button re-runs this branch).
    return
card → `connecting` ("Waiting for you in your browser… If you're already signed in
        to YouTube Music, this takes a second.")
hub.connect_youtube(on_done=self._complete_youtube)
```

`_complete_youtube(result)`: `ok` → `self.youtube_client = result.client`, `youtube_authenticated = True`, `_update_card_state(False, True)` with "✓ Connected as **{account_name}**", toast "YouTube Music connected." · `signed_out` → E9 with **Open YouTube Music** (`webbrowser.open`) · **Try again** · `timeout`/port died mid-request → E10 · `rate_limited` → "YouTube Music asked us to wait a moment — trying again at HH:MM" (auto-retry) · `network` → E18.

Remove: the "Connect Spotify first" gate (the YouTube card must be connectable in either order — one fewer forced step), the `token_manager.authenticate_youtube()` call, and any mention of headers files. `restore_session()` keeps using `TokenManager.get_youtube_client()`, which now reads the session store (§3.4) and performs the silent `get_account_info()`.

Store URLs (constants in `config/app_config.py`; placeholders until published — OPEN QUESTION 1):
`EXTENSION_STORE_URLS = {"chrome": "https://chromewebstore.google.com/detail/<id>", "edge": "https://microsoftedge.microsoft.com/addons/detail/<id>", "firefox": "https://addons.mozilla.org/firefox/addon/<slug>/", "brave": <chrome url>, "chromium": <chrome url>}`.

### 6.3 Progress screen & Settings

- `MigrationProgressScreen` already renders E11 from `auth_required`; it adds a 5 s success banner on the hub's `reauth_succeeded` event and wires **Reconnect YouTube Music** to `hub.reconnect_youtube()` (= §4.3 prompt path, which ends in `reauthenticate_youtube`).
- Settings "YouTube Music" row: "Extension: connected in Chrome, Firefox" from `hub.ports()`; "not detected — **Install**" opens the first-run state.
- `Notifier.notify_auth_required` is unchanged; the hub attempts the silent path **before** the notification would be meaningful — so `BackgroundWorker` should notify only if the hub reports no success within ~15 s (`on_auth_required` callback returns `handled: bool`; see Build plan task 6).

### 6.4 Popup (extension) copy — status only, no inputs

| State | Copy |
|---|---|
| port open, identity confirmed | "Connected to Playlist Migrator as {account_name}." |
| port open, no identity yet | "Connected to Playlist Migrator. Click Connect YouTube Music in the app." |
| `app_unavailable` | "The Playlist Migrator app isn't running. Open it and this connects automatically." |
| host not found / forbidden | "Can't reach the app. Open Playlist Migrator and, if that doesn't help, restart it." |
| `identity_failed signed_out` | "You're not signed in to YouTube Music in this browser. Sign in, then try again in the app." + **Open YouTube Music** |

No buttons that capture. All capture is driven from the App so there is exactly one place the user clicks.

---

## 7. Security & scope

- **Extension permissions:** `cookies`, `nativeMessaging`, `alarms`; `host_permissions: ["https://music.youtube.com/*"]`. Drop `storage` (use `storage.session`, which needs no permission? — it does need `storage`; if the popup needs state, keep `storage` as it carries no warning; otherwise hold state in the service worker and accept it resets) and **drop `http://127.0.0.1:8765/*`**. No `tabs`, no `webRequest`, no content scripts, no `<all_urls>`.
- **What leaves the browser:** cookie `name/value/domain/path/flags` for `music.youtube.com` only, to a host the browser itself vetted via the manifest, which relays over a same-user IPC channel to the same-user App. Nothing goes to any network destination other than YouTube Music (and Spotify, from the engine). No telemetry (invariant §6.4).
- **At rest:** only `youtube_session.enc` (Fernet) under `~/.playlist_migrator/credentials/`. The Host writes nothing. `run/capture.key` is random per App run and never contains cookies. Logs must never contain cookie values or the `authorization` header — add a `redact()` in `src/bridge/protocol.py` used by every log line (unit-tested).
- **IPC threat model:** another process as the *same* OS user can read the key file and connect — that is the same trust boundary as reading `~/.playlist_migrator/credentials/` directly or the browser's own profile; no local-user escalation is created. Other users / remote hosts: no path (no TCP socket; socket file 0600; pipe gated by HMAC).
- **Native Messaging limits honoured:** 1 MB host→browser; Host enforces 1 MB in both directions and on IPC.
- **Store review risk (HANDOFF open item):** an extension that reads cookies and ships them to a native host is reviewable but scrutinised. Mitigation: single purpose stated verbatim in the listing ("Connects your YouTube Music sign-in to the Playlist Migrator desktop app so it can copy your playlists"); privacy policy URL explaining local-only handling; `music.youtube.com` as the **only** host permission; no remote code; no obfuscation (ship readable source); a reviewer-facing note describing the native host and how to test. Keep Spotify Option B **out** of this extension until this review has passed once (CONTEXT_CONTRACT §4.2 decision). Expect Firefox AMO to require source submission; the extension has no build step beyond selecting the manifest variant.

---

## 8. What MUST be tested on the user's local machine (cannot be verified headless)

1. **Native Messaging handshake per browser** (Chrome, Edge, Brave, Firefox; Windows + macOS + at least one Linux): `connectNative` spawns the launcher, `hello`/`hello_ack` round-trip, `argv` contents, port survives ≥ 10 min idle.
2. **Chrome ≥ 116 service-worker liveness** with an open native port (and whether `ping` is needed at all); Firefox event-page behaviour.
3. **`cookies.getAll` returns the httpOnly set** (`HSID`, `SSID`, `__Secure-*PSID`, `__Secure-*PSIDTS`, `LOGIN_INFO`) in each browser, and whether any needed cookie is partitioned (CHIPS) or hidden by Firefox Total Cookie Protection / `firstPartyDomain`.
4. **`cookies.onChanged` fires on real session rotation** (`__Secure-3PSIDTS` etc.) while music.youtube.com is open and while it is closed but the browser is running; observed cadence; debounce adequacy.
5. **End-to-end silent re-capture:** start a migration, invalidate the session (sign out/in in the browser or wait for rotation), confirm `paused_auth` → zero-click resume with "Reconnected automatically."; then the prompt path with the browser fully closed.
6. **Manifest registration on each OS**: HKCU keys and launcher `.bat` on Windows (incl. path with spaces), copies under `~/Library/Application Support/...` on macOS (and whether the notarized app may spawn from inside the bundle), `~/.config/...` and `~/.mozilla/...` on Linux; Snap/Flatpak browsers (expect failure — document which).
7. **Register-after-install:** install the browser *after* the App, relaunch the App, confirm detection + registration.
8. **IPC on Windows:** `AF_PIPE` listener + HMAC handshake from the browser-spawned process (different parent, same user); pipe name uniqueness across two logged-in Windows users.
9. **Packaged binary as host:** `PlaylistMigrator.exe --native-host` start-up time (< 1 s, before Flet import) and that the browser does not show a console window (Windows: launcher via `.bat` may flash a window — may need `start /b` or a `.vbs`/`pythonw` approach; verify).
10. **Store review outcome** (Chrome Web Store, Edge Add-ons, AMO): approval, requested changes, and the final extension IDs → `allowed_origins`.
11. **Identity check via `get_account_info()`** on a freshly captured set vs a 24-hour-old stored set (does a stale set fail loudly or return garbage?).

---

## 9. Build plan (ordered; each task names what is headlessly testable)

| # | Task | Files | Headless unit tests (`tests/`) | Needs local |
|---|---|---|---|---|
| 1 | **Protocol module**: message schemas, `v`, validation, `redact()`, 1 MB guard, framing helpers `read_frame(stream)` / `write_frame(stream, obj)` | `src/bridge/__init__.py`, `src/bridge/protocol.py` | `test_bridge_protocol.py`: frame round-trip, LE length, oversize rejected, unknown type → error, redact strips cookie values/authorization | — |
| 2 | **Move session builder**: `bridge/session.py` → `src/bridge/session.py`, sorted cookies, ignore extra keys, optional UA override; delete `bridge/` and the prototype `extension/popup.*` token UI | `src/bridge/session.py`; remove `bridge/*`, update `tests/test_bridge_session.py` import | existing 3 tests + sort determinism + extra-key tolerance | — |
| 3 | **Session store**: encrypted save/load/clear; `TokenManager` reads it; delete `headers.json`/`browser.json`/OAuth code paths in `YouTubeAuthenticator`; `YOUTUBE_SESSION_PATH` constant | `src/auth/youtube_session_store.py`, `src/auth/token_manager.py`, `src/auth/youtube_auth.py`, `config/app_config.py` | `test_youtube_session_store.py` (tmp home, Fernet round trip, missing file → None); update `test_auth.py` | — |
| 4 | **Native host**: stdio relay ↔ `multiprocessing.connection.Client`, `app_unavailable` path, ping/pong local, exit codes; `main.py --native-host` dispatch before Flet import | `src/bridge/native_host.py`, `main.py` | `test_native_host.py`: drive with in-memory stdin/stdout `BytesIO` + a real `Listener` on a tmp AF_UNIX path (skip on Windows CI) — hello relay, capture_request relay, app-missing → `app_unavailable`, oversize frame → error + exit | browser spawn (§8.1) |
| 5 | **CaptureHub (App side)**: Listener thread, key/`capture.json` files with modes, port registry, `request_capture`, `connect_youtube` (build → RateLimiter → `get_account_info` → store), push handling with hash dedupe + 60 s cap, events | `src/bridge/capture_hub.py` | `test_capture_hub.py`: fake Host via `Client`; fake `YTMusic` (dict / raises / `[]`) to cover identity_confirmed/failed/signed-out trap; RateLimiter spy asserts every verify goes through it; dedupe; file modes 0600/0700 (POSIX) | Windows pipe (§8.8) |
| 6 | **Engine wiring**: `MigrationManager.set_auth_required_handler(cb)` (**NEW**, called from `BackgroundWorker` park path; `Notifier` fires only if handler returns False or after 15 s); hub `attach_engine` → `reauth()` → `reauthenticate_youtube`; `pending_client` lazy swap | `src/migrators/migration_manager.py`, `src/utils/background_worker.py`, `src/bridge/capture_hub.py` | `test_migration_manager.py` / `test_auth_pause_resume.py`: handler invoked once per outage; `reauthenticate_youtube` called with the hub's client; jobs leave `paused_auth`; no call when nothing parked | §8.5 |
| 7 | **Host registry**: manifests, launcher scripts, per-OS/browser locations, detection, `register_all` idempotent, `unregister_all`; call from `main.py` on launch | `src/bridge/host_registry.py`, `main.py` | `test_host_registry.py`: manifest JSON per family (allowed_origins vs allowed_extensions), locations table for each (os, browser), writes into a tmp `home`, fake `winreg` records keys, idempotence, launcher content | §8.6–8.7 |
| 8 | **Extension MV3 rewrite**: `background.js` (connectNative, hello, capture on request, onChanged debounce, ping, alarm reconnect, onInstalled/onStartup), status-only popup, `manifest.chromium.json` (`service_worker`, `key`) + `manifest.firefox.json` (`background.scripts`, `gecko.id`), `build.sh` to assemble `dist/chromium` + `dist/firefox`; drop `127.0.0.1` host permission and token input | `extension/*` | None in pytest (JS). Optional: `tests/test_extension_manifest.py` asserting both manifests contain only the §7 permissions and no `127.0.0.1` | §8.1–8.4 |
| 9 | **UI wiring**: `_handle_connect(is_spotify=False)` per §6.2, first-run install state, auto-start on `port_opened`, E7/E8/E9/E10 copy, remove "Connect Spotify first" gate; Progress screen "Reconnected automatically" + Reconnect button → `hub.reconnect_youtube()`; Settings extension status row | `src/ui/screens/welcome_screen.py`, `migration_progress_screen.py`, `settings_screen.py`, `config/app_config.py` (store URLs) | `test_welcome_screen.py`: fake hub with/without ports → first-run vs connecting; result → card copy; `test_migration_progress_screen.py`: success banner on event | visual check |
| 10 | **Docs/hygiene**: update `CLAUDE.md` auth paragraph and `HANDOFF.md` prototype section, delete repo-root `headers.json` references, add `.gitignore` for `dist/`; `tests/test_code_hygiene.py` gains "no `headers.json` string in `src/`" | docs, tests | hygiene test | — |

Dependencies: 1 → 2,3 → 4,5 → 6,7 → 9; 8 is parallel to 4–7 and needs only §2. Each task is a separate commit on `prototype/extension-bridge`.

---

## 10. Invariant & rubric self-check (CONTEXT_CONTRACT §6 / §7)

- No typed token, JSON edit, DevTools or terminal step anywhere: store install + one click. The IPC key is machine-generated and never shown. ✓
- YouTube Music = extension + Native Messaging only; OAuth code paths deleted; no embedded/automated browser; no cookie-jar reading from the App. ✓
- Every `get_account_info()` and engine call passes through the engine's single `RateLimiter`. ✓
- Local-only: no TCP listener, no outbound call except YouTube Music/Spotify, no telemetry; session encrypted at rest under `~/.playlist_migrator/credentials/`; nothing sensitive in the repo root. ✓
- Single app: the Host is the App binary with a flag, spawned by the browser, not a program the user runs. ✓
- Scope kept: `paused_auth` → silent resume via the existing `reauthenticate_youtube` seam; nothing about sharding/resume/throttling is touched. ✓
- Flet 0.28, branch `prototype/extension-bridge`, tests under `tests/`, no model identifiers. ✓

---

## 11. OPEN QUESTIONS (decide; do not invent)

1. **Extension IDs / store slugs.** `allowed_origins` and the store URLs need the published Chrome Web Store ID, Edge Add-ons ID and AMO slug; the Firefox `gecko.id` (`capture@playlist-migrator.app`) and the Chromium dev `key` can be fixed now. Who publishes, under which developer account, and when — the App can ship with placeholders only in dev builds.
2. **Chrome Web Store review posture.** Is the owner comfortable shipping *readable* source and a public privacy-policy URL (needed for a `cookies` + `nativeMessaging` extension)? Which domain hosts the policy (invariant §6.4 says the owner hosts nothing — a static page in the GitHub repo/Pages is the minimum)?
3. **Windows launcher without a console flash.** `.bat` launchers can briefly show a console window when the browser spawns them. Options: a tiny compiled stub, `wscript`/`.vbs`, or making the packaged exe a GUI-subsystem binary that accepts `--native-host` directly (then `path` points at the exe and no launcher is needed on Windows). Needs §8.9 to decide.
4. **Snap/Flatpak browsers on Linux.** Confined browsers may not be able to execute the host at all. Accept "unsupported — install the .deb/Flatpak-less browser" (E8 variant copy) or ship a Flatpak of the App with a portal? Proposed: register anyway, document as unsupported in v1.
5. **`storage` permission.** Keep `storage` (warning-free) for popup state across service-worker restarts, or go strictly `cookies` + `nativeMessaging` + `alarms`? Spec defaults to keeping `storage` if the popup needs more than "is the port open".
6. **Auth-required handler vs. polling.** Task 6 proposes a **NEW** `MigrationManager.set_auth_required_handler()` so the silent path runs before the OS notification. Alternative: hub polls `is_auth_required()` on the UI tick and the notification fires immediately (slightly noisier). Engine owner to pick; spec prefers the handler (fewer user-visible flickers).
7. **Multiple browsers signed into different Google accounts.** If Chrome and Firefox both have live ports with different YouTube accounts, which wins on reauth? Proposed: the browser that produced the last confirmed identity; if its port is gone, ask the user ("Reconnect using Chrome / Firefox") rather than silently switching accounts (writing playlists into the wrong account is unrecoverable).
8. **Firefox cookie partitioning.** Total Cookie Protection / `firstPartyDomain` may require passing `firstPartyDomain: "youtube.com"` (or `null` with `privacy.firstparty.isolate`) to `cookies.getAll`. Verify in §8.3 and encode the result in `background.js`.
9. **User-agent fidelity.** Should the App always use the capturing browser's real UA (sent in `hello`) for ytmusicapi requests? Likely yes for fingerprint consistency; confirm it does not change `get_account_info()` behaviour in §8.11.
10. **Uninstall.** Who removes the HKCU keys / manifest copies when the App is uninstalled (installer hook vs. "Delete everything" in Settings only)?
