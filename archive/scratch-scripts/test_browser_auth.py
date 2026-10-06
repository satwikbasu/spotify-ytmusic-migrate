"""
Test YouTube Music API with browser authentication (headers.json)
"""
from ytmusicapi import YTMusic

def test_browser_auth():
    try:
        print("Loading YTMusic with browser authentication...")
        yt = YTMusic('headers.json')
        print("✅ YTMusic client created successfully\n")
        
        # Test 1: Search (should work)
        print("Test 1: search()")
        results = yt.search("test", limit=1)
        print(f"✅ Search works: Found {len(results)} results\n")
        
        # Test 2: Get account info (requires auth)
        print("Test 2: get_account_info()")
        account = yt.get_account_info()
        print(f"✅ Account info works: {account.get('accountName', 'Unknown')}\n")
        
        # Test 3: Get library playlists (requires auth)
        print("Test 3: get_library_playlists()")
        playlists = yt.get_library_playlists(limit=5)
        print(f"✅ Library playlists work: Found {len(playlists)} playlists\n")
        
        print("=" * 60)
        print("🎉 ALL TESTS PASSED - Browser auth works!")
        print("=" * 60)
        
    except Exception as e:
        print(f"❌ Error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_browser_auth()
