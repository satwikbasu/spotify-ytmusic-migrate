"""Test different YouTube Music API endpoints."""
import os
from dotenv import load_dotenv
from ytmusicapi import YTMusic
from ytmusicapi.auth.oauth import OAuthCredentials

load_dotenv()

client_id = os.getenv('YOUTUBE_CLIENT_ID')
client_secret = os.getenv('YOUTUBE_CLIENT_SECRET')

print("Testing various YouTube Music API endpoints...")
print("=" * 80)

creds = OAuthCredentials(client_id=client_id, client_secret=client_secret)
yt = YTMusic('oauth_test.json', oauth_credentials=creds)

print("✓ YTMusic client created successfully\n")

# Test 1: Search (doesn't require authentication)
print("Test 1: search() - Should work without auth")
try:
    results = yt.search("Oasis Wonderwall", limit=1)
    print(f"✅ SUCCESS: Found {len(results)} search results")
    if results:
        print(f"   First result: {results[0].get('title', 'Unknown')}")
except Exception as e:
    print(f"❌ FAILED: {e}")

print("\n" + "=" * 80 + "\n")

# Test 2: Get home (requires authentication)
print("Test 2: get_home() - Requires auth")
try:
    home = yt.get_home(limit=1)
    print(f"✅ SUCCESS: Got home feed with {len(home)} items")
except Exception as e:
    print(f"❌ FAILED: {e}")

print("\n" + "=" * 80 + "\n")

# Test 3: Get account info (requires authentication)
print("Test 3: get_account_info() - Requires auth")
try:
    info = yt.get_account_info()
    print(f"✅ SUCCESS: Account info retrieved")
    print(f"   Account name: {info.get('accountName', 'Unknown')}")
except Exception as e:
    print(f"❌ FAILED: {e}")

print("\n" + "=" * 80 + "\n")

# Test 4: Get library playlists (requires authentication)
print("Test 4: get_library_playlists() - Requires auth")
try:
    playlists = yt.get_library_playlists(limit=1)
    print(f"✅ SUCCESS: Found {len(playlists)} playlists")
    if playlists:
        print(f"   First playlist: '{playlists[0].get('title', 'Unknown')}'")
except Exception as e:
    print(f"❌ FAILED: {e}")

print("\n" + "=" * 80)
print("\nTest Summary:")
print("If search works but authenticated endpoints fail,")
print("the issue is with OAuth configuration or account permissions.")
