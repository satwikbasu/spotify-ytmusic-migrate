# Configuration Module

This module contains all application-wide configuration constants for the Spotify to YouTube Music Migrator.

## Usage

### Import Constants

```python
from config import (
    WINDOW_WIDTH,
    WINDOW_HEIGHT,
    SPOTIFY_GREEN,
    YOUTUBE_RED,
    DEFAULT_MATCH_THRESHOLD
)
```

### Setup Application Directories

```python
from config import ensure_app_directories

# Create necessary directories on startup
ensure_app_directories()
```

### Validate API Credentials

```python
from config import validate_credentials

result = validate_credentials()
if not result['all_valid']:
    print(f"Missing credentials: {', '.join(result['missing'])}")
```

### Get Configuration Summary

```python
from config import get_config_summary

summary = get_config_summary()
print(f"Cache DB: {summary['paths']['cache_db']}")
print(f"Match threshold: {summary['migration']['match_threshold']}")
```

## Environment Variables

Set these environment variables for API credentials:

```bash
# Spotify API (from https://developer.spotify.com/dashboard)
export SPOTIFY_CLIENT_ID="your_spotify_client_id"
export SPOTIFY_CLIENT_SECRET="your_spotify_client_secret"
export SPOTIFY_REDIRECT_URI="http://localhost:8888/callback"

# YouTube API (from https://console.cloud.google.com/)
export YOUTUBE_CLIENT_ID="your_youtube_client_id"
export YOUTUBE_CLIENT_SECRET="your_youtube_client_secret"

# Optional: Set log level
export LOG_LEVEL="DEBUG"  # DEBUG, INFO, WARNING, ERROR, CRITICAL
```

On Windows (PowerShell):
```powershell
$env:SPOTIFY_CLIENT_ID="your_spotify_client_id"
$env:SPOTIFY_CLIENT_SECRET="your_spotify_client_secret"
# ... etc
```

## Configuration Categories

### Window Settings
- `WINDOW_WIDTH` (800px)
- `WINDOW_HEIGHT` (600px)
- `WINDOW_RESIZABLE` (False)
- `WINDOW_TITLE`

### Colors
Material Design palette with Spotify/YouTube branding:
- `PRIMARY_COLOR` - Material Blue
- `SPOTIFY_GREEN` - Spotify brand color
- `YOUTUBE_RED` - YouTube brand color
- `SUCCESS_COLOR` - Material Green
- `WARNING_COLOR` - Material Orange
- `ERROR_COLOR` - Material Red
- `TEXT_COLOR_LIGHT` / `TEXT_COLOR_DARK`
- `BACKGROUND_LIGHT` / `BACKGROUND_DARK`

### Typography
- `HEADING_SIZE_LARGE` (32px)
- `HEADING_SIZE_MEDIUM` (24px)
- `HEADING_SIZE_SMALL` (20px)
- `BODY_SIZE` (16px)
- `CAPTION_SIZE` (14px)

### Paths
All paths are relative to `~/.playlist_migrator`:
- `APP_DATA_DIR` - Main application directory
- `CACHE_DB_PATH` - SQLite database
- `LOG_FILE_PATH` - Application logs
- `CREDENTIALS_DIR` - OAuth tokens
- `SPOTIFY_TOKEN_PATH` - Spotify token cache
- `YOUTUBE_TOKEN_PATH` - YouTube token cache

### Migration Settings
- `DEFAULT_MATCH_THRESHOLD` (75) - Fuzzy matching threshold (0-100)
- `MAX_CONCURRENT_MIGRATIONS` (1) - Max simultaneous migrations
- `ENABLE_DESKTOP_NOTIFICATIONS` (True)
- `AUTO_RESUME_INCOMPLETE` (True) - Resume on startup

### Rate Limiting
- `YOUTUBE_DAILY_QUOTA` (10000) - YouTube API daily limit
- `YOUTUBE_REQUESTS_PER_MINUTE` (100)
- `SEARCH_DELAY_SECONDS` (1.0)

### Cache
- `CACHE_EXPIRY_DAYS` (30) - Days before cache expires
- `CLEAR_OLD_JOBS_DAYS` (30) - Days before old jobs cleared

### Logging
- `LOG_LEVEL` - Logging verbosity
- `LOG_FORMAT` - Log message format
- `LOG_MAX_BYTES` (10MB) - Max log file size
- `LOG_BACKUP_COUNT` (5) - Rotated log files to keep

## Testing

Run tests with:
```bash
pytest tests/test_app_config.py -v
```

Coverage:
```bash
pytest tests/test_app_config.py --cov=config --cov-report=term-missing
```
