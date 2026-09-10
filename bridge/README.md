# Extension + Bridge prototype

Turns the manual `headers.json` step into a one-click browser action. The user
signs into YouTube Music **normally in their own browser** (no devtools, no
embedded-browser login that Google blocks); a companion extension reads the
session cookies via `chrome.cookies` and hands them to a local HTTP bridge,
which reconstructs the ytmusicapi session and drives the existing engine.

```
 ┌────────────┐  chrome.cookies.getAll   ┌───────────┐  POST /yt-session  ┌──────────────┐
 │  extension │ ───────────────────────▶ │  popup.js │ ─────────────────▶ │  bridge.py   │
 │  (in the   │  (reads httpOnly session │           │  cookies + token   │ 127.0.0.1:8765│
 │  real      │   cookies a web page     └───────────┘                    │              │
 │  browser)  │   cannot see)                                             │ build_headers│
 └────────────┘                                                           │  → SAPISIDHASH│
                                                                          │ get_account_ │
                                                                          │  info() check │
                                                                          │ writes        │
                                                                          │  headers.json │
                                                                          │ → PlaylistMig │
                                                                          └──────────────┘
```

## Why this shape

- Google blocks Google sign-in inside embedded browsers (WebView/CEF/Electron)
  and detects automated Chromium, so the app cannot host the login itself. The
  extension sidesteps that entirely: the user logs in in their own real browser.
- `chrome.cookies` (with the `cookies` permission + host permission) can read
  the **httpOnly** `__Secure-3PAPISID` cookie that `document.cookie` cannot.
- The `authorization: SAPISIDHASH …` header is computed from that cookie, not
  captured — so no HTTP-header interception is needed.

## Run it

1. `python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`
   (plus `pip install "flet==0.28.3"`)
2. Authenticate Spotify once so a token cache exists (see the main app), and
   point `SPOTIFY_CACHE` at it.
3. Start the bridge + demo migrator: `python -m bridge.app`
   It prints a **pairing token**.
4. Load `extension/` as an unpacked extension (chrome://extensions → Developer
   mode → Load unpacked), while signed in to music.youtube.com.
5. Click the extension → paste the pairing token → **Connect YouTube Music**.
   The bridge validates the session, writes `headers.json`, and migrates the
   playlist named by `DEMO_PLAYLIST` (default "under my grave").

## Prototype limits

- Loopback only, single pairing token — not hardened beyond a local demo.
- Spotify auth is reused from the existing cached token rather than driven from
  the extension; wiring Spotify's OAuth into this flow is the next step.
- Desktop only. The standalone Android capture remains platform-blocked.
