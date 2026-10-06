# YouTube Authentication Fix - Stuck on Loading Loop

## Issue Description
After completing the device code OAuth flow and clicking "Continue" in the browser, the app would get stuck in a loading loop and fail to verify authentication.

**Error seen:**
```
ERROR:src.ui.base_screen:Showing error dialog: Failed to authenticate with YouTube Music.
YouTube Music authentication failed: Unexpected error during YouTube Music authentication
```

## Root Cause
The issue was in how the `YTMusic` client was being initialized after the device code flow completed.

**Incorrect code (causing the issue):**
```python
# After device code flow saves token to file
token = RefreshingToken.prompt_for_token(
    credentials=credentials,
    open_browser=True,
    to_file=str(self.credentials_path)
)

# WRONG: Passing both auth AND oauth_credentials
yt = YTMusic(auth=str(self.credentials_path), oauth_credentials=credentials)
```

**Problem:** When you pass a saved token file via the `auth` parameter, ytmusicapi expects to read all OAuth information from that file. Passing `oauth_credentials` as well causes a conflict and makes the client hang.

## Solution
Remove the `oauth_credentials` parameter when creating the `YTMusic` client with a saved token file.

**Correct code:**
```python
# After device code flow saves token to file
token = RefreshingToken.prompt_for_token(
    credentials=credentials,
    open_browser=True,
    to_file=str(self.credentials_path)
)

# CORRECT: Only pass auth (token file path)
yt = YTMusic(auth=str(self.credentials_path))
```

## Changes Made

### File: `src/auth/youtube_auth.py`

**1. Fixed cached token loading (line ~142):**
```python
# OLD:
yt = YTMusic(auth=str(self.credentials_path), oauth_credentials=credentials)

# NEW:
yt = YTMusic(auth=str(self.credentials_path))
```

**2. Fixed new token loading after device code flow (line ~174):**
```python
# OLD:
yt = YTMusic(auth=str(self.credentials_path), oauth_credentials=credentials)

# NEW:
yt = YTMusic(auth=str(self.credentials_path))
```

**3. Improved error logging:**
- Added `exc_info=True` to log full stack traces
- Added specific error handling for quota/rate limit errors
- Added specific error handling for permission errors

## How ytmusicapi OAuth Works

### Two ways to use YTMusic with OAuth:

**Option 1: With saved token file (what we're using)**
```python
# Token file contains: access_token, refresh_token, client_id, client_secret, etc.
yt = YTMusic(auth="/path/to/token.json")
```

**Option 2: With credentials object (for in-memory use)**
```python
# Pass the actual credentials/token object
credentials = OAuthCredentials(client_id, client_secret)
token = RefreshingToken.prompt_for_token(credentials=credentials)
yt = YTMusic(oauth_credentials=token)  # No auth file
```

**NEVER mix both!** Passing both `auth` (file path) and `oauth_credentials` (object) causes conflicts.

## Testing Instructions

1. **Delete old token file:**
   ```powershell
   Remove-Item ~\youtube_oauth.json -Force -ErrorAction SilentlyContinue
   ```

2. **Run the application:**
   ```powershell
   python main.py
   ```

3. **Complete device code flow:**
   - Click "Login with YouTube"
   - Browser opens to device code page
   - **Verify the code matches** what's shown in the app
   - Click "Continue"
   - **DO NOT enter a code** - you already verified it in the previous step
   - Sign in with your Google account
   - Grant access

4. **Expected behavior:**
   - App should show "Testing YouTube Music API connection..."
   - Then "YouTube Music authentication successful!"
   - UI should update and show playlists

## Why the Confusion Happened

The Google device code flow can be confusing:

1. **Step 1:** App displays: "Visit https://www.google.com/device and enter code: ABCD-EFGH"
2. **Step 2:** Browser shows the code and asks "Is this the code on your device?"
3. **Step 3:** You click "Continue" to confirm it matches
4. **Step 4:** Browser might show an input field - **IGNORE THIS**, just proceed to sign in
5. **Step 5:** Sign in and grant access
6. **Step 6:** App receives authorization and saves token

The key is: **You don't need to manually enter the code anywhere** - you just verify it matches.

## Related Files
- `src/auth/youtube_auth.py` - Authentication implementation (FIXED)
- `ACTION_REQUIRED.md` - User setup instructions
- `YOUTUBE_OAUTH_REWRITE_COMPLETE.md` - Technical documentation

## Verification
- ✅ Syntax check passed: `python -m py_compile src/auth/youtube_auth.py`
- ✅ No import errors
- ✅ Old token file deleted for clean test
- ✅ Ready for user testing

## Next Steps for User
1. Run the app: `python main.py`
2. Complete the device code flow
3. App should now successfully authenticate and load playlists
4. If issues persist, check the app logs for detailed error messages
