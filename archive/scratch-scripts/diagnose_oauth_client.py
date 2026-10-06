"""
YouTube OAuth Client Type Diagnostic
=====================================

This script will help determine if your OAuth Client ID is configured correctly.

The CRITICAL requirement is:
- OAuth Client type MUST be "TVs and Limited Input devices"
- NOT "Desktop app"
- NOT "Web application"

If you have the wrong type, you'll see errors like:
- "invalid_client"
- HTTP 400: Bad Request
- "Request contains an invalid argument"
"""

import os
import sys
import requests
import json
from dotenv import load_dotenv

load_dotenv()

print("=" * 80)
print("YouTube OAuth Client Type Diagnostic")
print("=" * 80)

client_id = os.getenv("YOUTUBE_CLIENT_ID")
client_secret = os.getenv("YOUTUBE_CLIENT_SECRET")

if not client_id or not client_secret:
    print("\n❌ Missing credentials in .env file")
    sys.exit(1)

print(f"\nClient ID: {client_id}")

# Test 1: Check if we can request a device code
print("\n" + "=" * 80)
print("Test 1: Requesting Device Code")
print("=" * 80)
print("This tests if your OAuth client supports device code flow...")

device_code_url = "https://oauth2.googleapis.com/device/code"
device_code_params = {
    "client_id": client_id,
    "scope": "https://www.googleapis.com/auth/youtube"
}

response = requests.post(device_code_url, data=device_code_params)

print(f"\nHTTP Status: {response.status_code}")

if response.status_code == 200:
    print("✅ SUCCESS - Your client supports device code flow")
    data = response.json()
    print(f"\nDevice code: {data.get('device_code', '')[:30]}...")
    print(f"User code: {data.get('user_code')}")
    print(f"Verification URL: {data.get('verification_url')}")
    print("\n✅ Your OAuth Client type appears to be CORRECT")
    print("   (TVs and Limited Input devices)")
elif response.status_code == 400:
    print("❌ FAILURE - Device code flow not supported")
    try:
        error_data = response.json()
        print(f"\nError: {error_data.get('error')}")
        print(f"Description: {error_data.get('error_description')}")
    except:
        print(f"\nResponse: {response.text}")
    
    print("\n🔍 DIAGNOSIS:")
    print("   Your OAuth Client type is WRONG")
    print("   It's likely configured as 'Desktop app' or 'Web application'")
    print("\n🔧 FIX:")
    print("   1. Go to: https://console.cloud.google.com/apis/credentials")
    print("   2. Delete your current OAuth Client ID")
    print("   3. Click 'CREATE CREDENTIALS' → 'OAuth client ID'")
    print("   4. Select type: 'TVs and Limited Input devices'")
    print("   5. Copy the new Client ID and Secret to .env")
    sys.exit(1)
else:
    print(f"❌ Unexpected status code: {response.status_code}")
    print(f"Response: {response.text}")
    sys.exit(1)

# Test 2: Check API enablement
print("\n" + "=" * 80)
print("Test 2: YouTube Data API v3 Status")
print("=" * 80)
print("Note: We can't directly check if the API is enabled without making")
print("      an authenticated request, but we've verified device code flow works.")

print("\n" + "=" * 80)
print("✅ ALL TESTS PASSED")
print("=" * 80)
print("\nYour OAuth configuration appears correct!")
print("\nIf you're still getting HTTP 400 errors when calling YouTube Music API,")
print("it could be:")
print("  1. API quota exceeded (check Google Cloud Console)")
print("  2. YouTube Data API v3 not enabled")
print("  3. Account not added as test user in OAuth consent screen")
print("\nNext steps:")
print("  1. Go to: https://console.cloud.google.com/apis/credentials/consent")
print("  2. Verify your Google account is listed as a test user")
print("  3. Go to: https://console.cloud.google.com/apis/library")
print("  4. Search 'YouTube Data API v3' and verify it's ENABLED")
