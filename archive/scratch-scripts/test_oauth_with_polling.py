"""YouTube OAuth with automatic polling - waits for you to authorize."""

import os
import sys
import time
import json
import webbrowser
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

print("=" * 80)
print("YouTube OAuth - Auto-Polling Version")
print("=" * 80)

client_id = os.getenv("YOUTUBE_CLIENT_ID")
client_secret = os.getenv("YOUTUBE_CLIENT_SECRET")

if not client_id or not client_secret:
    print("\n❌ Error: Missing credentials in .env file")
    sys.exit(1)

try:
    import requests
    from ytmusicapi import YTMusic
    from ytmusicapi.auth.oauth import OAuthCredentials, RefreshingToken
except ImportError as e:
    print(f"❌ Import error: {e}")
    print("\nRun: pip install requests ytmusicapi")
    sys.exit(1)

print(f"\n✓ Client ID: {client_id[:30]}...")
print(f"✓ Client Secret: {client_secret[:20]}...")

# Step 1: Request device code
print("\n" + "=" * 80)
print("Step 1: Requesting device code from Google...")
print("=" * 80)

device_code_url = "https://oauth2.googleapis.com/device/code"
device_code_params = {
    "client_id": client_id,
    "scope": "https://www.googleapis.com/auth/youtube"
}

response = requests.post(device_code_url, data=device_code_params)

if response.status_code != 200:
    print(f"❌ Failed to get device code: {response.status_code}")
    print(f"Response: {response.text}")
    sys.exit(1)

device_code_response = response.json()
device_code = device_code_response["device_code"]
user_code = device_code_response["user_code"]
verification_url = device_code_response["verification_url"]
expires_in = device_code_response["expires_in"]
interval = device_code_response.get("interval", 5)

print(f"✓ Device code received (expires in {expires_in} seconds)")

# Step 2: Display instructions and open browser
print("\n" + "=" * 80)
print("Step 2: USER ACTION REQUIRED")
print("=" * 80)
print(f"\n  🌐 Opening browser to: {verification_url}")
print(f"\n  📝 Enter this code: {user_code}")
print(f"\n  ⏰ You have {expires_in // 60} minutes to complete authorization")
print("\n" + "=" * 80)

# Open browser automatically
try:
    webbrowser.open(f"{verification_url}?user_code={user_code}")
    print("\n✓ Browser opened (if popup blocker allowed)")
except:
    print("\n⚠ Could not open browser automatically")

print(f"\nIf browser didn't open, go to: {verification_url}")
print(f"And enter code: {user_code}")

# Step 3: Poll for token
print("\n" + "=" * 80)
print("Step 3: Waiting for authorization...")
print("=" * 80)
print("\n⏳ Polling Google servers (will auto-detect when you authorize)...")
print("   Press Ctrl+C to cancel\n")

token_url = "https://oauth2.googleapis.com/token"
token_params = {
    "client_id": client_id,
    "client_secret": client_secret,
    "device_code": device_code,
    "grant_type": "urn:ietf:params:oauth:grant-type:device_code"
}

start_time = time.time()
poll_count = 0

while True:
    poll_count += 1
    elapsed = int(time.time() - start_time)
    
    # Check if expired
    if elapsed > expires_in:
        print("\n❌ Device code expired! Please run the script again.")
        sys.exit(1)
    
    print(f"  Poll #{poll_count} (elapsed: {elapsed}s / {expires_in}s)", end="\r")
    
    response = requests.post(token_url, data=token_params)
    raw_token = response.json()
    
    if "error" in raw_token:
        error = raw_token["error"]
        
        if error == "authorization_pending":
            # Still waiting - continue polling
            time.sleep(interval)
            continue
        elif error == "slow_down":
            # Increase interval
            interval += 1
            time.sleep(interval)
            continue
        elif error == "access_denied":
            print("\n\n❌ Access denied! You rejected the authorization.")
            sys.exit(1)
        elif error == "expired_token":
            print("\n\n❌ Device code expired! Please run the script again.")
            sys.exit(1)
        elif error == "invalid_client":
            print("\n\n❌ INVALID CLIENT - Wrong OAuth configuration!")
            print("\n🔍 Diagnosis:")
            print("   Your OAuth Client type is incorrect.")
            print("\n🔧 Fix:")
            print("   1. Go to: https://console.cloud.google.com/apis/credentials")
            print("   2. Delete current OAuth Client ID")
            print("   3. Create NEW with type: 'TVs and Limited Input devices'")
            print("   4. Update .env with new credentials")
            sys.exit(1)
        else:
            print(f"\n\n❌ OAuth error: {error}")
            print(f"   Description: {raw_token.get('error_description', 'No description')}")
            sys.exit(1)
    
    # Success! We got the token
    print(f"\n\n✅ Authorization successful! (after {elapsed}s, {poll_count} polls)")
    break

# Step 4: Save token
print("\n" + "=" * 80)
print("Step 4: Saving token...")
print("=" * 80)

token_path = Path.home() / "youtube_oauth.json"

# Create the token in ytmusicapi format
ytmusic_token = {
    "access_token": raw_token["access_token"],
    "refresh_token": raw_token["refresh_token"],
    "scope": raw_token.get("scope", "https://www.googleapis.com/auth/youtube"),
    "token_type": raw_token.get("token_type", "Bearer"),
    "expires_in": raw_token.get("expires_in", 3600)
}

with open(token_path, 'w') as f:
    json.dump(ytmusic_token, f, indent=2)

print(f"✓ Token saved to: {token_path}")
print(f"✓ File size: {token_path.stat().st_size} bytes")

# Step 5: Test with YTMusic
print("\n" + "=" * 80)
print("Step 5: Testing YTMusic client...")
print("=" * 80)

try:
    # Must create OAuth credentials object
    credentials = OAuthCredentials(client_id=client_id, client_secret=client_secret)
    
    print(f"\nCreating YTMusic(auth='{token_path}', oauth_credentials=credentials)...")
    yt = YTMusic(auth=str(token_path), oauth_credentials=credentials)
    print("✓ YTMusic client created")
    
    print("\nTesting API with get_library_playlists(limit=1)...")
    playlists = yt.get_library_playlists(limit=1)
    print(f"✓ API test successful!")
    print(f"✓ Found {len(playlists)} playlist(s)")
    
    if playlists:
        print(f"\nFirst playlist: '{playlists[0].get('title', 'Unknown')}'")
    
except Exception as e:
    print(f"❌ YTMusic test failed: {e}")
    import traceback
    traceback.print_exc()
    
    print("\n🔍 Debugging info:")
    print(f"   Token file exists: {token_path.exists()}")
    if token_path.exists():
        with open(token_path, 'r') as f:
            token_content = json.load(f)
        print(f"   Token keys: {list(token_content.keys())}")
    sys.exit(1)

# Success!
print("\n" + "=" * 80)
print("✅ COMPLETE SUCCESS!")
print("=" * 80)
print("\nYour YouTube Music authentication is working correctly.")
print("You can now run the main application: python main.py")
print(f"\nToken will be auto-refreshed when it expires.")
print(f"Token file: {token_path}")
