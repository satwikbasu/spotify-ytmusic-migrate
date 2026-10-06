# Manual Integration Testing Instructions

## 🚨 CRITICAL: OAuth Changes (November 2025)

**Spotify Policy Update:**
- Each user MUST create their own Spotify Developer app
- Shared credentials NO LONGER WORK
- **`localhost` is BANNED** - Use `127.0.0.1` or `[::1]` instead
- HTTP loopback addresses (127.0.0.1) still work IF you create your own app
- HTTPS required for non-loopback URIs

**Redirect URI Rules (Spotify):**
- ✅ `http://127.0.0.1:8888/callback` - ALLOWED (loopback IPv4)
- ✅ `http://[::1]:8888/callback` - ALLOWED (loopback IPv6)
- ✅ `https://example.com/callback` - ALLOWED (HTTPS)
- ❌ `http://localhost:8888/callback` - **FORBIDDEN**
- ❌ `http://example.com/callback` - FORBIDDEN (HTTP non-loopback)

**YouTube Policy:**
- NO CHANGES - HTTP localhost still fully supported
- Works exactly as before

**For Testers:**
- Plan 5-10 extra minutes for first-time credential setup
- You cannot share credentials with other testers
- **MUST use `127.0.0.1` instead of `localhost` for Spotify**
- This is a ONE-TIME setup per tester/machine

---

## Prerequisites

### Account Setup
1. **Create Spotify test account** (or use existing)
2. **Create 2 small public playlists** (5-10 songs each)
   - Playlist 1: Mix of popular songs (e.g., Top 40 hits)
   - Playlist 2: Mix of indie/less common songs
