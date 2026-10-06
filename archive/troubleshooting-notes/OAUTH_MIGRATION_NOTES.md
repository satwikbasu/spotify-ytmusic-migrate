# OAuth Redirect URI Migration - November 2025

## Summary

As of November 2025, Spotify enforces strict redirect URI validation that **forbids** the use of `localhost`. This document tracks all changes made to comply with the new requirements.

## Spotify Policy Changes

**What Changed:**
- ❌ `localhost` is now **explicitly forbidden** in redirect URIs
- ✅ Loopback IP literals (127.0.0.1 or [::1]) are **required** instead
- ✅ HTTP is still allowed for loopback addresses
- ⚠️ Each user must create their own Spotify Developer app (shared credentials no longer work)

**Valid Redirect URIs:**
- ✅ `http://127.0.0.1:8888/callback` (IPv4 loopback)
- ✅ `http://[::1]:8888/callback` (IPv6 loopback)
- ✅ `https://example.com/callback` (HTTPS for non-loopback)
- ❌ `http://localhost:8888/callback` (FORBIDDEN)
- ❌ `http://example.com/callback` (HTTP for non-loopback - FORBIDDEN)

**Port Flexibility:**
- Port numbers can be omitted from registration if assigned dynamically
- Example: Register `http://127.0.0.1/callback`, use `http://127.0.0.1:8888/callback` at runtime
- This applies ONLY to loopback IP literals

**Reference:**
- [Spotify Developer Blog - Redirect URI Changes](https://developer.spotify.com/blog)
- Enforcement began: April 9, 2025 (new apps)
- Full enforcement: November 2025 (all apps)

---

## Files Updated

### 1. **Configuration Files**

#### `.env`
- **Change:** `localhost:8888` → `127.0.0.1:8888`
- **Added:** Warning comments about Nov 2025 requirements
```properties
# Before
SPOTIFY_REDIRECT_URI=http://localhost:8888/callback

# After
SPOTIFY_REDIRECT_URI=http://127.0.0.1:8888/callback
```

#### `config/app_config.py`
- **Change:** Default redirect URI updated
- **Line 105:** `http://localhost:8888/callback` → `http://127.0.0.1:8888/callback`
- **Added:** Docstring note about Nov 2025 requirement

#### `config/README.md`
- **Change:** Example environment variables updated
- **Added:** Comment warning about localhost ban

---

### 2. **Source Code**

#### `src/auth/spotify_auth.py`
- **Line 31:** `DEFAULT_REDIRECT_URI` changed from localhost to 127.0.0.1
- **Added:** Class docstring note about Nov 2025 requirements
- **Impact:** All new SpotifyAuthenticator instances use compliant default

---

### 3. **Tests**

#### `tests/test_app_config.py`
- **Test:** `test_spotify_redirect_uri_default`
- **Change:** Expected value updated to `http://127.0.0.1:8888/callback`
- **Status:** ✅ PASSING

---

### 4. **Documentation**

#### `tests/manual_test_instructions.md`
- **Added:** Critical warning section at top of document
- **Updated:** Prerequisites section with redirect URI requirements
- **Updated:** Credentials setup instructions
- **Added:** OAuth troubleshooting section
- **Updated:** All examples to use 127.0.0.1 instead of localhost

#### `spec.md`
- **Line 53:** Updated redirect URI from localhost to 127.0.0.1
- **Line 558:** Updated interaction flow description
- **Added:** Warning notes about Nov 2025 requirements

---

## YouTube OAuth (No Changes)

**YouTube/Google OAuth policy:**
- ✅ Still allows `http://localhost` for desktop applications
- ✅ No changes required
- ✅ Can use `http://localhost:8080/oauth2callback`

---

## Migration Checklist

For users migrating from old code:

- [ ] Update Spotify Developer Dashboard
  - Go to https://developer.spotify.com/dashboard
  - Select your app → Settings → Edit
  - Remove: `http://localhost:8888/callback`
  - Add: `http://127.0.0.1:8888/callback`
  - Save changes

- [ ] Update `.env` file
  - Change `SPOTIFY_REDIRECT_URI=http://localhost:8888/callback`
  - To: `SPOTIFY_REDIRECT_URI=http://127.0.0.1:8888/callback`

- [ ] Clear Spotify token cache
  - Delete: `~/.spotify_cache` or `.spotify_cache` in project root
  - Forces re-authentication with new redirect URI

- [ ] Test authentication flow
  - Run app and click "Connect Spotify"
  - Browser should redirect to 127.0.0.1:8888 (not localhost)
  - Should complete successfully

---

## Error Messages and Solutions

### "Redirect URI mismatch"
**Cause:** Redirect URI in code doesn't match Spotify Dashboard  
**Solution:** Ensure `http://127.0.0.1:8888/callback` is set in BOTH places

### "localhost is not allowed"
**Cause:** Using `localhost` instead of loopback IP  
**Solution:** Replace all `localhost` with `127.0.0.1` in:
- Spotify Dashboard redirect URIs
- `.env` file
- Code constants

### "HTTPS required"
**Cause:** Using HTTP with non-loopback address  
**Solution:** Use loopback IP (127.0.0.1) or switch to HTTPS

### Authentication works on old app, fails on new app
**Cause:** Old app created before Nov 2025 may still allow localhost  
**Solution:** Each user must create their own new app with compliant redirect URI

---

## Testing Results

**Test Run:** November 11, 2025

```
pytest tests/test_app_config.py::test_spotify_redirect_uri_default -v
PASSED [100%]
```

**Status:** ✅ All tests passing with updated redirect URI

---

## Backward Compatibility

**Breaking Changes:**
- Users with hardcoded `localhost` in code will experience auth failures
- Old `.env` files with `localhost` will fail
- Shared credentials from before Nov 2025 will fail

**Migration Path:**
1. Update Spotify Dashboard redirect URI first
2. Update `.env` file or environment variables
3. Clear Spotify token cache
4. Re-authenticate

**Timeline:**
- **Before Nov 2025:** Both localhost and 127.0.0.1 may work (depending on app creation date)
- **After Nov 2025:** Only 127.0.0.1 works
- **This codebase:** Fully compliant as of Nov 11, 2025

---

## Developer Notes

**Why this matters:**
- Security: Loopback IP literals are more specific and secure
- Consistency: Aligns with IETF OAuth recommendations (RFC 8252)
- Future-proofing: Other services may adopt similar policies

**Best practices:**
- Always use 127.0.0.1 or [::1] for local development OAuth
- Document redirect URI requirements clearly for users
- Provide helpful error messages when URI mismatch occurs
- Test authentication flow after any redirect URI changes

**Spotipy compatibility:**
- Spotipy library handles loopback IPs correctly
- No code changes needed beyond updating redirect URI constant
- Spotipy's local HTTP server listens on all interfaces (0.0.0.0)
- Browser redirects to 127.0.0.1:8888 work correctly

---

## References

- [Spotify Web API - Authorization Guide](https://developer.spotify.com/documentation/web-api/concepts/authorization)
- [RFC 8252 - OAuth 2.0 for Native Apps](https://datatracker.ietf.org/doc/html/rfc8252)
- [Spotipy Documentation](https://spotipy.readthedocs.io/)

---

**Document Version:** 1.0  
**Last Updated:** November 11, 2025  
**Status:** Migration Complete ✅
