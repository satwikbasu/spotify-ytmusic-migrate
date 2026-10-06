# YouTube OAuth Rewrite - Complete ✅

## Summary
The `YouTubeAuthenticator` class has been **completely rewritten** to use ytmusicapi's native OAuth flow for TV/Limited Input devices, replacing the old broken `google-auth-oauthlib` implementation.

## What Changed

### ❌ Removed (Old Implementation)
- **google-auth-oauthlib** - `InstalledAppFlow` 
- **google.oauth2.credentials** - `Credentials` class
- Web server OAuth flow with `run_local_server()`
- Manual credential JSON handling
- Manual token refresh logic
- Helper methods: `_create_client_config()`, `_credentials_to_dict()`, `_refresh_token_if_needed()`, `_load_credentials()`, `_save_credentials()`

### ✅ Added (New Implementation)
- **ytmusicapi.auth.oauth** - `OAuthCredentials`, `RefreshingToken`
- Device code OAuth flow (TV/Limited Input devices)
- Automatic token caching and refresh
- `pathlib.Path` instead of `os.path`
- Comprehensive logging
- Better error messages with setup instructions

## File Changes

### 1. `src/auth/youtube_auth.py` (Complete Rewrite)
**Before:** 392 lines using InstalledAppFlow  
**After:** 246 lines using native ytmusicapi OAuth

**New Imports:**
```python
from pathlib import Path
from typing import Optional
import logging
from ytmusicapi import YTMusic
from ytmusicapi.auth.oauth import OAuthCredentials, RefreshingToken
```

**New Authentication Flow:**
```python
# 1. Create credentials
credentials = OAuthCredentials(client_id, client_secret)

# 2. Try cached token
if credentials_path.exists():
    token = RefreshingToken.from_json(filepath, client_id, client_secret)
    
# 3. Or start device code flow
token = RefreshingToken.prompt_for_token(
    credentials=credentials,
    open_browser=True,
    to_file=str(credentials_path)
)

# 4. Create authenticated client
yt = YTMusic(auth=str(credentials_path), oauth_credentials=credentials)
```

### 2. `requirements.txt`
**Removed:**
```plaintext
google-auth-oauthlib>=1.2.0
```

**Added Comment:**
```plaintext
# NOTE: google-auth-oauthlib is NO LONGER REQUIRED
# ytmusicapi now handles OAuth natively via ytmusicapi.auth.oauth
```

## Critical Setup Requirements

### ⚠️ IMPORTANT: OAuth Client Type Change Required

**YOU MUST recreate your OAuth credentials in Google Cloud Console:**

