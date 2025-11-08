"""Application configuration constants.

Defines all configuration constants for the Spotify to YouTube Music migrator:
- Window dimensions and appearance
- Color scheme (Material Design + Spotify/YouTube branding)
- Typography settings
- API credentials (to be set by user)
- File paths and directories

Example:
    >>> from config.app_config import ensure_app_directories
    >>> ensure_app_directories()  # Create necessary directories
    >>> print(CACHE_DB_PATH)
"""

import os


# ============================================================================
# Window Configuration
# ============================================================================

WINDOW_WIDTH = 800
"""Main window width in pixels."""

WINDOW_HEIGHT = 600
"""Main window height in pixels."""

WINDOW_RESIZABLE = False
"""Whether the main window can be resized by the user."""

WINDOW_TITLE = "Spotify to YouTube Music Migrator"
"""Application window title."""


# ============================================================================
# Color Scheme (Material Design + Platform Branding)
# ============================================================================

PRIMARY_COLOR = "#2196F3"
"""Primary UI color - Material Blue."""

SPOTIFY_GREEN = "#1DB954"
"""Spotify brand color - used for Spotify-related UI elements."""

YOUTUBE_RED = "#FF0000"
"""YouTube brand color - used for YouTube-related UI elements."""

SUCCESS_COLOR = "#4CAF50"
"""Success/completion color - Material Green."""

WARNING_COLOR = "#FF9800"
"""Warning/attention color - Material Orange."""

ERROR_COLOR = "#F44336"
"""Error/failure color - Material Red."""

TEXT_COLOR_LIGHT = "#FFFFFF"
"""Light text color for dark backgrounds."""

TEXT_COLOR_DARK = "#000000"
"""Dark text color for light backgrounds."""

BACKGROUND_LIGHT = "#FFFFFF"
"""Light background color."""

BACKGROUND_DARK = "#121212"
"""Dark background color (Material Dark Theme)."""


# ============================================================================
# Typography
# ============================================================================

HEADING_SIZE_LARGE = 32
"""Large heading font size (px) - Main titles."""

HEADING_SIZE_MEDIUM = 24
"""Medium heading font size (px) - Section titles."""

HEADING_SIZE_SMALL = 20
"""Small heading font size (px) - Subsection titles."""

BODY_SIZE = 16
"""Body text font size (px) - Default text."""

CAPTION_SIZE = 14
"""Caption text font size (px) - Secondary text, labels."""


# ============================================================================
# API Credentials
# ============================================================================
# NOTE: These should be loaded from environment variables or a secure config file.
# Users must provide their own API credentials from:
# - Spotify: https://developer.spotify.com/dashboard
# - YouTube: https://console.cloud.google.com/

SPOTIFY_CLIENT_ID = os.environ.get("SPOTIFY_CLIENT_ID", "")
"""Spotify API client ID. Set via SPOTIFY_CLIENT_ID environment variable."""

SPOTIFY_CLIENT_SECRET = os.environ.get("SPOTIFY_CLIENT_SECRET", "")
"""Spotify API client secret. Set via SPOTIFY_CLIENT_SECRET environment variable."""

SPOTIFY_REDIRECT_URI = os.environ.get("SPOTIFY_REDIRECT_URI", "http://localhost:8888/callback")
"""Spotify OAuth redirect URI. Defaults to localhost:8888/callback."""

YOUTUBE_CLIENT_ID = os.environ.get("YOUTUBE_CLIENT_ID", "")
"""YouTube API client ID. Set via YOUTUBE_CLIENT_ID environment variable."""

YOUTUBE_CLIENT_SECRET = os.environ.get("YOUTUBE_CLIENT_SECRET", "")
"""YouTube API client secret. Set via YOUTUBE_CLIENT_SECRET environment variable."""


# ============================================================================
# File Paths and Directories
# ============================================================================

APP_DATA_DIR = os.path.expanduser("~/.playlist_migrator")
"""Application data directory in user's home folder."""

CACHE_DB_PATH = os.path.join(APP_DATA_DIR, "cache.db")
"""SQLite database path for caching playlists and track matches."""

LOG_FILE_PATH = os.path.join(APP_DATA_DIR, "app.log")
"""Application log file path."""

CREDENTIALS_DIR = os.path.join(APP_DATA_DIR, "credentials")
"""Directory for storing OAuth tokens and credentials."""

SPOTIFY_TOKEN_PATH = os.path.join(CREDENTIALS_DIR, "spotify_token.json")
"""Spotify OAuth token cache path."""

YOUTUBE_TOKEN_PATH = os.path.join(CREDENTIALS_DIR, "youtube_token.json")
"""YouTube OAuth token cache path."""


# ============================================================================
# Migration Settings
# ============================================================================

DEFAULT_MATCH_THRESHOLD = 75
"""Default fuzzy matching threshold (0-100). Higher = stricter matching."""

MAX_CONCURRENT_MIGRATIONS = 1
"""Maximum number of playlists to migrate simultaneously."""

ENABLE_DESKTOP_NOTIFICATIONS = True
"""Whether to show desktop notifications for migration events."""

AUTO_RESUME_INCOMPLETE = True
"""Whether to automatically resume incomplete migrations on startup."""


# ============================================================================
# Rate Limiting
# ============================================================================

