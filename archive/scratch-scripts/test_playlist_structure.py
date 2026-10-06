"""
Test to verify playlist data structure from Spotify
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.auth.spotify_auth import SpotifyAuthenticator
from src.fetchers.spotify_fetcher import SpotifyFetcher
from src.utils.rate_limiter import RateLimiter
from src.utils.cache_manager import CacheManager
from config import app_config

def test_playlist_structure():
    print("Testing Spotify playlist data structure...\n")
    
    # Authenticate
    auth = SpotifyAuthenticator(
        client_id=app_config.SPOTIFY_CLIENT_ID,
        client_secret=app_config.SPOTIFY_CLIENT_SECRET
    )
    
    try:
        spotify = auth.authenticate()
        print("✅ Authenticated with Spotify\n")
        
        # Create fetcher
        rate_limiter = RateLimiter(per_minute_limit=60, daily_limit=10000)
        cache_manager = CacheManager()
        
        fetcher = SpotifyFetcher(
            spotify_client=spotify,
            rate_limiter=rate_limiter,
            cache_manager=cache_manager
        )
        
        # Get playlists
        playlists = fetcher.get_user_playlists(use_cache=False)
        print(f"✅ Fetched {len(playlists)} playlists\n")
        
        if playlists:
            print("First playlist structure:")
            print("-" * 60)
            first = playlists[0]
            for key, value in first.items():
                if isinstance(value, str) and len(value) > 100:
                    print(f"  {key}: {value[:100]}...")
                else:
                    print(f"  {key}: {value}")
            print("-" * 60)
            print()
            
            # Check expected fields
            print("Field checks:")
            print(f"  ✅ 'id': {first.get('id', 'MISSING')}")
            print(f"  ✅ 'name': {first.get('name', 'MISSING')}")
            print(f"  ✅ 'tracks_count': {first.get('tracks_count', 'MISSING')}")
            print(f"  ✅ 'image_url': {'Present' if first.get('image_url') else 'Missing'}")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_playlist_structure()
