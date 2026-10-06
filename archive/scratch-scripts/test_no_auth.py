"""Test YTMusic without authentication first."""
from ytmusicapi import YTMusic

print("Testing YTMusic without authentication...")

# Create client without auth
yt = YTMusic()

print("✓ YTMusic client created (no auth)\n")

print("Test: search() without authentication")
try:
    results = yt.search("test", limit=1)
    print(f"✅ SUCCESS: Search works without auth")
    print(f"   Found {len(results)} results")
except Exception as e:
    print(f"❌ FAILED: {e}")
    import traceback
    traceback.print_exc()
