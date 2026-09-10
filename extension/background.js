// Minimal service worker. Present so the extension has a stable runtime context;
// currently just logs install. Cookie capture happens in the popup.
chrome.runtime.onInstalled.addListener(() => {
  console.log("Spotify -> YT Music bridge extension installed.");
});
