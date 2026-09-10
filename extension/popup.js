const BRIDGE = "http://127.0.0.1:8765";
const statusEl = document.getElementById("status");
const tokenEl = document.getElementById("token");

// Remember the pairing token between popup opens.
chrome.storage.local.get("token", ({ token }) => {
  if (token) tokenEl.value = token;
});

function show(msg, cls) {
  statusEl.textContent = msg;
  statusEl.className = cls || "";
}

document.getElementById("connect").addEventListener("click", async () => {
  const token = tokenEl.value.trim();
  if (!token) return show("Enter the pairing token shown in the app window.", "err");
  chrome.storage.local.set({ token });

  show("Reading YouTube Music session ...");
  let cookies;
  try {
    // Returns httpOnly cookies too (unlike document.cookie), because the
    // extension holds the "cookies" permission for this host.
    cookies = await chrome.cookies.getAll({ url: "https://music.youtube.com" });
  } catch (e) {
    return show("Could not read cookies: " + e.message, "err");
  }
  if (!cookies || !cookies.some((c) => c.name === "__Secure-3PAPISID")) {
    return show("You are not signed in to music.youtube.com in this browser.", "err");
  }

  show("Handing session to the local app ...");
  try {
    const res = await fetch(BRIDGE + "/yt-session", {
      method: "POST",
      headers: { "content-type": "application/json", "x-bridge-token": token },
      body: JSON.stringify({
        cookies: cookies.map((c) => ({ name: c.name, value: c.value })),
      }),
    });
    const body = await res.json();
    if (res.ok && body.connected) {
      show("Connected as " + (body.account || "your account") +
           ".\nMigration started - watch the app window.", "ok");
    } else {
      show("Bridge error: " + (body.error || res.status), "err");
    }
  } catch (e) {
    return show("Could not reach the local app on 127.0.0.1:8765. Is it running?", "err");
  }
});
