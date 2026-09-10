"""Tests for app_config module.

Tests configuration constants and helper functions.
"""

import pytest
import os
import tempfile
import shutil
from unittest.mock import patch

from config import app_config


# ============================================================================
# Test: Constants
# ============================================================================

def test_window_constants():
    """Test window configuration constants."""
    assert app_config.WINDOW_WIDTH == 800
    assert app_config.WINDOW_HEIGHT == 600
    assert app_config.WINDOW_RESIZABLE is False
    assert app_config.WINDOW_TITLE == "Spotify to YouTube Music Migrator"


def test_color_constants():
    """Test color scheme constants."""
    assert app_config.PRIMARY_COLOR == "#2196F3"
    assert app_config.SPOTIFY_GREEN == "#1DB954"
    assert app_config.YOUTUBE_RED == "#FF0000"
    assert app_config.SUCCESS_COLOR == "#4CAF50"
    assert app_config.WARNING_COLOR == "#FF9800"
    assert app_config.ERROR_COLOR == "#F44336"
    assert app_config.TEXT_COLOR_LIGHT == "#FFFFFF"
    assert app_config.TEXT_COLOR_DARK == "#000000"
    assert app_config.BACKGROUND_LIGHT == "#FFFFFF"
    assert app_config.BACKGROUND_DARK == "#121212"


def test_typography_constants():
    """Test typography constants."""
    assert app_config.HEADING_SIZE_LARGE == 32
    assert app_config.HEADING_SIZE_MEDIUM == 24
    assert app_config.HEADING_SIZE_SMALL == 20
    assert app_config.BODY_SIZE == 16
    assert app_config.CAPTION_SIZE == 14


def test_migration_settings():
    """Test migration configuration constants."""
    assert app_config.DEFAULT_MATCH_THRESHOLD == 75
    assert app_config.MAX_CONCURRENT_MIGRATIONS == 1
    assert app_config.ENABLE_DESKTOP_NOTIFICATIONS is True
    assert app_config.AUTO_RESUME_INCOMPLETE is True


def test_rate_limiting_constants():
    """Test rate limiting constants."""
    assert app_config.YOUTUBE_DAILY_QUOTA == 10000
    assert app_config.YOUTUBE_REQUESTS_PER_MINUTE == 100
    assert app_config.SEARCH_DELAY_SECONDS == 1.0


def test_cache_constants():
    """Test cache configuration constants."""
    assert app_config.CACHE_EXPIRY_DAYS == 30
    assert app_config.CLEAR_OLD_JOBS_DAYS == 30


def test_logging_constants():
    """Test logging configuration constants."""
    assert app_config.LOG_LEVEL in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
    assert app_config.LOG_FORMAT == "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    assert app_config.LOG_MAX_BYTES == 10 * 1024 * 1024  # 10 MB
    assert app_config.LOG_BACKUP_COUNT == 5


# ============================================================================
# Test: Path Constants
# ============================================================================

def test_path_constants():
    """Test path constants are properly defined."""
    assert app_config.APP_DATA_DIR.endswith(".playlist_migrator")
    assert app_config.CACHE_DB_PATH.endswith("cache.db")
    assert app_config.LOG_FILE_PATH.endswith("app.log")
    assert app_config.CREDENTIALS_DIR.endswith("credentials")
    assert app_config.SPOTIFY_TOKEN_PATH.endswith("spotify_token.json")
    assert app_config.YOUTUBE_TOKEN_PATH.endswith("youtube_token.json")


def test_path_expansion():
    """Test that paths use user's home directory."""
    assert os.path.expanduser("~") in app_config.APP_DATA_DIR


# ============================================================================
# Test: API Credentials
# ============================================================================

def test_api_credentials_from_env():
    """Test that API credentials load from environment variables."""
    with patch.dict(os.environ, {
        'SPOTIFY_CLIENT_ID': 'test_spotify_id',
        'SPOTIFY_CLIENT_SECRET': 'test_spotify_secret',
        'YOUTUBE_CLIENT_ID': 'test_youtube_id',
        'YOUTUBE_CLIENT_SECRET': 'test_youtube_secret'
    }):
        # Reload module to pick up env vars
        import importlib
        importlib.reload(app_config)
        
        assert app_config.SPOTIFY_CLIENT_ID == 'test_spotify_id'
        assert app_config.SPOTIFY_CLIENT_SECRET == 'test_spotify_secret'
        assert app_config.YOUTUBE_CLIENT_ID == 'test_youtube_id'
        assert app_config.YOUTUBE_CLIENT_SECRET == 'test_youtube_secret'


