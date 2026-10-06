# 🔧 URGENT: Action Required - YouTube OAuth Credentials Update

## ⚠️ Critical Change Required

Your YouTube Music authentication will **NOT WORK** until you complete these steps. The application has been updated to use a new OAuth flow that requires different credentials.

## What You Must Do NOW

### Step 1: Create New OAuth Credentials (REQUIRED)

1. **Open Google Cloud Console:**
   https://console.cloud.google.com/apis/credentials

2. **Delete your current OAuth Client ID:**
   - Find the existing OAuth 2.0 Client ID (probably named "Playlist Migrator")
   - Click the trash icon to delete it
   - **IMPORTANT:** The old "Desktop app" type will NOT work

3. **Create NEW OAuth Client ID:**
   - Click "+ CREATE CREDENTIALS" 
   - Select "OAuth client ID"
   - **Application type:** Select **"TVs and Limited Input devices"** ⚠️ CRITICAL
     - Do NOT select "Desktop app"
     - Do NOT select "Web application"  
     - Must be "TVs and Limited Input devices"
   - **Name:** "Playlist Migrator" (or any name you prefer)
   - Click "CREATE"

4. **Copy Your New Credentials:**
   You'll see a dialog with:
   ```
   Client ID: 962811673639-xxxxxxxxxxxx.apps.googleusercontent.com
   Client Secret: GOCSPX-xxxxxxxxxxxx
   ```
   Copy both values - you'll need them in Step 2

### Step 2: Update Your .env File (REQUIRED)

1. **Open** `d:\spotify-yt-migrate\.env` in a text editor

2. **Replace** the YOUTUBE_CLIENT_ID and YOUTUBE_CLIENT_SECRET lines:
   ```env
   YOUTUBE_CLIENT_ID=<paste_new_client_id_here>
   YOUTUBE_CLIENT_SECRET=<paste_new_client_secret_here>
   ```

3. **Save** the file

### Step 3: Delete Old Token File (REQUIRED)

The old token format is incompatible. Delete it:

**PowerShell:**
```powershell
Remove-Item ~\youtube_oauth.json -Force -ErrorAction SilentlyContinue
```

**File Explorer:**
1. Press `Win + R`
2. Type: `%USERPROFILE%`
3. Delete file: `youtube_oauth.json` (if it exists)

### Step 4: Verify OAuth Consent Screen (REQUIRED)

1. **Go to:** https://console.cloud.google.com/apis/credentials/consent

2. **Check Test Users:**
   - Your Google account must be listed under "Test users"
   - If not, click "ADD USERS" and add your Google account email

3. **Check Scopes:**
   - Click "EDIT APP"
   - Scroll to "Scopes"
   - Ensure this scope is added: `https://www.googleapis.com/auth/youtube`
   - If not, click "ADD OR REMOVE SCOPES", search for "YouTube", and add it

### Step 5: Verify API is Enabled (REQUIRED)

1. **Go to:** https://console.cloud.google.com/apis/library

2. **Search:** "YouTube Data API v3"

3. **Enable:** If not already enabled, click "ENABLE"

## Testing Your Setup

Once you've completed all steps above:

### 1. Run the Application
```powershell
cd d:\spotify-yt-migrate
python main.py
```

### 2. Expected Output
```
======================================================================
YouTube Music Authentication - Device Code Flow
======================================================================

IMPORTANT: This requires OAuth Client ID type 'TVs and Limited Input devices'
If you see errors, verify your OAuth client type in Google Cloud Console.

Please visit: https://www.google.com/device
Enter code: ABCD-EFGH

Waiting for authorization...
```

### 3. Authorize in Browser
1. Your browser should open to https://www.google.com/device
2. If not, manually navigate to the URL shown
3. Enter the code displayed (e.g., `ABCD-EFGH`)
4. Select your Google account
5. Click "Continue" to grant access

### 4. Success!
```
Credentials saved to: C:\Users\YourName\youtube_oauth.json

Testing YouTube Music API connection...

======================================================================
YouTube Music authentication successful!
======================================================================
```

## Why This Change Was Necessary

- **Old Method:** Used "Desktop app" OAuth + web server callback
- **Problem:** Incompatible with ytmusicapi's internal authentication format
- **New Method:** Uses "TVs and Limited Input devices" OAuth + device code flow
- **Benefit:** Native ytmusicapi support, automatic token refresh, cleaner code

## Common Errors and Solutions

### Error: "invalid_grant" or "unauthorized_client"
**Problem:** You're still using "Desktop app" OAuth client type  
**Solution:** Delete OAuth credentials and recreate as "TVs and Limited Input devices"

### Error: "Access blocked: This app's request is invalid"
**Problem:** Missing test user or incorrect scope  
**Solution:** 
1. Add your Google account as test user (Step 4 above)
2. Add YouTube scope (Step 4 above)

### Error: "API not enabled"
**Problem:** YouTube Data API v3 not enabled  
**Solution:** Enable it (Step 5 above)

### Error: "ModuleNotFoundError: No module named 'ytmusicapi.auth.oauth'"
**Problem:** Old ytmusicapi version  
**Solution:** Update dependencies:
```powershell
pip install --upgrade ytmusicapi
```

### Error: "Client ID not found" or credentials not loading
**Problem:** .env file not updated or not being read  
**Solution:** 
1. Verify .env file has new credentials (Step 2)
2. No quotes around values
3. No spaces around `=`
4. File saved properly

## Quick Checklist

Before running the app, verify:

- [ ] Created NEW OAuth credentials with type "TVs and Limited Input devices"
- [ ] Copied Client ID to .env file (YOUTUBE_CLIENT_ID)
- [ ] Copied Client Secret to .env file (YOUTUBE_CLIENT_SECRET)
- [ ] Deleted old youtube_oauth.json token file
- [ ] Added your Google account as test user in OAuth consent screen
- [ ] Added YouTube scope (https://www.googleapis.com/auth/youtube)
- [ ] YouTube Data API v3 is enabled
- [ ] Saved all files

## Need Help?

If you're still having issues after completing ALL steps above:

1. **Check the detailed guide:** `YOUTUBE_OAUTH_REWRITE_COMPLETE.md`
2. **Check credentials setup:** `CREDENTIALS_SETUP.md`
3. **Verify your OAuth client type:** Must say "TVs and Limited Input devices"
4. **Verify .env file:** Check for typos, extra spaces, or quotes
5. **Check logs:** Look for error messages in the terminal output

## Summary

**Critical Actions:**
1. ✅ Create new OAuth credentials (type: "TVs and Limited Input devices")
2. ✅ Update .env with new Client ID and Secret
3. ✅ Delete old youtube_oauth.json
4. ✅ Add test user in OAuth consent screen
5. ✅ Add YouTube scope
6. ✅ Enable YouTube Data API v3
7. ✅ Run application and complete device code flow

**Do NOT skip any steps!** Each one is required for the new authentication to work.
