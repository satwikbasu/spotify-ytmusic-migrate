// Status-only popup. No inputs: the app and extension pair automatically.
"use strict";
const api = globalThis.browser || globalThis.chrome;
const statusEl = document.getElementById("status");
const btn = document.getElementById("connect");

function describe(s) {
  if (s.account) return { text: "Connected to YouTube Music as " + s.account + ".", button: false };
  if (s.state === "app_not_running") return { text: "The Playlist Migrator app isn't running. Open it, then click Connect.", button: true };
  if (s.state === "host_unreachable") return { text: "This extension can't reach the app. Restarting the app usually fixes it.", button: true };
  if (s.signedOut || s.failure === "signed_out") return { text: "You're not signed in to YouTube Music in this browser. Sign in at music.youtube.com, then click Connect.", button: true };
  if (s.failure) return { text: "YouTube Music didn't accept the sign-in. Make sure you're signed in, then try again.", button: true };
  if (s.state === "connected") return { text: "Ready. Click Connect to link YouTube Music.", button: true };
  return { text: "Not connected.", button: true };
}

function render(s) {
  const d = describe(s);
  statusEl.textContent = d.text;
  btn.hidden = !d.button;
}

function refresh() { api.runtime.sendMessage({ type: "get_status" }).then(render, () => render({})); }

btn.addEventListener("click", () => {
  btn.disabled = true;
  statusEl.textContent = "Connecting...";
  api.runtime.sendMessage({ type: "connect" }).then(() => setTimeout(() => { btn.disabled = false; refresh(); }, 1500),
    () => { btn.disabled = false; refresh(); });
});
refresh();
