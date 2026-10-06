"""Test script to determine correct ytmusicapi authentication format."""

import json
from ytmusicapi import YTMusic

# Sample OAuth credentials (replace with your actual credentials from youtube_oauth.json)
sample_creds = {
    "access_token": "your_access_token",
    "refresh_token": "your_refresh_token",
    "token_uri": "https://oauth2.googleapis.com/token",
    "client_id": "your_client_id",
    "client_secret": "your_client_secret",
    "scopes": ["https://www.googleapis.com/auth/youtube.force-ssl"]
}

print("Testing different ytmusicapi authentication formats...\n")

# Test 1: Direct dict with oauth_credentials key
print("Test 1: Dict with oauth_credentials key")
try:
    auth1 = {"oauth_credentials": sample_creds}
    yt = YTMusic(auth=auth1)
    print("✅ SUCCESS: Dict with oauth_credentials works\n")
except Exception as e:
    print(f"❌ FAILED: {str(e)}\n")

# Test 2: JSON string with oauth_credentials key
print("Test 2: JSON string with oauth_credentials key")
try:
    auth2 = json.dumps({"oauth_credentials": sample_creds})
    yt = YTMusic(auth=auth2)
    print("✅ SUCCESS: JSON string with oauth_credentials works\n")
except Exception as e:
    print(f"❌ FAILED: {str(e)}\n")

# Test 3: Direct dict (no oauth_credentials wrapper)
print("Test 3: Direct credentials dict")
try:
    yt = YTMusic(auth=sample_creds)
    print("✅ SUCCESS: Direct dict works\n")
except Exception as e:
    print(f"❌ FAILED: {str(e)}\n")

# Test 4: JSON string of direct credentials
print("Test 4: JSON string of direct credentials")
try:
    auth4 = json.dumps(sample_creds)
    yt = YTMusic(auth=auth4)
    print("✅ SUCCESS: JSON string of direct credentials works\n")
except Exception as e:
    print(f"❌ FAILED: {str(e)}\n")

print("\n" + "="*60)
print("INSTRUCTIONS:")
print("1. Replace sample_creds with your actual credentials from ~/youtube_oauth.json")
print("2. Run: python test_ytmusic_format.py")
print("3. See which format works (✅)")
print("4. I'll update the code to use that format")
