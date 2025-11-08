"""Desktop notification system for playlist migrations.

Provides cross-platform desktop notifications using plyer library.
Gracefully handles platforms that don't support notifications.

Example:
    >>> notifier = Notifier(app_name="My App")
    >>> notifier.notify_migration_complete(
    ...     playlist_name="My Favorites",
    ...     matched=45,
    ...     total=50,
    ...     playlist_url="https://music.youtube.com/playlist?list=PLxxx"
    ... )
"""

import logging
import webbrowser
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from plyer import notification as plyer_notification
    PLYER_AVAILABLE = True
except ImportError:
    PLYER_AVAILABLE = False
    logger.warning("plyer not installed - desktop notifications will be disabled")


class Notifier:
    """Cross-platform desktop notification manager.
    
    Uses plyer library for sending system notifications. Gracefully degrades
    if plyer is not available or platform doesn't support notifications.
    
    Attributes:
        app_name (str): Application name displayed in notifications.
        enabled (bool): Whether notifications are available on this platform.
    
    Example:
        >>> notifier = Notifier(app_name="Playlist Migrator")
        >>> notifier.notify_migration_complete("My Playlist", 45, 50, "url")
    """
    
    def __init__(self, app_name: str = "Playlist Migrator"):
        """Initialize the notifier.
        
        Args:
            app_name (str): Name of the application for notifications.
                Defaults to "Playlist Migrator".
        """
        self.app_name = app_name
        self.enabled = PLYER_AVAILABLE
        
        if self.enabled:
            logger.info(f"Notifier initialized for: {app_name}")
        else:
            logger.info(f"Notifier initialized in disabled mode (plyer not available)")
    
    def _send_notification(
        self,
        title: str,
        message: str,
        timeout: int = 10,
        sound: bool = False,
        on_click: Optional[callable] = None
    ) -> None:
        """Internal method to send a notification.
        
        Args:
            title (str): Notification title.
            message (str): Notification message/body.
            timeout (int): Duration in seconds before auto-dismiss. Default: 10.
            sound (bool): Whether to play notification sound. Default: False.
            on_click (Optional[callable]): Callback function when notification
                is clicked. Not supported on all platforms.
        
        Note:
            Some platforms may not support all features (sound, on_click).
            The method gracefully handles these limitations.
        """
        if not self.enabled:
            logger.debug(f"Notification skipped (disabled): {title}")
            return
        
        try:
            # Basic notification parameters
            notify_params = {
                'title': title,
                'message': message,
                'app_name': self.app_name,
                'timeout': timeout
            }
            
            # Note: plyer doesn't consistently support 'sound' and 'on_click'
            # across all platforms, so we log but don't include them
            if sound:
                logger.debug("Sound requested for notification (may not be supported)")
            
            if on_click:
                logger.debug("Click handler provided (may not be supported)")
            
            # Send notification
            plyer_notification.notify(**notify_params)
            
            logger.info(f"Notification sent: {title}")
        
        except Exception as e:
            logger.error(f"Failed to send notification '{title}': {str(e)}")
            # Don't raise - notifications are non-critical
    
    def notify_migration_complete(
        self,
        playlist_name: str,
        matched: int,
        total: int,
        playlist_url: str,
        sound: bool = False
    ) -> None:
        """Notify that a playlist migration completed successfully.
        
        Args:
            playlist_name (str): Name of the migrated playlist.
            matched (int): Number of successfully matched/migrated tracks.
            total (int): Total number of tracks attempted.
            playlist_url (str): URL to the migrated YouTube Music playlist.
            sound (bool): Play notification sound. Default: False.
        
        Example:
            >>> notifier.notify_migration_complete(
            ...     "My Favorites",
            ...     45, 50,
            ...     "https://music.youtube.com/playlist?list=PLxxx"
            ... )
        """
        success_rate = (matched / total * 100) if total > 0 else 0
        
        title = "✅ Migration Complete"
        message = f"{playlist_name}: {matched}/{total} songs ({success_rate:.0f}%)"
        
        # Define click handler to open playlist URL
        def open_playlist():
            try:
                webbrowser.open(playlist_url)
                logger.info(f"Opened playlist URL: {playlist_url}")
            except Exception as e:
                logger.error(f"Failed to open playlist URL: {str(e)}")
        
        self._send_notification(
            title=title,
            message=message,
            timeout=10,
            sound=sound,
            on_click=open_playlist
        )
    
    def notify_migration_failed(
        self,
        playlist_name: str,
        error: str,
        sound: bool = False
    ) -> None:
        """Notify that a playlist migration failed.
        
        Args:
            playlist_name (str): Name of the playlist that failed to migrate.
            error (str): Error message or reason for failure.
            sound (bool): Play notification sound. Default: False.
        
        Example:
            >>> notifier.notify_migration_failed(
            ...     "My Playlist",
            ...     "Rate limit exceeded"
            ... )
        """
        title = "❌ Migration Failed"
        
        # Truncate error if too long
        max_error_length = 100
        error_display = error if len(error) <= max_error_length else error[:max_error_length] + "..."
        
        message = f"{playlist_name}: {error_display}"
        
        self._send_notification(
            title=title,
            message=message,
            timeout=10,
            sound=sound
        )
    
    def notify_rate_limit_pause(
        self,
        duration_seconds: int,
        sound: bool = False
    ) -> None:
        """Notify that migration is paused due to rate limits.
        
        Args:
            duration_seconds (int): How long the pause will last.
            sound (bool): Play notification sound. Default: False.
        
        Example:
            >>> notifier.notify_rate_limit_pause(60)  # Paused for 1 minute
        """
        title = "⏸️ Paused Due to Rate Limits"
        
        # Format duration nicely
        if duration_seconds < 60:
            duration_str = f"{duration_seconds} seconds"
        elif duration_seconds < 3600:
            minutes = duration_seconds // 60
            duration_str = f"{minutes} minute{'s' if minutes != 1 else ''}"
        else:
            hours = duration_seconds // 3600
            duration_str = f"{hours} hour{'s' if hours != 1 else ''}"
        
        message = f"Resuming in {duration_str}..."
        
        # Use the pause duration as timeout (auto-dismiss when resuming)
        timeout = min(duration_seconds, 60)  # Cap at 60 seconds for UX
        
        self._send_notification(
            title=title,
            message=message,
            timeout=timeout,
            sound=sound
        )
    
    def notify_all_complete(
        self,
        total_playlists: int,
        total_songs: int,
        sound: bool = False
    ) -> None:
        """Notify that all playlist migrations are complete.
        
        Args:
            total_playlists (int): Total number of playlists migrated.
            total_songs (int): Total number of songs migrated across all playlists.
            sound (bool): Play notification sound. Default: False.
        
        Example:
            >>> notifier.notify_all_complete(5, 237)
        """
        title = "🎉 All Migrations Complete!"
        
        playlist_word = "playlist" if total_playlists == 1 else "playlists"
        song_word = "song" if total_songs == 1 else "songs"
        
        message = f"{total_playlists} {playlist_word}, {total_songs} {song_word} migrated"
        
        self._send_notification(
            title=title,
            message=message,
            timeout=15,
            sound=sound
        )
    
    def notify_progress_milestone(
        self,
        playlist_name: str,
        current: int,
        total: int,
        sound: bool = False
    ) -> None:
        """Notify when reaching a progress milestone (optional).
        
        Useful for long-running migrations to show intermediate progress.
        
        Args:
            playlist_name (str): Name of the playlist being migrated.
            current (int): Current number of tracks processed.
            total (int): Total number of tracks.
            sound (bool): Play notification sound. Default: False.
        
        Example:
            >>> notifier.notify_progress_milestone("Big Playlist", 50, 100)
        """
        percentage = (current / total * 100) if total > 0 else 0
        
        title = f"⏳ Migration Progress"
        message = f"{playlist_name}: {current}/{total} ({percentage:.0f}%)"
        
        self._send_notification(
            title=title,
            message=message,
            timeout=5,  # Shorter timeout for progress updates
            sound=sound
        )
    
    def is_available(self) -> bool:
        """Check if notifications are available on this platform.
        
        Returns:
            bool: True if plyer is installed and notifications are supported.
        
        Example:
            >>> notifier = Notifier()
            >>> if notifier.is_available():
            ...     notifier.notify_migration_complete(...)
        """
        return self.enabled
