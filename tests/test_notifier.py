"""Tests for Notifier class.

Tests desktop notification functionality with cross-platform support.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import sys

from src.utils.notifier import Notifier, PLYER_AVAILABLE


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_plyer_notification():
    """Mock plyer.notification for testing."""
    with patch('src.utils.notifier.plyer_notification') as mock:
        yield mock


@pytest.fixture
def notifier():
    """Create a Notifier instance."""
    return Notifier(app_name="Test App")


# ============================================================================
# Test: Initialization
# ============================================================================

def test_init_default_app_name():
    """Test Notifier initialization with default app name."""
    notifier = Notifier()
    assert notifier.app_name == "Playlist Migrator"
    assert notifier.enabled == PLYER_AVAILABLE


def test_init_custom_app_name():
    """Test Notifier initialization with custom app name."""
    notifier = Notifier(app_name="My Custom App")
    assert notifier.app_name == "My Custom App"
    assert notifier.enabled == PLYER_AVAILABLE


def test_is_available():
    """Test is_available method."""
    notifier = Notifier()
    assert notifier.is_available() == PLYER_AVAILABLE


# ============================================================================
# Test: Migration Complete Notification
# ============================================================================

@patch('src.utils.notifier.PLYER_AVAILABLE', True)
def test_notify_migration_complete(mock_plyer_notification):
    """Test migration complete notification."""
    notifier = Notifier()
    notifier.enabled = True  # Force enable for testing
    
    notifier.notify_migration_complete(
        playlist_name="My Favorites",
        matched=45,
        total=50,
        playlist_url="https://music.youtube.com/playlist?list=PLxxx"
    )
    
    # Verify notification was called
    mock_plyer_notification.notify.assert_called_once()
    
    # Verify notification parameters
    call_kwargs = mock_plyer_notification.notify.call_args[1]
    assert call_kwargs['title'] == "✅ Migration Complete"
    assert "My Favorites" in call_kwargs['message']
    assert "45/50" in call_kwargs['message']
    assert "90%" in call_kwargs['message']
    assert call_kwargs['app_name'] == "Playlist Migrator"
    assert call_kwargs['timeout'] == 10


@patch('src.utils.notifier.PLYER_AVAILABLE', True)
def test_notify_migration_complete_100_percent(mock_plyer_notification):
    """Test migration complete notification with 100% success."""
    notifier = Notifier()
    notifier.enabled = True
    
    notifier.notify_migration_complete(
        playlist_name="Perfect Playlist",
        matched=100,
        total=100,
        playlist_url="https://example.com"
    )
    
    call_kwargs = mock_plyer_notification.notify.call_args[1]
    assert "100/100" in call_kwargs['message']
    assert "100%" in call_kwargs['message']


@patch('src.utils.notifier.PLYER_AVAILABLE', True)
def test_notify_migration_complete_zero_total(mock_plyer_notification):
    """Test migration complete with zero total tracks."""
    notifier = Notifier()
    notifier.enabled = True
    
    notifier.notify_migration_complete(
        playlist_name="Empty Playlist",
        matched=0,
        total=0,
        playlist_url="https://example.com"
    )
    
    call_kwargs = mock_plyer_notification.notify.call_args[1]
    assert "0/0" in call_kwargs['message']
    # Should handle division by zero gracefully


@patch('src.utils.notifier.PLYER_AVAILABLE', True)
def test_notify_migration_complete_with_sound(mock_plyer_notification):
    """Test migration complete notification with sound enabled."""
    notifier = Notifier()
    notifier.enabled = True
    
    notifier.notify_migration_complete(
        playlist_name="My Playlist",
        matched=10,
        total=10,
        playlist_url="https://example.com",
        sound=True
    )
    
    # Notification should still be sent (sound may not be supported)
    mock_plyer_notification.notify.assert_called_once()


# ============================================================================
# Test: Migration Failed Notification
# ============================================================================

@patch('src.utils.notifier.PLYER_AVAILABLE', True)
def test_notify_migration_failed(mock_plyer_notification):
    """Test migration failed notification."""
    notifier = Notifier()
    notifier.enabled = True
    
    notifier.notify_migration_failed(
        playlist_name="Problem Playlist",
        error="Rate limit exceeded"
    )
    
    mock_plyer_notification.notify.assert_called_once()
    
    call_kwargs = mock_plyer_notification.notify.call_args[1]
    assert call_kwargs['title'] == "❌ Migration Failed"
    assert "Problem Playlist" in call_kwargs['message']
    assert "Rate limit exceeded" in call_kwargs['message']
    assert call_kwargs['timeout'] == 10


@patch('src.utils.notifier.PLYER_AVAILABLE', True)
def test_notify_migration_failed_long_error(mock_plyer_notification):
    """Test migration failed with very long error message."""
    notifier = Notifier()
    notifier.enabled = True
    
    long_error = "A" * 200  # 200 character error
    
    notifier.notify_migration_failed(
        playlist_name="My Playlist",
        error=long_error
    )
    
    call_kwargs = mock_plyer_notification.notify.call_args[1]
    # Error should be truncated
    assert len(call_kwargs['message']) < len(long_error) + 20
    assert "..." in call_kwargs['message']


@patch('src.utils.notifier.PLYER_AVAILABLE', True)
def test_notify_migration_failed_with_sound(mock_plyer_notification):
    """Test migration failed notification with sound."""
    notifier = Notifier()
    notifier.enabled = True
    
    notifier.notify_migration_failed(
        playlist_name="My Playlist",
        error="Network error",
        sound=True
    )
    
    mock_plyer_notification.notify.assert_called_once()


# ============================================================================
# Test: Rate Limit Pause Notification
# ============================================================================

@patch('src.utils.notifier.PLYER_AVAILABLE', True)
def test_notify_rate_limit_pause_seconds(mock_plyer_notification):
    """Test rate limit pause notification with seconds."""
    notifier = Notifier()
    notifier.enabled = True
    
    notifier.notify_rate_limit_pause(duration_seconds=30)
    
    mock_plyer_notification.notify.assert_called_once()
    
    call_kwargs = mock_plyer_notification.notify.call_args[1]
    assert call_kwargs['title'] == "⏸️ Paused Due to Rate Limits"
    assert "30 seconds" in call_kwargs['message']
    assert call_kwargs['timeout'] == 30


@patch('src.utils.notifier.PLYER_AVAILABLE', True)
def test_notify_rate_limit_pause_minutes(mock_plyer_notification):
    """Test rate limit pause notification with minutes."""
    notifier = Notifier()
    notifier.enabled = True
    
    notifier.notify_rate_limit_pause(duration_seconds=120)  # 2 minutes
    
    call_kwargs = mock_plyer_notification.notify.call_args[1]
    assert "2 minutes" in call_kwargs['message']
    assert call_kwargs['timeout'] == 60  # Capped at 60


@patch('src.utils.notifier.PLYER_AVAILABLE', True)
def test_notify_rate_limit_pause_hours(mock_plyer_notification):
    """Test rate limit pause notification with hours."""
    notifier = Notifier()
    notifier.enabled = True
    
    notifier.notify_rate_limit_pause(duration_seconds=7200)  # 2 hours
    
    call_kwargs = mock_plyer_notification.notify.call_args[1]
    assert "2 hours" in call_kwargs['message']
    assert call_kwargs['timeout'] == 60  # Capped at 60


@patch('src.utils.notifier.PLYER_AVAILABLE', True)
def test_notify_rate_limit_pause_singular(mock_plyer_notification):
    """Test rate limit pause with singular units."""
    notifier = Notifier()
    notifier.enabled = True
    
    # 1 minute
    notifier.notify_rate_limit_pause(duration_seconds=60)
    call_kwargs = mock_plyer_notification.notify.call_args[1]
    assert "1 minute" in call_kwargs['message']
    assert "minutes" not in call_kwargs['message']  # Should be singular


# ============================================================================
# Test: All Complete Notification
# ============================================================================

@patch('src.utils.notifier.PLYER_AVAILABLE', True)
def test_notify_all_complete(mock_plyer_notification):
    """Test all migrations complete notification."""
    notifier = Notifier()
    notifier.enabled = True
    
    notifier.notify_all_complete(
        total_playlists=5,
        total_songs=237
    )
    
    mock_plyer_notification.notify.assert_called_once()
    
    call_kwargs = mock_plyer_notification.notify.call_args[1]
    assert call_kwargs['title'] == "🎉 All Migrations Complete!"
    assert "5 playlists" in call_kwargs['message']
    assert "237 songs" in call_kwargs['message']
    assert call_kwargs['timeout'] == 15


@patch('src.utils.notifier.PLYER_AVAILABLE', True)
def test_notify_all_complete_singular(mock_plyer_notification):
    """Test all complete with singular playlist and song."""
    notifier = Notifier()
    notifier.enabled = True
    
    notifier.notify_all_complete(
        total_playlists=1,
        total_songs=1
    )
    
    call_kwargs = mock_plyer_notification.notify.call_args[1]
    assert "1 playlist" in call_kwargs['message']
    assert "1 song" in call_kwargs['message']
    # Should use singular forms


@patch('src.utils.notifier.PLYER_AVAILABLE', True)
def test_notify_all_complete_with_sound(mock_plyer_notification):
    """Test all complete notification with sound."""
    notifier = Notifier()
    notifier.enabled = True
    
    notifier.notify_all_complete(
        total_playlists=3,
        total_songs=100,
        sound=True
    )
    
    mock_plyer_notification.notify.assert_called_once()


# ============================================================================
# Test: Progress Milestone Notification
# ============================================================================

@patch('src.utils.notifier.PLYER_AVAILABLE', True)
def test_notify_progress_milestone(mock_plyer_notification):
    """Test progress milestone notification."""
    notifier = Notifier()
    notifier.enabled = True
    
    notifier.notify_progress_milestone(
        playlist_name="Big Playlist",
        current=50,
        total=100
    )
    
    mock_plyer_notification.notify.assert_called_once()
    
    call_kwargs = mock_plyer_notification.notify.call_args[1]
    assert call_kwargs['title'] == "⏳ Migration Progress"
    assert "Big Playlist" in call_kwargs['message']
    assert "50/100" in call_kwargs['message']
    assert "50%" in call_kwargs['message']
    assert call_kwargs['timeout'] == 5  # Shorter timeout for progress


# ============================================================================
# Test: Error Handling
# ============================================================================

@patch('src.utils.notifier.PLYER_AVAILABLE', True)
def test_notification_exception_handling(mock_plyer_notification):
    """Test that notification exceptions are caught and logged."""
    notifier = Notifier()
    notifier.enabled = True
    
    # Make notify raise an exception
    mock_plyer_notification.notify.side_effect = Exception("Platform not supported")
    
    # Should not raise, just log
    notifier.notify_migration_complete(
        "Test",
        10,
        10,
        "https://example.com"
    )
    
    # Verify notify was attempted
    mock_plyer_notification.notify.assert_called_once()


def test_notifications_disabled_when_plyer_unavailable():
    """Test that notifications are skipped when plyer is not available."""
    with patch('src.utils.notifier.PLYER_AVAILABLE', False):
        notifier = Notifier()
        
        # Should not raise error when plyer is unavailable
        notifier.notify_migration_complete(
            "Test",
            10,
            10,
            "https://example.com"
        )
        
        assert not notifier.is_available()


@patch('src.utils.notifier.PLYER_AVAILABLE', True)
def test_send_notification_when_disabled(mock_plyer_notification):
    """Test that notifications are not sent when disabled."""
    notifier = Notifier()
    notifier.enabled = False  # Explicitly disable
    
    notifier.notify_migration_complete(
        "Test",
        10,
        10,
        "https://example.com"
    )
    
    # Should not call plyer when disabled
    mock_plyer_notification.notify.assert_not_called()


# ============================================================================
# Test: Click Handler (Browser Opening)
# ============================================================================

@patch('src.utils.notifier.PLYER_AVAILABLE', True)
@patch('src.utils.notifier.webbrowser')
def test_migration_complete_click_handler(mock_webbrowser, mock_plyer_notification):
    """Test that click handler is set up for migration complete."""
    notifier = Notifier()
    notifier.enabled = True
    
    playlist_url = "https://music.youtube.com/playlist?list=PLxxx"
    
    notifier.notify_migration_complete(
        "Test",
        10,
        10,
        playlist_url
    )
    
    # Note: We can't directly test the click handler since plyer may not
    # support it on all platforms, but we verify the notification was sent
    mock_plyer_notification.notify.assert_called_once()


# ============================================================================
# Test: Integration
# ============================================================================

@patch('src.utils.notifier.PLYER_AVAILABLE', True)
def test_multiple_notifications(mock_plyer_notification):
    """Test sending multiple notifications in sequence."""
    notifier = Notifier()
    notifier.enabled = True
    
    # Send multiple notifications
    notifier.notify_migration_complete("Playlist 1", 10, 10, "url1")
    notifier.notify_migration_complete("Playlist 2", 20, 20, "url2")
    notifier.notify_all_complete(2, 30)
    
    # Verify all were sent
    assert mock_plyer_notification.notify.call_count == 3


@patch('src.utils.notifier.PLYER_AVAILABLE', True)
def test_notification_with_special_characters(mock_plyer_notification):
    """Test notifications with special characters in messages."""
    notifier = Notifier()
    notifier.enabled = True
    
    notifier.notify_migration_complete(
        playlist_name="Playlist with émojis 🎵",
        matched=5,
        total=10,
        playlist_url="https://example.com"
    )
    
    call_kwargs = mock_plyer_notification.notify.call_args[1]
    assert "Playlist with émojis 🎵" in call_kwargs['message']
