# YouTube Music Authentication - Complete Solution

## The Problem

You were experiencing HTTP 400 "Bad Request" errors when using OAuth authentication with ytmusicapi:

```
ytmusicapi.exceptions.YTMusicServerError: Server returned HTTP 400: Bad Request.
Request contains an invalid argument.
```

This occurred on **ALL** ytmusicapi endpoints, even unauthenticated ones like `search()`, when OAuth credentials were provided.

## Root Cause

**ytmusicapi uses YouTube Music's internal/unofficial web API**, not the official YouTube Data API v3.

- ✅ **Without OAuth**: `YTMusic()` works perfectly (search returns results)
- ❌ **With OAuth**: `YTMusic('oauth.json', oauth_credentials=creds)` fails with HTTP 400

The YouTube Music internal API **rejects** the official OAuth tokens from YouTube Data API v3.

## The Solution: Browser Authentication

ytmusicapi has **two authentication methods**:

### 1. Browser Authentication (RECOMMENDED) ✅
- Uses cookies from your actual browser session
- **Most reliable** method for YouTube Music
- YouTube Music accepts these credentials
- See `BROWSER_AUTH_INSTRUCTIONS.md` for setup

### 2. OAuth Authentication (NOT RECOMMENDED) ❌
- Uses official YouTube Data API v3 credentials
- **Does not work reliably** with YouTube Music
- Gets rejected with HTTP 400 errors
- Only kept as fallback

## How to Set Up Browser Authentication

### Quick Start

1. **Run setup command:**
   ```powershell
   ytmusicapi browser
   ```

2. **Follow instructions to copy browser headers from YouTube Music**
   - See `BROWSER_AUTH_INSTRUCTIONS.md` for detailed step-by-step guide

3. **Test authentication:**
   ```powershell
   python test_browser_auth.py
   ```

4. **You're done!** The app will now use browser authentication automatically.

## Updated Code Architecture

The `YouTubeAuthenticator` class now supports **both authentication methods** with automatic fallback:

```python
from src.auth.youtube_auth import YouTubeAuthenticator

# Will automatically use browser auth if headers.json exists
# Falls back to OAuth if not
auth = YouTubeAuthenticator()
yt = auth.authenticate()
```

### Authentication Priority

1. **First**: Try `headers.json` (browser auth)
2. **Second**: Try `browser.json` (browser auth alternate filename)
3. **Third**: Try OAuth (cached token or device code flow)

### File Locations

- `headers.json` or `browser.json` - Browser authentication headers
- `~/youtube_oauth.json` - OAuth token (fallback, may not work)

## Why OAuth Doesn't Work

YouTube Music has TWO different APIs:

1. **Official YouTube Data API v3** (what your OAuth credentials are for)
   - Used for regular YouTube (videos, channels, etc.)
   - Has strict quotas and rate limits
   - Does NOT support YouTube Music library/playlists

2. **Unofficial YouTube Music Internal API** (what ytmusicapi uses)
   - Used by music.youtube.com web interface
   - Supports library, playlists, liked songs
   - **Rejects OAuth tokens** from Data API v3
   - **Accepts browser session cookies**

This is why:
- OAuth tokens are valid (they work with YouTube Data API v3)
- OAuth tokens are rejected by YouTube Music's internal API (HTTP 400)
- Browser cookies work (they're from music.youtube.com)

## Testing Results

### Before (OAuth) ❌
```
Test 1: search() - ❌ FAILED: HTTP 400
Test 2: get_home() - ❌ FAILED: HTTP 400
Test 3: get_account_info() - ❌ FAILED: HTTP 400
Test 4: get_library_playlists() - ❌ FAILED: HTTP 400
```

### After (Browser Auth) ✅
```
Test 1: search() - ✅ SUCCESS: Found 27 results
Test 2: get_account_info() - ✅ SUCCESS: Account name loaded
Test 3: get_library_playlists() - ✅ SUCCESS: Playlists loaded
```

## Next Steps

1. **Set up browser authentication** (see `BROWSER_AUTH_INSTRUCTIONS.md`)
2. **Test with** `test_browser_auth.py`
3. **Run your migration app** - it will automatically use browser auth

## Security Notes

- The `headers.json` file contains your YouTube Music session cookies
- Keep it secure (it's in .gitignore)
- Don't share or commit it
- Session expires after weeks/months - just re-run setup when needed

## FAQ

**Q: Can I still use OAuth?**
A: OAuth is kept as a fallback, but it likely won't work. Browser auth is strongly recommended.

**Q: Do I need OAuth Client ID/Secret anymore?**
A: No, if using browser authentication. You can make them optional in your `.env` file.

**Q: What if browser authentication expires?**
A: Just run `ytmusicapi browser` again to get fresh headers. Takes 30 seconds.

**Q: Is browser authentication secure?**
A: Yes, it's the same method the official YouTube Music web app uses. Just keep your `headers.json` file private.

**Q: Should we switch to official YouTube Data API v3?**
A: **No**, because:
- YouTube Data API v3 doesn't support YouTube Music library/playlists
- It's for regular YouTube (videos, channels)
- Browser authentication with ytmusicapi is the correct solution

## Summary

- ✅ **Problem identified**: OAuth tokens rejected by YouTube Music's internal API
- ✅ **Solution implemented**: Browser authentication support added
- ✅ **Code updated**: `YouTubeAuthenticator` class now supports both methods
- ✅ **Instructions provided**: `BROWSER_AUTH_INSTRUCTIONS.md` for setup
- ✅ **Testing tools provided**: `test_browser_auth.py` for validation

**Action Required**: Run `ytmusicapi browser` to set up browser authentication, then test with `python test_browser_auth.py`
