"""Test YouTube Music authentication in isolation."""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

print("=" * 80)
print("YouTube Music Authentication Test")
print("=" * 80)

# Get credentials from .env
client_id = os.getenv("YOUTUBE_CLIENT_ID")
client_secret = os.getenv("YOUTUBE_CLIENT_SECRET")

print(f"\n✓ Client ID loaded: {client_id[:20]}..." if client_id else "✗ Client ID missing")
print(f"✓ Client Secret loaded: {client_secret[:20]}..." if client_secret else "✗ Client Secret missing")

if not client_id or not client_secret:
    print("\n❌ Error: Missing credentials in .env file")
    sys.exit(1)

print("\n" + "=" * 80)
print("Step 1: Testing ytmusicapi imports")
print("=" * 80)

try:
    from ytmusicapi import YTMusic
    from ytmusicapi.auth.oauth import OAuthCredentials, RefreshingToken
    print("✓ All imports successful")
except ImportError as e:
    print(f"❌ Import error: {e}")
    print("\nRun: pip install --upgrade ytmusicapi")
    sys.exit(1)

print("\n" + "=" * 80)
print("Step 2: Creating OAuth credentials object")
print("=" * 80)

try:
    credentials = OAuthCredentials(
        client_id=client_id,
        client_secret=client_secret
    )
    print("✓ OAuthCredentials created successfully")
    print(f"  Client ID: {credentials.client_id[:20]}...")
except Exception as e:
    print(f"❌ Failed to create OAuthCredentials: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "=" * 80)
print("Step 3: Check for existing token file")
print("=" * 80)

token_path = Path.home() / "youtube_oauth.json"
print(f"Token path: {token_path}")

if token_path.exists():
    print("✓ Token file exists - attempting to load")
    try:
        token = RefreshingToken.from_json(
            filepath=str(token_path),
            client_id=client_id,
            client_secret=client_secret
        )
        print("✓ Token loaded successfully")
        
        print("\n" + "=" * 80)
        print("Step 4: Creating YTMusic client with cached token")
        print("=" * 80)
        
        yt = YTMusic(auth=str(token_path))
        print("✓ YTMusic client created")
        
        print("\n" + "=" * 80)
        print("Step 5: Testing API connection")
        print("=" * 80)
        
        playlists = yt.get_library_playlists(limit=1)
        print(f"✓ API test successful! Found {len(playlists)} playlist(s)")
        
        print("\n" + "=" * 80)
        print("✅ AUTHENTICATION SUCCESSFUL WITH CACHED TOKEN")
        print("=" * 80)
        sys.exit(0)
        
    except Exception as e:
        print(f"⚠ Cached token failed: {e}")
        print("Will proceed to device code flow...")
        import traceback
        traceback.print_exc()
else:
    print("✗ Token file does not exist - will start device code flow")

print("\n" + "=" * 80)
print("Step 4: Starting device code flow")
print("=" * 80)
print("\nThis will:")
print("1. Display a URL and code")
print("2. Open your browser automatically")
print("3. Wait for you to authorize")
print("4. Save the token to file")
print("\nIMPORTANT: Just verify the code matches and sign in.")
print("Don't manually enter the code anywhere.\n")

input("Press ENTER to start device code flow... ")

try:
    print("\nStarting RefreshingToken.prompt_for_token()...")
    token = RefreshingToken.prompt_for_token(
        credentials=credentials,
        open_browser=True,
        to_file=str(token_path)
    )
    print(f"\n✓ Device code flow completed")
    print(f"✓ Token saved to: {token_path}")
except Exception as e:
    print(f"\n❌ Device code flow failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "=" * 80)
print("Step 5: Verifying saved token file")
print("=" * 80)

if token_path.exists():
    print(f"✓ Token file exists")
    file_size = token_path.stat().st_size
    print(f"✓ File size: {file_size} bytes")
    
    # Show token structure (without sensitive data)
    import json
    with open(token_path, 'r') as f:
        token_data = json.load(f)
    print(f"✓ Token contains keys: {list(token_data.keys())}")
else:
    print("❌ Token file was not created!")
    sys.exit(1)

print("\n" + "=" * 80)
print("Step 6: Creating YTMusic client with new token")
print("=" * 80)

try:
    print(f"Creating YTMusic(auth='{token_path}', oauth_credentials=credentials)...")
    yt = YTMusic(auth=str(token_path), oauth_credentials=credentials)
    print("✓ YTMusic client created successfully")
except Exception as e:
    print(f"❌ Failed to create YTMusic client: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "=" * 80)
print("Step 7: Testing API connection")
print("=" * 80)

try:
    print("Calling yt.get_library_playlists(limit=1)...")
    playlists = yt.get_library_playlists(limit=1)
    print(f"✓ API test successful!")
    print(f"✓ Found {len(playlists)} playlist(s)")
    
    if playlists:
        print(f"\nFirst playlist: {playlists[0].get('title', 'Unknown')}")
    
except Exception as e:
    print(f"❌ API test failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "=" * 80)
print("✅ ALL TESTS PASSED - AUTHENTICATION WORKING!")
print("=" * 80)
print("\nThe YouTubeAuthenticator class should work correctly.")
print("If the main app still fails, the issue is in the UI layer.")