def test_spotify_redirect_uri_default():
    """Test Spotify redirect URI has default value (127.0.0.1, not localhost)."""
    # Changed from localhost to 127.0.0.1 per Spotify Nov 2025 requirements
    assert app_config.SPOTIFY_REDIRECT_URI == "http://127.0.0.1:8888/callback"


# ============================================================================
# Test: ensure_app_directories
# ============================================================================

def test_ensure_app_directories():
    """Test ensure_app_directories creates necessary directories."""
    # Use temporary directory
    with tempfile.TemporaryDirectory() as tmpdir:
        test_app_dir = os.path.join(tmpdir, "test_app")
        test_creds_dir = os.path.join(test_app_dir, "credentials")
        
        with patch.object(app_config, 'APP_DATA_DIR', test_app_dir), \
             patch.object(app_config, 'CREDENTIALS_DIR', test_creds_dir):
            
            # Directories should not exist yet
            assert not os.path.exists(test_app_dir)
            assert not os.path.exists(test_creds_dir)
            
            # Call function
            app_config.ensure_app_directories()
            
            # Directories should now exist
            assert os.path.exists(test_app_dir)
            assert os.path.exists(test_creds_dir)
            assert os.path.isdir(test_app_dir)
            assert os.path.isdir(test_creds_dir)


def test_ensure_app_directories_already_exists():
    """Test ensure_app_directories handles existing directories."""
    with tempfile.TemporaryDirectory() as tmpdir:
        test_app_dir = os.path.join(tmpdir, "existing_app")
        test_creds_dir = os.path.join(test_app_dir, "credentials")
        
        # Create directories first
        os.makedirs(test_creds_dir, exist_ok=True)
        
        with patch.object(app_config, 'APP_DATA_DIR', test_app_dir), \
             patch.object(app_config, 'CREDENTIALS_DIR', test_creds_dir):
            
            # Should not raise error
            app_config.ensure_app_directories()
            
            # Directories should still exist
            assert os.path.exists(test_app_dir)
            assert os.path.exists(test_creds_dir)


# ============================================================================
# Test: validate_credentials
# ============================================================================

def test_validate_credentials_all_set():
    """Test validate_credentials with all credentials set."""
    with patch.object(app_config, 'SPOTIFY_CLIENT_ID', 'spotify_id'), \
         patch.object(app_config, 'SPOTIFY_CLIENT_SECRET', 'spotify_secret'), \
         patch.object(app_config, 'YOUTUBE_CLIENT_ID', 'youtube_id'), \
         patch.object(app_config, 'YOUTUBE_CLIENT_SECRET', 'youtube_secret'):
        
        result = app_config.validate_credentials()
        
        assert result['spotify_valid'] is True
        assert result['youtube_valid'] is True
        assert result['all_valid'] is True
        assert result['missing'] == []


def test_validate_credentials_spotify_missing():
    """Test validate_credentials with Spotify credentials missing."""
    with patch.object(app_config, 'SPOTIFY_CLIENT_ID', ''), \
         patch.object(app_config, 'SPOTIFY_CLIENT_SECRET', ''), \
         patch.object(app_config, 'YOUTUBE_CLIENT_ID', 'youtube_id'), \
         patch.object(app_config, 'YOUTUBE_CLIENT_SECRET', 'youtube_secret'):
        
        result = app_config.validate_credentials()
        
        assert result['spotify_valid'] is False
        assert result['youtube_valid'] is True
        assert result['all_valid'] is False
        assert 'SPOTIFY_CLIENT_ID' in result['missing']
        assert 'SPOTIFY_CLIENT_SECRET' in result['missing']


