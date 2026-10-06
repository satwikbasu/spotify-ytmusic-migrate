"""Test with the official ytmusicapi oauth token file."""
import os
from dotenv import load_dotenv
from ytmusicapi import YTMusic
from ytmusicapi.auth.oauth import OAuthCredentials

load_dotenv()

client_id = os.getenv('YOUTUBE_CLIENT_ID')
client_secret = os.getenv('YOUTUBE_CLIENT_SECRET')

print("Testing with official ytmusicapi oauth.json file...")

creds = OAuthCredentials(client_id=client_id, client_secret=client_secret)
yt = YTMusic('oauth_test.json', oauth_credentials=creds)

print("YTMusic client created successfully")
print("\nTesting API call: get_library_playlists(limit=1)...")

playlists = yt.get_library_playlists(limit=1)
print(f"\n✅ SUCCESS! Found {len(playlists)} playlists")

if playlists:
    print(f"First playlist: '{playlists[0].get('title', 'Unknown')}'")