3. **Set up Spotify API credentials**
   - Go to https://developer.spotify.com/dashboard
   - Create a new app
   - Note down Client ID and Client Secret
   - **IMPORTANT:** As of November 2025, Spotify enforces strict redirect URI validation
   - **Redirect URI Requirements:**
     * ✅ **Recommended:** `http://127.0.0.1:8888/callback` (loopback IPv4 literal - COMPLIANT)
     * ✅ **Alternative:** `http://[::1]:8888/callback` (loopback IPv6 literal - COMPLIANT)
     * ❌ **NOT ALLOWED:** `http://localhost:8888/callback` (localhost is explicitly forbidden)
     * ⚠️ Port numbers can be omitted in redirect URI registration if assigned dynamically (e.g., `http://127.0.0.1/callback`)
     * ℹ️ HTTPS is required for non-loopback URIs (e.g., `https://example.com/callback`)
   - ⚠️ **You MUST create your own Spotify app - shared credentials no longer work**
   - 📖 **Reference:** [Spotify Developer Blog - Redirect URI Changes](https://developer.spotify.com/blog)
4. **Set up YouTube/Google API credentials**
   - Go to https://console.cloud.google.com/
   - Enable YouTube Data API v3
   - Create OAuth 2.0 credentials
   - Redirect URI: `http://localhost:8080` or `http://localhost:8080/oauth2callback`
   - ✅ **YouTube allows HTTP localhost for desktop apps - no HTTPS required**
   - Download client secrets JSON file
5. **Have a YouTube account** for testing (existing Google account works)

### Credentials Setup

Since each user must create their own API credentials:

**Option A: Use First-Time Setup Wizard (Recommended)**
1. Launch app → Follow on-screen instructions to get credentials
2. App saves credentials securely (encrypted)
3. This is a ONE-TIME setup

**Option B: Manual Environment Variables (Advanced)**

Set environment variables before launching:
```powershell
$env:SPOTIFY_CLIENT_ID="your_client_id"
$env:SPOTIFY_CLIENT_SECRET="your_client_secret"
$env:SPOTIFY_REDIRECT_URI="http://127.0.0.1:8888/callback"
$env:YOUTUBE_CLIENT_ID="your_client_id"
$env:YOUTUBE_CLIENT_SECRET="your_client_secret"
```

Or create `.env` file in project root:
```
SPOTIFY_CLIENT_ID=your_client_id
SPOTIFY_CLIENT_SECRET=your_client_secret
SPOTIFY_REDIRECT_URI=http://127.0.0.1:8888/callback
YOUTUBE_CLIENT_ID=your_client_id
YOUTUBE_CLIENT_SECRET=your_client_secret
```

⚠️ **CRITICAL:** Use `http://127.0.0.1:8888/callback` (NOT `localhost`) - Spotify blocks `localhost` as of Nov 2025

**Important Notes:**
- ⚠️ Each tester must use their OWN credentials
- ⚠️ DO NOT share credentials between testers (violates ToS)
- ⚠️ Spotify credentials from before Nov 2025 may not work
- Place YouTube OAuth credentials in project root as `client_secrets.json` (if using manual setup)

### Environment Setup
1. Clear any existing cache: Delete `~/.playlist_migrator/` folder manually (PowerShell: `Remove-Item -Recurse -Force "$env:USERPROFILE\.playlist_migrator"`)
2. Ensure Python 3.13+ and all dependencies installed (`pip install -r requirements.txt`)

---

## Test Scenarios

### Scenario 1: Happy Path Migration

**Objective:** Verify complete end-to-end migration flow works correctly.

**Steps:**
0. **First-Time Setup (if not done):**
   - Click "Setup API Credentials" in welcome screen
   - Follow wizard to create Spotify Developer app
   - Follow wizard to create Google Cloud project
   - Save credentials when prompted
   - This is a ONE-TIME setup per tester
1. Launch app: `python main.py`
2. **Welcome Screen:** Click "Get Started"
3. **Authentication:**
   - Click "Connect Spotify" → authenticate in browser
   - Click "Connect YouTube Music" → authenticate in browser
   - Verify both services show green "Connected" status
4. **Playlist Selection:**
   - Verify playlists loaded correctly from Spotify
   - Select both test playlists (use checkboxes)
   - Click "Start Migration"
5. **Progress Screen:**
   - Observe progress bars updating in real-time
   - Watch track count incrementing
   - Verify percentage updates
6. **Completion:**
   - Wait for "Migration Complete" message
   - Check desktop notification appears
7. **Verification on YouTube Music:**
   - Open YouTube Music in browser
   - Navigate to Library → Playlists
   - Verify both playlists exist with correct names
   - Spot-check 3-5 songs in each playlist for accuracy
8. **Report Review:**
   - Click "View Report" or "Export Report"
   - Review match accuracy, failed tracks, processing time
   - Save report for records

**Expected Results:**
- ✅ Both playlists migrated successfully
- ✅ Match rate >90% for popular songs
- ✅ No crashes or unhandled errors
- ✅ Desktop notification received
- ✅ Progress updates smooth and accurate
- ✅ Report shows detailed statistics

**Common Issues:**
- ❌ Authentication fails → Check credentials in `.env` and `client_secrets.json`
- ❌ Playlists don't appear → Verify Spotify account has public playlists
- ❌ Low match rate → Expected for obscure songs, check report for details

### OAuth & Credential Issues

**"Redirect URI mismatch" error (Spotify):**
- Cause: The redirect URI in your Spotify app dashboard doesn't match the one in code
- Fix: Go to Spotify Dashboard → Settings → Edit → Add exact URI: `http://127.0.0.1:8888/callback`
- ⚠️ **CRITICAL:** Do NOT use `localhost` - it's forbidden as of Nov 2025
- ✅ Use `http://127.0.0.1:8888/callback` (IPv4 loopback) instead
- Note: Copy-paste exactly, no trailing slashes, include port number

**"Invalid client" error:**
- Cause: Client ID or Secret is incorrect
- Fix: Double-check credentials in Spotify/Google dashboards
- Tip: Use copy-paste, don't type manually

**"HTTPS required" error (Spotify):**
- Cause: Using old shared credentials OR using `localhost` instead of loopback IP
- Fix #1: Replace `localhost` with `127.0.0.1` in redirect URI everywhere
- Fix #2: Create your own Spotify Developer app with your own credentials
- Workaround: Not possible - must use compliant redirect URI

**"localhost is not allowed" error (Spotify):**
- Cause: Using `http://localhost:8888/callback` (explicitly forbidden since Nov 2025)
- Fix: Change to `http://127.0.0.1:8888/callback` in:
  1. Spotify Dashboard → App Settings → Redirect URIs
  2. Your `.env` file or environment variables
  3. Code that constructs OAuth URLs
- Why: Spotify enforces loopback IP literals (127.0.0.1 or [::1]) instead of localhost

**YouTube authentication works, Spotify fails:**
- This is expected if you haven't created your own Spotify app OR using `localhost`
- YouTube allows HTTP localhost, Spotify requires loopback IPs (127.0.0.1)
- Solution #1: Follow Credentials Setup Wizard in app
- Solution #2: Change all `localhost` to `127.0.0.1` in Spotify configs

**Browser doesn't redirect back to app:**
- Check firewall isn't blocking localhost ports (8888 for Spotify, 8080 for YouTube)
- Try closing all browser tabs and retrying
- On Windows: Check Windows Defender firewall rules

---

### Scenario 2: Network Interruption

**Objective:** Verify app handles network interruptions gracefully.

**Steps:**
1. Start migration with a 20+ song playlist
2. After 5 tracks successfully migrated, **disable network:**
   - Windows: Disable Wi-Fi adapter or unplug Ethernet
   - Use `ipconfig /release` in PowerShell (run as admin)
3. Observe app behavior:
   - Should show error banner/message
   - Progress should pause (not crash)
4. Wait 10 seconds
5. **Re-enable network:**
   - Windows: Enable Wi-Fi or plug Ethernet back in
   - Use `ipconfig /renew` in PowerShell
6. Observe app behavior:
   - Should automatically detect network restored
   - Should resume migration from where it stopped
7. Let migration complete
8. **Verify on YouTube Music:**
   - Check playlist for duplicate tracks
   - Count should match Spotify playlist

**Expected Results:**
- ✅ Graceful pause on network loss (no crash)
- ✅ Clear error message displayed to user
- ✅ Automatic resume within 30 seconds of network restoration
- ✅ No duplicate tracks added
- ✅ Progress state preserved correctly

**Common Issues:**
- ❌ App crashes → Report bug with logs
- ❌ Duplicates added → Cache issue, check logs

---

### Scenario 3: Large Playlist Performance Test

**Objective:** Verify app performance with large datasets.

**Steps:**
1. **Preparation:**
   - Create or use playlist with **500+ songs**
   - If creating, use Spotify's "Discover Weekly" or "Liked Songs" as source
2. **Launch app** and authenticate both services
3. Select the large playlist
4. **Before starting migration, open Task Manager (Windows) or Activity Monitor (Mac):**
   - Note baseline memory usage
   - Note baseline CPU usage
5. Click "Start Migration"
6. **Monitor during migration (every 5 minutes):**
   - **Memory usage:** Should stay below 500MB total
   - **CPU usage:** Should stay below 50% average
   - **UI responsiveness:** Click around UI, check if laggy
   - **Progress updates:** Should update smoothly
7. **Minimize app** to system tray after 10 minutes
8. **Wait 5 minutes**, then restore app
9. Let migration complete (may take 30-60 minutes)
10. **After completion:**
    - Check final memory usage
    - Verify playlist on YouTube Music

**Expected Results:**
- ✅ No crashes or hangs
- ✅ Memory usage stays <500MB (ideally <300MB)
- ✅ CPU usage stays <50% average
- ✅ UI remains responsive throughout
- ✅ Can minimize to tray and continue in background
- ✅ Progress updates regularly (every 2-3 seconds)
- ✅ Rate limiting respected (no API quota errors)

**Performance Benchmarks:**
- Processing speed: ~15-30 tracks/minute (with rate limiting)
- Memory growth: <50MB per 100 tracks
- UI refresh rate: <100ms response time

**Common Issues:**
- ❌ Excessive memory → Check for memory leaks in logs
- ❌ API quota exceeded → Rate limiter not working, check settings
- ❌ UI freezes → Threading issue, report bug

---

### Scenario 4: Crash Recovery

**Objective:** Verify app can recover from unexpected termination.

**Steps:**
1. Start migration with 50+ song playlist
2. After **20 tracks** successfully migrated (watch counter):
   - **Windows:** Open Task Manager → Find `python.exe` process → "End Task"
   - **Mac/Linux:** Find PID with `ps aux | grep python` → `kill -9 <PID>`
3. Wait 5 seconds
4. **Restart app:** `python main.py`
5. Navigate to playlist selection screen
6. Select the **same playlist** you were migrating
7. Observe if:
   - Resume prompt appears: "Found incomplete migration, resume?"
   - Or app starts fresh
8. **If resume prompt appears:**
   - Click "Resume"
   - Verify continues from track ~20 (not from beginning)
9. **If no resume prompt:**
   - Check YouTube Music manually for partial playlist
   - Note down track count
   - Let migration complete
10. **Final verification:**
    - Check YouTube Music playlist
    - Count tracks (should match Spotify, no duplicates)

**Expected Results:**
- ✅ Resume prompt appears on restart
- ✅ Continues from where it left off (~track 20)
- ✅ No duplicate tracks added
- ✅ Cache state correctly restored
- ✅ Migration completes successfully

**Alternative Expected Behavior (if resume not implemented):**
- ⚠️ App starts fresh migration
- ⚠️ Duplicate tracks may be added (this is acceptable for MVP)
- ✅ No crashes on restart

**Common Issues:**
- ❌ Corrupted cache → Delete `~/.playlist_migrator/cache.db` and retry
- ❌ Duplicates added → Resume feature not fully working

---

### Scenario 5: Edge Cases and Special Characters

**Objective:** Verify app handles unusual input gracefully.

**Steps:**
1. **Create test playlists with edge cases:**

   **Playlist A: "Special Characters Test 🎵🎶"**
   - Songs with emojis in titles
   - Songs with accents: "Café Tacvba", "Björk"
   - Songs with special chars: "AC/DC", "Ke$ha"
   - Very long song names (60+ characters)

   **Playlist B: "International Test"**
   - Japanese songs: "初音ミク - Miku Hatsune"
   - Arabic songs: "أم كلثوم - Umm Kulthum"
   - Korean K-pop songs
   - Russian songs (Cyrillic)

   **Playlist C: "Duplicates & Unavailable"**
   - Same song added 3 times
   - Very obscure indie songs
   - Songs likely not on YouTube Music
   - Extremely long playlist name (100+ characters)

2. **Migrate each playlist separately**
3. **For each playlist, observe:**
   - Any encoding errors in UI?
   - Any crashes during search?
   - How are duplicates handled?
   - Are error messages clear for unavailable songs?

4. **Verification:**
   - Check YouTube Music playlists
   - Verify special characters display correctly
   - Check report for failed tracks
   - Verify playlist names preserved correctly

**Expected Results:**
- ✅ Special characters display correctly in UI
- ✅ Playlist names with emojis/accents preserved
- ✅ International songs searched correctly
- ✅ Duplicate songs handled (added once or multiple times - both acceptable)
- ✅ Clear error messages for unavailable songs
- ✅ No crashes or encoding errors
- ✅ Report shows which tracks failed and why

**Acceptable Outcomes:**
- ⚠️ Lower match rate for non-English songs (expected)
- ⚠️ Very obscure songs may fail to match (expected)
- ⚠️ Emojis in playlist names may be stripped (acceptable)

**Common Issues:**
- ❌ UnicodeDecodeError → Encoding issue, report bug
- ❌ Crash on duplicate → Report bug with logs
- ❌ Blank error messages → Need better error handling

---

## Additional Test Cases

### Scenario 6: Empty and Single-Song Playlists

**Steps:**
1. Create empty playlist
2. Create playlist with only 1 song
3. Attempt to migrate both

**Expected:**
- ✅ Empty playlist: Clear message "No tracks to migrate"
- ✅ Single song: Migrates successfully
- ✅ No crashes

---

### Scenario 7: Authentication Expiry

**Steps:**
1. Authenticate Spotify and YouTube
2. Wait 1 hour (or manually revoke tokens)
3. Attempt migration

**Expected:**
- ✅ Detects expired token
- ✅ Prompts re-authentication
- ✅ Continues after re-auth

---

### Scenario 8: Concurrent Migrations

**Steps:**
1. Start migration of Playlist A
2. Attempt to start migration of Playlist B while A is running

**Expected:**
- ✅ Either: Second migration queued
- ✅ Or: Error message "Migration in progress"
- ✅ No data corruption

---

## Testing Checklist

### Functional Tests
- [ ] **Scenario 1:** Happy path migration (both playlists)
- [ ] **Scenario 2:** Network interruption recovery
- [ ] **Scenario 3:** Large playlist performance (500+ songs)
- [ ] **Scenario 4:** Crash recovery
- [ ] **Scenario 5:** Edge cases (special chars, international)
- [ ] **Scenario 6:** Empty/single-song playlists
- [ ] **Scenario 7:** Authentication expiry
- [ ] **Scenario 8:** Concurrent migrations

### UI/UX Tests
- [ ] Welcome screen displays correctly
- [ ] Authentication flow intuitive
- [ ] Playlist selection UI responsive
- [ ] Progress bars update smoothly
- [ ] Settings screen accessible and functional
- [ ] Report screen displays accurate data
- [ ] Desktop notifications work

### Performance Tests
- [ ] Memory usage <500MB for large playlists
- [ ] CPU usage <50% average
- [ ] UI responsive during migration
- [ ] No memory leaks over time
- [ ] Rate limiting working (no quota errors)

### Error Handling Tests
- [ ] Network errors handled gracefully
- [ ] API errors show helpful messages
- [ ] File I/O errors caught
- [ ] Invalid input handled
- [ ] Logs captured for debugging

### Cross-Platform Tests (if applicable)
- [ ] Windows 10/11
- [ ] macOS (Intel)
- [ ] macOS (Apple Silicon)
- [ ] Linux (Ubuntu/Debian)

---

## Bug Report Template

If you encounter issues during testing, please document using this template:

```markdown
### Bug Report

**Bug ID:** BUG-YYYYMMDD-001

**Severity:** [Critical / High / Medium / Low]
- Critical: App crashes, data loss
- High: Feature broken, workaround exists
- Medium: Minor feature issue
- Low: Cosmetic issue

**Test Scenario:** [e.g., Scenario 3: Large Playlist]

**Steps to Reproduce:**
1. Step 1
2. Step 2
3. Step 3

**Expected Behavior:**
What should happen...

**Actual Behavior:**
What actually happened...

**Screenshots:**
[Attach screenshots if applicable]

**Environment:**
- OS: Windows 11 Pro 23H2
- Python: 3.13.5
- App Version: [Check version in app]
- Date/Time: 2025-11-11 14:30 EST

**Logs:**
```
[Paste relevant logs from ~/.playlist_migrator/app.log]
```

**Additional Context:**
Any other relevant information...

**Workaround (if found):**
How to temporarily fix...
```

---

## Test Results Log

Use this template to track your testing session:

```markdown
## Test Session: YYYY-MM-DD

**Tester:** [Your Name]
**Duration:** [Start Time] - [End Time]
**Environment:** Windows 11, Python 3.13.5

**Credentials Used:**
- Spotify App Name: [Your Spotify Dev App Name]
- Google Project Name: [Your Google Cloud Project]
- Credential Owner: [Your email/identifier]

### Results Summary
- **Total Scenarios Tested:** X/8
- **Passed:** X
- **Failed:** X
- **Bugs Found:** X

### Scenario Results

#### Scenario 1: Happy Path
- **Status:** ✅ PASS / ❌ FAIL
- **Notes:** ...
- **Bugs:** [Link to bug reports if any]

#### Scenario 2: Network Interruption
- **Status:** ✅ PASS / ❌ FAIL
- **Notes:** ...

[Continue for all scenarios...]

### Overall Assessment
- **Ready for Release?** YES / NO / WITH CAVEATS
- **Confidence Level:** High / Medium / Low
- **Blocker Issues:** [List critical bugs]
- **Recommendations:** [Any suggestions]

```

---

## Performance Monitoring Tools

### Windows
```powershell
# Monitor Python process memory
Get-Process python | Select-Object Name, WS, CPU

# Continuous monitoring (every 5 seconds)
while($true) { 
    Get-Process python | Select-Object Name, @{N='MemoryMB';E={$_.WS/1MB}}, CPU 
    Start-Sleep 5 
}
```

### Log Analysis
Check logs at: `~/.playlist_migrator/app.log`
```powershell
# View last 50 lines
Get-Content -Path "$env:USERPROFILE\.playlist_migrator\app.log" -Tail 50

# Search for errors
Select-String -Path "$env:USERPROFILE\.playlist_migrator\app.log" -Pattern "ERROR"
```

---

## Post-Testing Cleanup

After completing all tests:

1. **Delete test playlists** from YouTube Music (optional)
2. **Clear cache:** Delete `~/.playlist_migrator/cache.db`
3. **Revoke API access:**
   - Spotify: https://www.spotify.com/account/apps/
   - Google: https://myaccount.google.com/permissions
4. **Archive test reports** and logs for reference
5. **Submit bug reports** if any found
6. **Update this document** with lessons learned

---

## Success Criteria

Testing is considered successful when:
- ✅ Each tester successfully created their own credentials
- ✅ OAuth flow works with user's own credentials
- ✅ No shared credentials being used
- ✅ All 8 scenarios pass without critical bugs
- ✅ No crashes during normal operation
- ✅ Performance within acceptable limits
- ✅ Error handling works as expected
- ✅ User experience is smooth and intuitive
- ✅ Reports are accurate and helpful
- ✅ Any bugs found are documented and prioritized

---

## Contact

For questions about testing or to report bugs:
- GitHub Issues: [Project Repository]
- Email: [Your Contact]
- Discord/Slack: [If applicable]

---

**Document Version:** 1.0  
**Last Updated:** 2025-11-11  
**Next Review:** Before each release