def test_validate_credentials_youtube_missing():
    """Test validate_credentials with YouTube credentials missing."""
    with patch.object(app_config, 'SPOTIFY_CLIENT_ID', 'spotify_id'), \
         patch.object(app_config, 'SPOTIFY_CLIENT_SECRET', 'spotify_secret'), \
         patch.object(app_config, 'YOUTUBE_CLIENT_ID', ''), \
         patch.object(app_config, 'YOUTUBE_CLIENT_SECRET', ''):
        
        result = app_config.validate_credentials()
        
        assert result['spotify_valid'] is True
        assert result['youtube_valid'] is False
        assert result['all_valid'] is False
        assert 'YOUTUBE_CLIENT_ID' in result['missing']
        assert 'YOUTUBE_CLIENT_SECRET' in result['missing']


def test_validate_credentials_all_missing():
    """Test validate_credentials with all credentials missing."""
    with patch.object(app_config, 'SPOTIFY_CLIENT_ID', ''), \
         patch.object(app_config, 'SPOTIFY_CLIENT_SECRET', ''), \
         patch.object(app_config, 'YOUTUBE_CLIENT_ID', ''), \
         patch.object(app_config, 'YOUTUBE_CLIENT_SECRET', ''):
        
        result = app_config.validate_credentials()
        
        assert result['spotify_valid'] is False
        assert result['youtube_valid'] is False
        assert result['all_valid'] is False
        assert len(result['missing']) == 4


# ============================================================================
# Test: get_config_summary
# ============================================================================

def test_get_config_summary():
    """Test get_config_summary returns complete configuration."""
    summary = app_config.get_config_summary()
    
    # Check all sections exist
    assert 'window' in summary
    assert 'colors' in summary
    assert 'typography' in summary
    assert 'paths' in summary
    assert 'migration' in summary
    assert 'rate_limiting' in summary
    assert 'cache' in summary
    assert 'logging' in summary


def test_get_config_summary_window():
    """Test window configuration in summary."""
    summary = app_config.get_config_summary()
    
    assert summary['window']['width'] == 800
    assert summary['window']['height'] == 600
    assert summary['window']['resizable'] is False
    assert summary['window']['title'] == "Spotify to YouTube Music Migrator"


def test_get_config_summary_colors():
    """Test color configuration in summary."""
    summary = app_config.get_config_summary()
    
    assert summary['colors']['primary'] == "#2196F3"
    assert summary['colors']['spotify'] == "#1DB954"
    assert summary['colors']['youtube'] == "#FF0000"
    assert summary['colors']['success'] == "#4CAF50"
    assert summary['colors']['warning'] == "#FF9800"
    assert summary['colors']['error'] == "#F44336"


def test_get_config_summary_typography():
    """Test typography configuration in summary."""
    summary = app_config.get_config_summary()
    
    assert summary['typography']['heading_large'] == 32
    assert summary['typography']['heading_medium'] == 24
    assert summary['typography']['heading_small'] == 20
    assert summary['typography']['body'] == 16
    assert summary['typography']['caption'] == 14


def test_get_config_summary_paths():
    """Test paths configuration in summary."""
    summary = app_config.get_config_summary()
    
    assert 'app_data_dir' in summary['paths']
    assert 'cache_db' in summary['paths']
    assert 'log_file' in summary['paths']
    assert 'credentials_dir' in summary['paths']


def test_get_config_summary_migration():
    """Test migration configuration in summary."""
    summary = app_config.get_config_summary()
    
    assert summary['migration']['match_threshold'] == 75
    assert summary['migration']['max_concurrent'] == 1
    assert summary['migration']['notifications'] is True
    assert summary['migration']['auto_resume'] is True


def test_get_config_summary_rate_limiting():
    """Test rate limiting configuration in summary."""
    summary = app_config.get_config_summary()
    
    assert summary['rate_limiting']['youtube_daily_quota'] == 10000
    assert summary['rate_limiting']['youtube_per_minute'] == 100
    assert summary['rate_limiting']['search_delay'] == 1.0


def test_get_config_summary_cache():
    """Test cache configuration in summary."""
    summary = app_config.get_config_summary()
    
    assert summary['cache']['expiry_days'] == 30
    assert summary['cache']['clear_old_jobs_days'] == 30


def test_get_config_summary_logging():
    """Test logging configuration in summary."""
    summary = app_config.get_config_summary()
    
    assert summary['logging']['level'] in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
    assert summary['logging']['max_bytes'] == 10 * 1024 * 1024
    assert summary['logging']['backup_count'] == 5
