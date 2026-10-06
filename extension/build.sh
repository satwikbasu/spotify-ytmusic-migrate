#!/bin/sh
# Builds dist/chromium and dist/firefox from the shared sources.
# Dev: load dist/chromium unpacked (chrome://extensions, Developer mode) or
# dist/firefox via about:debugging > Load Temporary Add-on (manifest.json).
set -e
cd "$(dirname "$0")"
rm -rf dist
for t in chromium firefox; do
  mkdir -p "dist/$t"
  cp background.js popup.html popup.js "dist/$t/"
done
cp manifest.json dist/chromium/manifest.json
cp manifest.firefox.json dist/firefox/manifest.json
echo "Built extension/dist/chromium and extension/dist/firefox"
