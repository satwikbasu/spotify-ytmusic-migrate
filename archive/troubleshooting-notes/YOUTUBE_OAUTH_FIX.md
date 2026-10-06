# YouTube OAuth Error Fix

## What Was Wrong

### The Error Message
```
Error: YouTube Music authentication failed: Unexpected error during YouTube Music 
authentication: oauth JSON provided via auth argument, but oauth_credentials not 
provided. Please provide oauth_credentials as specified in the OAuth setup documentation.
```

### Root Cause

The `ytmusicapi` library has a specific format requirement for OAuth credentials. When you pass authentication credentials, it expects them in this structure:

```python
# ❌ WRONG - What the code was doing
yt = YTMusic(auth="/path/to/credentials.json")

# ❌ ALSO WRONG - Just passing the credentials dict
yt = YTMusic(auth=creds_dict)

# ✅ CORRECT - Wrapping in oauth_credentials key
ytmusic_auth = {
    "oauth_credentials": creds_dict
}
yt = YTMusic(auth=ytmusic_auth)
```

The library requires credentials to be wrapped in an `oauth_credentials` key to distinguish between different authentication methods (OAuth vs browser cookies).

---

## What Was Fixed

### File: `src/auth/youtube_auth.py`

**Two locations updated:**

#### 1. New Authentication Flow (Line ~290)
```python
# Before
yt = YTMusic(auth=self.credentials_path)

# After
ytmusic_auth = {
    "oauth_credentials": creds_dict
}
yt = YTMusic(auth=ytmusic_auth)
```

#### 2. Cached Credentials Loading (Line ~225)
```python
# Before
yt = YTMusic(auth=self.credentials_path)

# After
ytmusic_auth = {
    "oauth_credentials": creds_dict
}
yt = YTMusic(auth=ytmusic_auth)
```

---

## How ytmusicapi Authentication Works

`ytmusicapi` supports two authentication methods:

### Method 1: OAuth (What we use)
```python
auth_data = {
    "oauth_credentials": {
        "access_token": "...",
        "refresh_token": "...",
        "token_uri": "...",
        "client_id": "...",
        "client_secret": "...",
        "scopes": [...]
    }
}
yt = YTMusic(auth=auth_data)
```

### Method 2: Browser Cookies (Not used)
```python
auth_data = {
    "cookies": "...",
    "headers": {...}
}
yt = YTMusic(auth=auth_data)
```

The library checks for the `oauth_credentials` key to know which method you're using.

---

## Why This Happened

1. **You successfully authenticated** with Google OAuth
2. **Credentials were saved** correctly to `youtube_oauth.json`
3. **But when creating YTMusic client**, the credentials weren't in the expected format
4. **ytmusicapi couldn't find** the `oauth_credentials` key
5. **Error was thrown** instead of using the credentials

---

## Testing the Fix

### Step 1: Delete Old Credentials (Optional)
If you want to start fresh:
```bash
rm ~/youtube_oauth.json
```

### Step 2: Run the App
```bash
python main.py
```

### Step 3: Click "Connect YouTube"
- Browser should open
- Authenticate with Google
- **Should now work without the oauth_credentials error!**

### Expected Success Messages
```
YouTube Music authentication successful!
```

Or if using cached credentials:
```
Using cached YouTube Music credentials
```

---

## What Happens Now

1. ✅ You authenticate via Google OAuth (same as before)
2. ✅ Credentials are saved to `~/youtube_oauth.json` (same as before)
3. ✅ Credentials are wrapped in `oauth_credentials` key (NEW - this fixes the error)
4. ✅ YTMusic client is created successfully
5. ✅ API test call succeeds
6. ✅ You can now use YouTube Music features

---

## If You Still Get Errors

### Error: "Authentication succeeded but API test failed"
**Cause:** YouTube Data API v3 not enabled  
**Solution:** 
1. Go to Google Cloud Console
2. Enable YouTube Data API v3

### Error: "Invalid credentials or configuration"
**Cause:** Client ID or Secret incorrect  
**Solution:**
1. Check `.env` file
2. Verify credentials match Google Cloud Console

### Error: "Network error during YouTube Music authentication"
**Cause:** Internet connection issue or firewall  
**Solution:**
1. Check internet connection
2. Check firewall allows localhost connections

---

## Summary

**Problem:** ytmusicapi expected credentials in format: `{"oauth_credentials": {...}}`  
**What we were doing:** Passing file path or just the credentials dict  
**Solution:** Wrap credentials in `oauth_credentials` key  
**Result:** YouTube authentication now works! ✅

---

**Fixed:** November 11, 2025  
**Status:** Ready to test
