"""Configuration package for Spotify to YouTube Music Migrator.

This package contains application-wide configuration constants and settings.

Example:
    >>> from config import WINDOW_WIDTH, WINDOW_HEIGHT
    >>> from config import ensure_app_directories, validate_credentials
    >>> 
    >>> ensure_app_directories()
    >>> result = validate_credentials()
    >>> if not result['all_valid']:
    ...     print(f"Missing credentials: {result['missing']}")
"""

from config.app_config import (
    # Window configuration
    WINDOW_WIDTH,
    WINDOW_HEIGHT,
    WINDOW_RESIZABLE,
    WINDOW_TITLE,
    
    # Colors
    PRIMARY_COLOR,
    SPOTIFY_GREEN,
    YOUTUBE_RED,
    SUCCESS_COLOR,
    WARNING_COLOR,
    ERROR_COLOR,
    TEXT_COLOR_LIGHT,
    TEXT_COLOR_DARK,
    BACKGROUND_LIGHT,
    BACKGROUND_DARK,
    
    # Typography
    HEADING_SIZE_LARGE,
    HEADING_SIZE_MEDIUM,
    HEADING_SIZE_SMALL,
    BODY_SIZE,
    CAPTION_SIZE,
    
    # API Credentials
    SPOTIFY_CLIENT_ID,
    SPOTIFY_CLIENT_SECRET,
    SPOTIFY_REDIRECT_URI,
    YOUTUBE_CLIENT_ID,
    YOUTUBE_CLIENT_SECRET,
    
    # Paths
    APP_DATA_DIR,
    CACHE_DB_PATH,
    LOG_FILE_PATH,
    CREDENTIALS_DIR,
    SPOTIFY_TOKEN_PATH,
    YOUTUBE_TOKEN_PATH,
    
    # Migration settings
    DEFAULT_MATCH_THRESHOLD,
    MAX_CONCURRENT_MIGRATIONS,
    ENABLE_DESKTOP_NOTIFICATIONS,
    AUTO_RESUME_INCOMPLETE,
    
    # Rate limiting
    YOUTUBE_DAILY_QUOTA,
    YOUTUBE_REQUESTS_PER_MINUTE,
    SEARCH_DELAY_SECONDS,
    
    # Cache
    CACHE_EXPIRY_DAYS,
    CLEAR_OLD_JOBS_DAYS,
    
    # Logging
    LOG_LEVEL,
    LOG_FORMAT,
    LOG_MAX_BYTES,
    LOG_BACKUP_COUNT,
    
    # Helper functions
    ensure_app_directories,
    validate_credentials,
    get_config_summary,
)

__all__ = [
    # Window configuration
    'WINDOW_WIDTH',
    'WINDOW_HEIGHT',
    'WINDOW_RESIZABLE',
    'WINDOW_TITLE',
    
    # Colors
    'PRIMARY_COLOR',
    'SPOTIFY_GREEN',
    'YOUTUBE_RED',
    'SUCCESS_COLOR',
    'WARNING_COLOR',
    'ERROR_COLOR',
    'TEXT_COLOR_LIGHT',
    'TEXT_COLOR_DARK',
    'BACKGROUND_LIGHT',
    'BACKGROUND_DARK',
    
    # Typography
    'HEADING_SIZE_LARGE',
    'HEADING_SIZE_MEDIUM',
    'HEADING_SIZE_SMALL',
    'BODY_SIZE',
    'CAPTION_SIZE',
    
    # API Credentials
    'SPOTIFY_CLIENT_ID',
    'SPOTIFY_CLIENT_SECRET',
    'SPOTIFY_REDIRECT_URI',
    'YOUTUBE_CLIENT_ID',
    'YOUTUBE_CLIENT_SECRET',
    
    # Paths
    'APP_DATA_DIR',
    'CACHE_DB_PATH',
    'LOG_FILE_PATH',
    'CREDENTIALS_DIR',
    'SPOTIFY_TOKEN_PATH',
    'YOUTUBE_TOKEN_PATH',
    
    # Migration settings
    'DEFAULT_MATCH_THRESHOLD',
    'MAX_CONCURRENT_MIGRATIONS',
    'ENABLE_DESKTOP_NOTIFICATIONS',
    'AUTO_RESUME_INCOMPLETE',
    
    # Rate limiting
    'YOUTUBE_DAILY_QUOTA',
    'YOUTUBE_REQUESTS_PER_MINUTE',
    'SEARCH_DELAY_SECONDS',
    
    # Cache
    'CACHE_EXPIRY_DAYS',
    'CLEAR_OLD_JOBS_DAYS',
    
    # Logging
    'LOG_LEVEL',
    'LOG_FORMAT',
    'LOG_MAX_BYTES',
    'LOG_BACKUP_COUNT',
    
    # Helper functions
    'ensure_app_directories',
    'validate_credentials',
    'get_config_summary',
]