1. **Go to:** [Google Cloud Console → Credentials](https://console.cloud.google.com/apis/credentials)

2. **Delete existing OAuth Client ID** (if type is "Desktop app")

3. **Create NEW OAuth Client ID:**
   - Click "+ CREATE CREDENTIALS" → "OAuth client ID"
   - **Application type:** "TVs and Limited Input devices" (NOT "Desktop app")
   - **Name:** "Playlist Migrator" (or any name)
   - Click "CREATE"

4. **Copy new credentials:**
   - Client ID: `962811673639-xxxxxxxxxx.apps.googleusercontent.com`
   - Client Secret: `GOCSPX-xxxxxxxxxxxx`

5. **Update `.env` file:**
   ```env
   YOUTUBE_CLIENT_ID=<new_client_id_here>
   YOUTUBE_CLIENT_SECRET=<new_client_secret_here>
   ```

6. **Verify OAuth Consent Screen:**
   - Add your Google account as a test user
   - Add scope: `https://www.googleapis.com/auth/youtube`

7. **Verify API is enabled:**
   - YouTube Data API v3 must be enabled
   - Check in "APIs & Services" → "Library"

## Testing the New Implementation

### 1. Delete Old Token
```powershell
Remove-Item ~\youtube_oauth.json -ErrorAction SilentlyContinue
```

### 2. Run Application
```powershell
python main.py
```

### 3. Expected Flow
```
======================================================================
YouTube Music Authentication - Device Code Flow
======================================================================

IMPORTANT: This requires OAuth Client ID type 'TVs and Limited Input devices'
If you see errors, verify your OAuth client type in Google Cloud Console.

Please visit: https://www.google.com/device
Enter code: XXXX-YYYY

Waiting for authorization...
```

### 4. Authorize
1. Browser opens to `https://www.google.com/device`
2. Enter the displayed code (e.g., `ABCD-EFGH`)
3. Select your Google account
4. Click "Continue" to grant access

### 5. Success Message
```
Credentials saved to: C:\Users\YourName\youtube_oauth.json

Testing YouTube Music API connection...

======================================================================
YouTube Music authentication successful!
======================================================================
```

## Benefits of New Implementation

1. **✅ Works with ytmusicapi 1.4.0+**
   - Native OAuth support
   - No format conversion needed

2. **✅ Device Code Flow**
   - Better for apps without web servers
   - Works on devices with limited input

3. **✅ Automatic Token Management**
   - Tokens auto-refresh when expired
   - No manual refresh logic needed

4. **✅ Simpler Code**
   - 146 fewer lines of code
   - No manual JSON handling
   - Cleaner architecture

5. **✅ Better Error Messages**
   - Specific instructions for common issues
   - Links to Google Cloud Console
   - Setup verification steps

## Troubleshooting

### Error: "invalid_grant"
**Cause:** Using wrong OAuth client type (Desktop app instead of TV/Limited Input)  
**Fix:** Delete OAuth client, create new one with type "TVs and Limited Input devices"

### Error: "Access blocked: This app's request is invalid"
**Cause:** Missing test user or wrong scope  
**Fix:** 
1. Go to OAuth consent screen
2. Add your Google account as test user
3. Add scope: `https://www.googleapis.com/auth/youtube`

### Error: "API not enabled"
**Cause:** YouTube Data API v3 not enabled  
**Fix:** 
1. Go to APIs & Services → Library
2. Search "YouTube Data API v3"
3. Click "ENABLE"

### Error: "Client ID not found"
**Cause:** Incorrect credentials in .env  
**Fix:** 
1. Copy credentials from Google Cloud Console
2. Update .env file
3. Restart application

## Migration Path for Existing Users

1. ✅ **Backup old token** (optional):
   ```powershell
   Copy-Item ~\youtube_oauth.json ~\youtube_oauth.json.backup
   ```

2. ✅ **Delete old token**:
   ```powershell
   Remove-Item ~\youtube_oauth.json
   ```

3. ✅ **Create new OAuth credentials** (see setup above)

4. ✅ **Update .env file** with new credentials

5. ✅ **Run application** and complete device code flow

6. ✅ **Token auto-caches** for future use

## Verification Checklist

- [ ] OAuth client type is "TVs and Limited Input devices"
- [ ] Client ID and Client Secret copied to .env
- [ ] .env file loaded correctly (python-dotenv installed)
- [ ] YouTube Data API v3 enabled
- [ ] Test user added to OAuth consent screen
- [ ] Old youtube_oauth.json deleted
- [ ] Application runs without errors
- [ ] Device code flow displays URL and code
- [ ] Browser authorization completes successfully
- [ ] YTMusic client connects and fetches playlists

## Files Modified

1. ✅ `src/auth/youtube_auth.py` - Complete rewrite (392 → 246 lines)
2. ✅ `requirements.txt` - Removed google-auth-oauthlib dependency

## Files NOT Modified (No Changes Needed)

- `main.py` - Already loads .env with python-dotenv
- `config/app_config.py` - Already reads YOUTUBE_CLIENT_ID/SECRET from env
- Tests - Will continue to work with new implementation
- Other auth files (spotify_auth.py) - Independent implementation

## Next Steps

1. **User action required:** Create new OAuth credentials with correct type
2. **User action required:** Update .env file with new credentials
3. **User action required:** Delete old token file
4. **User action required:** Run application and complete device code flow

Once completed, YouTube Music authentication will work perfectly with ytmusicapi's native OAuth implementation! 🎉

## Documentation

For more details, see:
- `CREDENTIALS_SETUP.md` - Full setup guide
- `OAUTH_MIGRATION_NOTES.md` - OAuth policy changes
- Module docstring in `youtube_auth.py` - Implementation details
