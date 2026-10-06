#!/usr/bin/env bash
# Setup for the Spotify -> YouTube Music migrator.
# Works on Linux / WSL / macOS / Claude Code cloud environments.
set -euo pipefail

echo "==> Creating virtualenv (.venv)"
python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate

echo "==> Installing runtime dependencies"
pip install --upgrade pip >/dev/null
pip install -r requirements.txt

# The extension/bridge prototype's end-to-end tests drive a real Chromium.
# Only needed if you run bridge e2e tests; skip with SKIP_PLAYWRIGHT=1.
if [ "${SKIP_PLAYWRIGHT:-0}" != "1" ]; then
  echo "==> Installing Playwright + Chromium (for bridge e2e tests)"
  pip install playwright
  python -m playwright install chromium
fi

if [ ! -f .env ]; then
  echo "==> No .env found; copying .env.example -> .env (fill in your credentials)"
  cp .env.example .env
fi

echo "==> Running the test suite"
python -m pytest tests/ -q || true

cat <<'DONE'

Setup complete.
  - Activate the venv:   source .venv/bin/activate
  - Fill in .env with your Spotify + YouTube credentials
  - Run the app:         python main.py
  - Run the prototype:   python -m bridge.app   (see bridge/README.md)
DONE
