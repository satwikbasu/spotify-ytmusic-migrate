# Quick Start - Credentials Setup

## Problem: "I don't have credentials configured" Error

If you see an error message saying credentials are not configured when you click "Connect Spotify" or "Connect YouTube", it means the app cannot find your API credentials.

## Solution

The app loads credentials from environment variables, which can be set in two ways:

### Option 1: Use .env File (Recommended)

1. **Create a `.env` file** in the project root (same folder as `main.py`)
2. **Add your credentials:**

```env
# Spotify API Credentials
SPOTIFY_CLIENT_ID=your_spotify_client_id
SPOTIFY_CLIENT_SECRET=your_spotify_client_secret
SPOTIFY_REDIRECT_URI=http://127.0.0.1:8888/callback

# YouTube API Credentials  
YOUTUBE_CLIENT_ID=your_youtube_client_id
YOUTUBE_CLIENT_SECRET=your_youtube_client_secret
```

3. **Save the file**
4. **Install python-dotenv** (if not already installed):
   ```bash
   pip install python-dotenv
   ```

5. **Run the app:**
   ```bash
   python main.py
   ```

The app will automatically load credentials from `.env` on startup.

### Option 2: Set Environment Variables Manually

**Windows (PowerShell):**
```powershell
$env:SPOTIFY_CLIENT_ID="your_spotify_client_id"
$env:SPOTIFY_CLIENT_SECRET="your_spotify_client_secret"
$env:SPOTIFY_REDIRECT_URI="http://127.0.0.1:8888/callback"
$env:YOUTUBE_CLIENT_ID="your_youtube_client_id"
$env:YOUTUBE_CLIENT_SECRET="your_youtube_client_secret"

python main.py
```

**macOS/Linux (Bash):**
```bash
export SPOTIFY_CLIENT_ID="your_spotify_client_id"
export SPOTIFY_CLIENT_SECRET="your_spotify_client_secret"
export SPOTIFY_REDIRECT_URI="http://127.0.0.1:8888/callback"
export YOUTUBE_CLIENT_ID="your_youtube_client_id"
export YOUTUBE_CLIENT_SECRET="your_youtube_client_secret"

python main.py
```

---

## Getting Your API Credentials

### Spotify Credentials

1. Go to https://developer.spotify.com/dashboard
2. Log in with your Spotify account
3. Click **"Create app"**
4. Fill in app details:
   - **App name:** "Playlist Migrator" (or any name)
   - **App description:** "Personal playlist migration tool"
   - **Redirect URI:** `http://127.0.0.1:8888/callback` ⚠️ (NOT localhost!)
5. Click **"Settings"** → Copy your **Client ID** and **Client Secret**

**IMPORTANT:** As of November 2025, Spotify requires:
- ✅ Use `127.0.0.1` (NOT `localhost`) in redirect URI
- ✅ Each user must create their own app (shared credentials don't work)

### YouTube Credentials

1. Go to https://console.cloud.google.com/
2. Create a new project or select existing
3. Enable **YouTube Data API v3**:
   - Go to APIs & Services → Library
   - Search "YouTube Data API v3"
   - Click Enable
4. Create OAuth credentials:
   - Go to APIs & Services → Credentials
   - Click **"Create Credentials"** → **"OAuth client ID"**
   - Application type: **Desktop app**
   - Name: "Playlist Migrator"
   - Redirect URI: `http://localhost:8080` (YouTube allows localhost)
5. Copy your **Client ID** and **Client Secret**

---

## Verify Credentials Are Loaded

After setting up credentials, verify they're loaded correctly:

```bash
python -c "from dotenv import load_dotenv; load_dotenv(); from config import app_config; result = app_config.validate_credentials(); print('All credentials valid:', result['all_valid'])"
```

**Expected output:**
```
All credentials valid: True
```

If you see `False`, check:
- ✅ `.env` file exists in project root
- ✅ No typos in credential names
- ✅ `python-dotenv` is installed
- ✅ Credentials are not empty strings

---

## Troubleshooting

### "Credentials not configured" error persists

**Cause:** `.env` file not found or not loaded

**Solutions:**
1. Check `.env` is in project root (same folder as `main.py`)
2. Install python-dotenv: `pip install python-dotenv`
3. Restart terminal/PowerShell after setting environment variables
4. Try absolute path: `python-dotenv` looks in current working directory

### "Spotify authentication failed"

**Cause:** Incorrect redirect URI

**Solution:** 
- Dashboard redirect URI: `http://127.0.0.1:8888/callback`
- .env file: `SPOTIFY_REDIRECT_URI=http://127.0.0.1:8888/callback`
- Both must match EXACTLY (no trailing slash)

### "YouTube authentication failed"

**Cause:** YouTube Data API v3 not enabled

**Solution:**
1. Go to Google Cloud Console
2. Select your project
3. APIs & Services → Library
4. Search "YouTube Data API v3"
5. Click "Enable"

---

## Security Notes

⚠️ **DO NOT commit `.env` to version control**

Add to `.gitignore`:
```
.env
```

⚠️ **Each user should create their own credentials**
- Do not share credentials between users (violates ToS)
- Each tester needs their own Spotify and YouTube apps

---

## Quick Test

After setup, test authentication:

```bash
python main.py
```

1. Click **"Connect Spotify"** → Browser should open
2. Authorize app → Browser redirects to `127.0.0.1:8888`
3. Should show "✅ Connected" in app
4. Click **"Connect YouTube"** → Same flow
5. Both connected → "Continue" button enabled

If both work, credentials are configured correctly! 🎉

---

**Last Updated:** November 11, 2025  
**Version:** 1.1
