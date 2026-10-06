# YouTube Music Browser Authentication Setup

## Why Browser Authentication?

**OAuth authentication is NOT working** because ytmusicapi uses YouTube Music's internal/unofficial API, which rejects the official OAuth tokens. 

**Browser authentication** uses your actual browser cookies and headers, which YouTube Music accepts.

## Step-by-Step Instructions

### 1. Open YouTube Music in Firefox
- Go to https://music.youtube.com
- Make sure you're **logged in** to your YouTube Music account

### 2. Open Firefox Developer Tools
- Press `F12` or right-click → "Inspect"
- Click the **"Network"** tab

### 3. Navigate to Browse Page
- In YouTube Music, click **"Home"** or **"Library"** in the left sidebar
- This will trigger a network request

### 4. Find the Browse Request
- In the Network tab, look for a request named **"browse"** or **"browse?**"
- The URL should look like: `https://music.youtube.com/youtubei/v1/browse?...`
- Click on this request

### 5. Copy Request Headers
- In the request details (right panel), click **"Headers"** tab
- Find **"Request Headers"** section (NOT Response Headers)
- Click the **"Raw"** button or right-click the headers section
- Select **"Copy All"** or manually copy ALL the request headers

The headers should look like:
```
POST /youtubei/v1/browse?... HTTP/2
Host: music.youtube.com
User-Agent: Mozilla/5.0...
Accept: */*
Accept-Language: en-US,en;q=0.5
Content-Type: application/json
x-goog-authuser: 0
x-goog-visitor-id: ...
Authorization: SAPISIDHASH ...
cookie: __Secure-1PSID=...; __Secure-1PAPISID=...; ...
...
```

### 6. Run ytmusicapi Setup
```powershell
ytmusicapi browser
```

- When prompted, **paste ALL the headers** you copied
- Press `Enter`
- Then press `Ctrl+Z` and `Enter` (Windows) to finish

This creates `browser.json` with your authentication.

### 7. Test Browser Authentication
```powershell
python test_browser_auth.py
```

If successful, you'll see:
```
✅ YTMusic client created successfully
✅ Search works: Found X results
✅ Account info works: Your Name
✅ Library playlists work: Found X playlists
🎉 ALL TESTS PASSED - Browser auth works!
```

## Troubleshooting

### Error: "Missing entries: x-goog-authuser, cookie"
- Make sure you're **logged in** to YouTube Music
- Use a **browse** request (not search or other endpoints)
- Copy **ALL** headers including cookie

### Error: "Invalid response received"
- Your session may have expired
- Re-do the setup with fresh headers
- Make sure you copied the complete cookie

### Still Not Working?
Try using **Chrome** instead of Firefox:
1. Open Chrome DevTools (F12)
2. Network tab → Find browse request
3. Right-click the request → Copy → Copy as cURL
4. Extract the headers from the cURL command

## Why This Works

- **OAuth**: Uses official YouTube Data API v3 tokens → Rejected by YouTube Music's internal API
- **Browser auth**: Uses your actual browser session cookies → Accepted by YouTube Music

Browser authentication is **recommended** for ytmusicapi and is more reliable than OAuth.

## Security Note

The `browser.json` file contains your YouTube Music session cookies. Keep it secure:
- Don't commit to Git (already in .gitignore)
- Don't share the file
- Regenerate if compromised

The session will eventually expire (usually after several weeks/months). When it does, just re-run the setup.
