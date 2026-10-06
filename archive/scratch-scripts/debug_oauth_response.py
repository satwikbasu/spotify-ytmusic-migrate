"""Debug script to see what the OAuth server actually returns."""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv
import json

# Load environment variables
load_dotenv()

print("=" * 80)
print("YouTube OAuth Debug - Raw Token Response")
print("=" * 80)

client_id = os.getenv("YOUTUBE_CLIENT_ID")
client_secret = os.getenv("YOUTUBE_CLIENT_SECRET")

if not client_id or not client_secret:
    print("\n❌ Error: Missing credentials in .env file")
    sys.exit(1)

print(f"\nClient ID: {client_id[:30]}...")
print(f"Client Secret: {client_secret[:20]}...")

try:
    from ytmusicapi.auth.oauth import OAuthCredentials
    from ytmusicapi.auth.oauth.token import RefreshingToken
    import ytmusicapi.auth.oauth.credentials as oauth_creds_module
    
    print("\n✓ Imports successful")
except ImportError as e:
    print(f"❌ Import error: {e}")
    sys.exit(1)

print("\n" + "=" * 80)
print("Testing Device Code Flow with Raw Response Capture")
print("=" * 80)

credentials = OAuthCredentials(
    client_id=client_id,
    client_secret=client_secret
)

print("\n1. Requesting device code...")

try:
    # This is what prompt_for_token does internally
    # Let's do it step by step to see the raw response
    
    import requests
    
    # Step 1: Get device code
    device_code_url = "https://oauth2.googleapis.com/device/code"
    device_code_params = {
        "client_id": client_id,
        "scope": "https://www.googleapis.com/auth/youtube"
    }
    
    print(f"\nPOST {device_code_url}")
    print(f"Params: {device_code_params}")
    
    response = requests.post(device_code_url, data=device_code_params)
    print(f"\nStatus: {response.status_code}")
    
    if response.status_code != 200:
        print(f"❌ Device code request failed: {response.status_code}")
        print(f"Response: {response.text}")
        sys.exit(1)
    
    device_code_response = response.json()
    print(f"\n✓ Device code response:")
    print(json.dumps(device_code_response, indent=2))
    
    device_code = device_code_response.get("device_code")
    user_code = device_code_response.get("user_code")
    verification_url = device_code_response.get("verification_url")
    
    if not device_code or not user_code:
        print("\n❌ Missing device_code or user_code in response")
        sys.exit(1)
    
    print(f"\n{'='*80}")
    print("MANUAL AUTHORIZATION REQUIRED")
    print(f"{'='*80}")
    print(f"\n1. Go to: {verification_url}")
    print(f"2. Enter code: {user_code}")
    print(f"3. Sign in and authorize")
    print(f"\n{'='*80}\n")
    
    input("Press ENTER after you've completed authorization in the browser... ")
    
    # Step 2: Poll for token
    print("\n2. Polling for access token...")
    
    token_url = "https://oauth2.googleapis.com/token"
    token_params = {
        "client_id": client_id,
        "client_secret": client_secret,
        "device_code": device_code,
        "grant_type": "urn:ietf:params:oauth:grant-type:device_code"
    }
    
    print(f"\nPOST {token_url}")
    print(f"Params: client_id, client_secret, device_code, grant_type")
    
    response = requests.post(token_url, data=token_params)
    print(f"\nStatus: {response.status_code}")
    
    raw_token = response.json()
    print(f"\n✓ Token response:")
    print(json.dumps(raw_token, indent=2))
    
    # Check for errors
    if "error" in raw_token:
        print(f"\n❌ OAuth error: {raw_token.get('error')}")
        print(f"Description: {raw_token.get('error_description', 'No description')}")
        
        if raw_token.get('error') == 'invalid_client':
            print("\n🔍 Diagnosis: INVALID CLIENT")
            print("This means your OAuth Client ID configuration is wrong.")
            print("\nPossible causes:")
            print("1. OAuth Client type is 'Desktop app' instead of 'TVs and Limited Input devices'")
            print("2. Client ID or Client Secret is incorrect")
            print("3. OAuth client was deleted or disabled")
            print("\n🔧 Solution:")
            print("1. Go to: https://console.cloud.google.com/apis/credentials")
            print("2. Delete the existing OAuth Client ID")
            print("3. Create NEW OAuth Client ID with type: 'TVs and Limited Input devices'")
            print("4. Update .env file with new Client ID and Secret")
        elif raw_token.get('error') == 'authorization_pending':
            print("\n⚠ Authorization still pending - you need to complete it in the browser")
        elif raw_token.get('error') == 'access_denied':
            print("\n⚠ Access denied - you need to grant permission in the browser")
        
        sys.exit(1)
    
    # If we got here, token is valid
    print("\n✅ Token received successfully!")
    print(f"✓ Access token: {raw_token.get('access_token', '')[:30]}...")
    print(f"✓ Refresh token: {raw_token.get('refresh_token', '')[:30]}...")
    print(f"✓ Token type: {raw_token.get('token_type')}")
    print(f"✓ Expires in: {raw_token.get('expires_in')} seconds")
    
    # Try to create RefreshingToken
    print("\n" + "=" * 80)
    print("3. Creating RefreshingToken object...")
    print("=" * 80)
    
    try:
        token = RefreshingToken(credentials=credentials, **raw_token)
        print("✓ RefreshingToken created successfully!")
        
        # Save to file
        token_path = Path.home() / "youtube_oauth.json"
        with open(token_path, 'w') as f:
            json.dump(raw_token, f, indent=2)
        print(f"✓ Token saved to: {token_path}")
        
        print("\n✅ Authentication successful! You can now use the main app.")
        
    except TypeError as e:
        print(f"❌ Failed to create RefreshingToken: {e}")
        print(f"\nRaw token keys: {list(raw_token.keys())}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
except Exception as e:
    print(f"\n❌ Unexpected error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
