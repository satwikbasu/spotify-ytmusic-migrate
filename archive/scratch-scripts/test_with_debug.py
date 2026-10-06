"""Test YouTube Music API with debug logging enabled."""

import os
import sys
import logging
from pathlib import Path
from dotenv import load_dotenv

# Enable DEBUG logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

load_dotenv()

from ytmusicapi import YTMusic
from ytmusicapi.auth.oauth import OAuthCredentials

client_id = os.getenv("YOUTUBE_CLIENT_ID")
client_secret = os.getenv("YOUTUBE_CLIENT_SECRET")
token_path = Path.home() / "youtube_oauth.json"

print("=" * 80)
print("YouTube Music API Test with Debug Logging")
print("=" * 80)

if not token_path.exists():
    print(f"\n❌ Token file not found: {token_path}")
    print("Run test_oauth_with_polling.py first to create the token")
    sys.exit(1)

print(f"\n✓ Token file: {token_path}")
print(f"✓ Client ID: {client_id[:30]}...")

credentials = OAuthCredentials(client_id=client_id, client_secret=client_secret)

print("\nCreating YTMusic client...")
yt = YTMusic(auth=str(token_path), oauth_credentials=credentials)
print("✓ Client created")

print("\nAttempting API call: get_account_info()...")
try:
    info = yt.get_account_info()
    print(f"✅ SUCCESS: {info}")
except Exception as e:
    print(f"❌ FAILED: {e}")
    import traceback
    traceback.print_exc()
