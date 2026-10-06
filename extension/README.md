# Capture extension

MV3 extension that hands the user's signed-in YouTube Music session to the desktop
app over Native Messaging (host `com.playlist_migrator.capture`). No typed token, no
localhost server. Protocol: `docs/EXTENSION_BRIDGE_PROTOCOL.md`.

- `manifest.json` Chromium family (Chrome/Edge/Brave). Carries the dev `key`
  (`DEV_CHROMIUM_EXTENSION_KEY`) so unpacked loads get a stable id.
- `manifest.firefox.json` Firefox: `background.scripts` plus
  `browser_specific_settings.gecko.id` (`FIREFOX_GECKO_ID`).
- `./build.sh` copies the shared files plus the right manifest into `dist/chromium`
  and `dist/firefox`.

Permissions are minimal: `cookies`, `nativeMessaging`, `alarms`, and the single host
`https://music.youtube.com/*`. No icons yet (placeholder; add before store submission).
The silent `cookies.onChanged` push is deferred (see TODO in `background.js`).