YOUTUBE_DAILY_QUOTA = 10000
"""YouTube API daily quota limit (default for free tier)."""

YOUTUBE_REQUESTS_PER_MINUTE = 100
"""YouTube API requests per minute limit."""

SEARCH_DELAY_SECONDS = 1.0
"""Delay between search requests to avoid rate limiting (seconds)."""


# ============================================================================
# Cache Settings
# ============================================================================

CACHE_EXPIRY_DAYS = 30
"""Number of days before cached data expires."""

CLEAR_OLD_JOBS_DAYS = 30
"""Number of days before old migration jobs are cleared."""


# ============================================================================
# Logging
# ============================================================================

LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
"""Logging level. Can be DEBUG, INFO, WARNING, ERROR, CRITICAL."""

LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
"""Log message format."""

LOG_MAX_BYTES = 10 * 1024 * 1024  # 10 MB
"""Maximum log file size before rotation."""

LOG_BACKUP_COUNT = 5
"""Number of rotated log files to keep."""


# ============================================================================
# Helper Functions
# ============================================================================

def ensure_app_directories() -> None:
    """Create necessary application directories if they don't exist.
    
    Creates:
    - APP_DATA_DIR: Main application data directory
    - CREDENTIALS_DIR: Directory for OAuth tokens
    
    This should be called on application startup before any file I/O.
    
    Example:
        >>> from config.app_config import ensure_app_directories
        >>> ensure_app_directories()
    """
    directories = [
        APP_DATA_DIR,
        CREDENTIALS_DIR
    ]
    
    for directory in directories:
        os.makedirs(directory, exist_ok=True)


def validate_credentials() -> dict:
    """Validate that required API credentials are set.
    
    Returns:
        dict: Validation result with keys:
            - 'spotify_valid' (bool): Whether Spotify credentials are set
            - 'youtube_valid' (bool): Whether YouTube credentials are set
            - 'all_valid' (bool): Whether all credentials are set
            - 'missing' (list): List of missing credential names
    
    Example:
        >>> result = validate_credentials()
        >>> if not result['all_valid']:
        ...     print(f"Missing: {', '.join(result['missing'])}")
    """
    missing = []
    
    # Check Spotify credentials
    if not SPOTIFY_CLIENT_ID:
        missing.append("SPOTIFY_CLIENT_ID")
    if not SPOTIFY_CLIENT_SECRET:
        missing.append("SPOTIFY_CLIENT_SECRET")
    
    # Check YouTube credentials
    if not YOUTUBE_CLIENT_ID:
        missing.append("YOUTUBE_CLIENT_ID")
    if not YOUTUBE_CLIENT_SECRET:
        missing.append("YOUTUBE_CLIENT_SECRET")
    
    spotify_valid = SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET
    youtube_valid = YOUTUBE_CLIENT_ID and YOUTUBE_CLIENT_SECRET
    
    return {
        'spotify_valid': bool(spotify_valid),
        'youtube_valid': bool(youtube_valid),
        'all_valid': len(missing) == 0,
        'missing': missing
    }


def get_config_summary() -> dict:
    """Get a summary of current configuration.
    
    Returns:
        dict: Configuration summary with all settings
    
    Example:
        >>> summary = get_config_summary()
        >>> print(f"Cache DB: {summary['paths']['cache_db']}")
    """
    return {
        'window': {
            'width': WINDOW_WIDTH,
            'height': WINDOW_HEIGHT,
            'resizable': WINDOW_RESIZABLE,
            'title': WINDOW_TITLE
        },
        'colors': {
            'primary': PRIMARY_COLOR,
            'spotify': SPOTIFY_GREEN,
            'youtube': YOUTUBE_RED,
            'success': SUCCESS_COLOR,
            'warning': WARNING_COLOR,
            'error': ERROR_COLOR
        },
        'typography': {
            'heading_large': HEADING_SIZE_LARGE,
            'heading_medium': HEADING_SIZE_MEDIUM,
            'heading_small': HEADING_SIZE_SMALL,
            'body': BODY_SIZE,
            'caption': CAPTION_SIZE
        },
        'paths': {
            'app_data_dir': APP_DATA_DIR,
            'cache_db': CACHE_DB_PATH,
            'log_file': LOG_FILE_PATH,
            'credentials_dir': CREDENTIALS_DIR
        },
        'migration': {
            'match_threshold': DEFAULT_MATCH_THRESHOLD,
            'max_concurrent': MAX_CONCURRENT_MIGRATIONS,
            'notifications': ENABLE_DESKTOP_NOTIFICATIONS,
            'auto_resume': AUTO_RESUME_INCOMPLETE
        },
        'rate_limiting': {
            'youtube_daily_quota': YOUTUBE_DAILY_QUOTA,
            'youtube_per_minute': YOUTUBE_REQUESTS_PER_MINUTE,
            'search_delay': SEARCH_DELAY_SECONDS
        },
        'cache': {
            'expiry_days': CACHE_EXPIRY_DAYS,
            'clear_old_jobs_days': CLEAR_OLD_JOBS_DAYS
        },
        'logging': {
            'level': LOG_LEVEL,
            'max_bytes': LOG_MAX_BYTES,
            'backup_count': LOG_BACKUP_COUNT
        }
    }
