// Playlist Migrator - YouTube Music connector (MV3 background).
//
// Talks to the desktop app through Native Messaging (no network, no typed
// token). Protocol: docs/EXTENSION_BRIDGE_PROTOCOL.md, message shapes in
// src/capture/protocol.py. Cookie values are only ever sent over the native
// port and are never logged.
"use strict";

const api = globalThis.browser || globalThis.chrome;
const HOST = "com.playlist_migrator.capture";
const PROTOCOL_V = 1;
const MUSIC_URL = "https://music.youtube.com";
const PING_MS = 25000;
const BACKOFF_MS = [5000, 15000, 60000];

let port = null;
let pingTimer = null;
let retryTimer = null;
let attempt = 0;

// Status shown by the popup. state: connecting | connected | app_not_running
// | host_unreachable | disconnected. account: name once the app confirmed it.
const status = { state: "disconnected", account: null, signedOut: false, failure: null };

function browserName() {
  const brands = (navigator.userAgentData && navigator.userAgentData.brands || [])
    .map((b) => b.brand.toLowerCase()).join(",");
  const ua = navigator.userAgent.toLowerCase();
  if (ua.includes("firefox")) return "firefox";
  if (ua.includes("edg/") || brands.includes("edge")) return "edge";
  if (brands.includes("brave") || (navigator.brave !== undefined)) return "brave";
  if (brands.includes("google chrome") || ua.includes("chrome/")) return "chrome";
  return "unknown";
}

function send(msg) {
  if (!port) return false;
  try {
    port.postMessage(Object.assign({ v: PROTOCOL_V }, msg));
    return true;
  } catch (e) {
    return false;
  }
}

function connect() {
  if (port) return;
  clearTimeout(retryTimer);
  status.state = "connecting";
  try {
    port = api.runtime.connectNative(HOST);
  } catch (e) {
    port = null;
    status.state = "host_unreachable";
    scheduleRetry();
    return;
  }
  port.onMessage.addListener(onHostMessage);
  port.onDisconnect.addListener(onDisconnect);
  send({
    type: "hello",
    extension_id: api.runtime.id,
    extension_version: api.runtime.getManifest().version,
    browser: browserName(),
    user_agent: navigator.userAgent,
    capabilities: ["cookies"], // "onchanged" is added when the silent push lands
  });
  clearInterval(pingTimer);
  pingTimer = setInterval(() => send({ type: "ping", t: Date.now() }), PING_MS);
}

function onDisconnect() {
  const err = api.runtime.lastError && api.runtime.lastError.message || "";
  port = null;
  clearInterval(pingTimer);
  status.account = null;
  if (status.state !== "app_not_running") {
    // "host not found" / "forbidden" / "host has exited" => the app can't be reached.
    status.state = err ? "host_unreachable" : "disconnected";
  }
  scheduleRetry();
}

function scheduleRetry() {
  clearTimeout(retryTimer);
  const wait = BACKOFF_MS[Math.min(attempt, BACKOFF_MS.length - 1)];
  attempt += 1;
  retryTimer = setTimeout(connect, wait);
}

function onHostMessage(msg) {
  if (!msg || typeof msg.type !== "string") return;
  switch (msg.type) {
    case "hello_ack":
      attempt = 0;
      status.state = "connected";
      break;
    case "app_unavailable":
      status.state = "app_not_running"; // host exits right after; alarm retries
      break;
    case "capture_request":
      capture(msg.request_id || null, "request");
      break;
    case "identity_confirmed":
      status.state = "connected";
      status.account = msg.account_name || "your account";
      status.signedOut = false;
      status.failure = null;
      break;
    case "identity_failed":
      status.account = null;
      status.signedOut = msg.code === "signed_out";
      status.failure = msg.code;
      break;
    case "bye":
      status.state = "app_not_running";
      status.account = null;
      try { port && port.disconnect(); } catch (e) { /* already closed */ }
      port = null;
      clearInterval(pingTimer);
      break;
    default:
      break; // pong, error, unknown: nothing to do
  }
}

// Read the full cookie set for music.youtube.com and send it, or signed_out.
async function capture(requestId, reason) {
  let cookies;
  try {
    cookies = await api.cookies.getAll({ url: MUSIC_URL });
  } catch (e) {
    send({ type: "error", request_id: requestId, code: "cookies_denied", message: "Could not read cookies" });
    return;
  }
  const signedIn = cookies.some((c) => c.name === "__Secure-3PAPISID" && c.domain.endsWith("youtube.com"));
  if (!signedIn) {
    status.signedOut = true;
    send({ type: "signed_out", request_id: requestId, reason: "no_session_cookie" });
    return;
  }
  send({
    type: "cookies",
    request_id: requestId,
    reason: reason,
    captured_at: Date.now(),
    cookies: cookies.map((c) => ({
      name: c.name, value: c.value, domain: c.domain, path: c.path,
      secure: c.secure, httpOnly: c.httpOnly, expirationDate: c.expirationDate,
    })),
  });
}

// TODO(deferred, owner thin-slice decision): silent auto-push. Subscribe to
// cookies.onChanged (domain endsWith "youtube.com"), debounce 2 s, re-read the
// full set and send cookies{reason:"changed", request_id:null} (spec section 4.1).
// The app currently ignores "changed" pushes, so it is intentionally not wired.

// Popup <-> background.
api.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg && msg.type === "get_status") {
    sendResponse(Object.assign({}, status));
  } else if (msg && msg.type === "connect") {
    attempt = 0;
    if (!port) connect();
    // Port may have just opened; the host answers hello_ack first, then we capture.
    setTimeout(() => capture(null, "request").then(() => sendResponse(Object.assign({}, status))), port ? 0 : 400);
    return true;
  }
  return false;
});

// Keep trying to reach the app (it may be started after the browser).
api.alarms.create("reconnect", { periodInMinutes: 1 });
api.alarms.onAlarm.addListener((a) => { if (a.name === "reconnect" && !port) connect(); });
api.runtime.onInstalled.addListener(connect);
api.runtime.onStartup.addListener(connect);
connect();
