"""Migration Progress Screen for real-time migration monitoring.

This screen displays live progress updates during playlist migrations, including:
- Current playlist and track being processed
- Overall progress bar with percentage
- Success/failure statistics
- Estimated time remaining
- Pause/resume and cancel controls

The screen uses thread-safe UI updates to receive progress callbacks from the
background MigrationManager worker threads.

Example:
    >>> screen = MigrationProgressScreen(page, app_state)
    >>> screen.show(show_back=False, progress_text="Step 3 of 5")
    >>> # Migration starts automatically on show
"""

import flet as ft
import time
import threading
from typing import Optional, Dict, Any
from datetime import datetime, timedelta

from src.ui.base_screen import BaseScreen
from src.ui.components import AppButton, ProgressBar, StatusBanner
from src.migrators.migration_manager import MigrationManager
from config import app_config


class MigrationProgressScreen(BaseScreen):
    """Screen for monitoring real-time migration progress.
    
    Displays live updates as playlists are migrated from Spotify to YouTube Music.
    Features include:
    - Animated sync icon that rotates continuously
    - Real-time track and playlist progress
    - Success/failure counters with animations
    - Estimated time remaining calculation
    - Pause/resume functionality
    - Cancel with confirmation dialog
    - Thread-safe UI updates from background workers
    
    Attributes:
        migration_manager (Optional[MigrationManager]): Migration orchestrator.
        current_playlist_index (int): Index of current playlist (0-based).
        current_playlist_name (str): Name of currently processing playlist.
        current_track_index (int): Index of current track (0-based).
        total_playlists (int): Total number of playlists to migrate.
        total_tracks (int): Total number of tracks across all playlists.
        matched_count (int): Number of successfully matched tracks.
        failed_count (int): Number of failed track migrations.
        start_time (Optional[float]): Unix timestamp when migration started.
        is_paused (bool): Whether migration is currently paused.
        is_cancelled (bool): Whether migration has been cancelled.
        last_update_time (float): Unix timestamp of last UI update.
        update_lock (threading.Lock): Thread lock for safe UI updates.
    
    Example:
        >>> app_state = {
        ...     'spotify_client': spotify,
        ...     'youtube_client': ytmusic,
        ...     'cache_manager': cache,
        ...     'selected_playlists': [{'id': 'sp_123', 'name': 'Rock'}]
        ... }
        >>> screen = MigrationProgressScreen(page, app_state)
        >>> screen.show(progress_text="Migration in Progress [3/5]")
    """
    
    def __init__(self, page: ft.Page, app_state: Dict[str, Any]):
        """Initialize the migration progress screen.
        
        Args:
            page (ft.Page): Flet page instance.
            app_state (Dict[str, Any]): Shared application state containing:
                - 'spotify_client': Authenticated Spotify client
                - 'youtube_client': Authenticated YouTube Music client
                - 'cache_manager': Cache manager instance
                - 'selected_playlists': List of playlists to migrate
        """
        super().__init__(page, app_state)
        
        # Migration state
        self.migration_manager: Optional[MigrationManager] = None
        self.current_playlist_index = 0
        self.current_playlist_name = ""
        self.current_track_index = 0
        self.current_track_name = ""
        self.total_playlists = 0
        self.total_tracks = 0
        self.matched_count = 0
        self.failed_count = 0
        self.start_time: Optional[float] = None
        self.is_paused = False
        self.is_cancelled = False
        
        # UI update throttling
        self.last_update_time = 0.0
        self.update_lock = threading.Lock()
        
        # UI component references
        self.sync_icon: Optional[ft.Icon] = None
        self.playlist_text: Optional[ft.Text] = None
        self.track_text: Optional[ft.Text] = None
        self.track_name_text: Optional[ft.Text] = None
        self.progress_bar: Optional[ProgressBar] = None
        self.matched_text: Optional[ft.Text] = None
        self.failed_text: Optional[ft.Text] = None
        self.time_text: Optional[ft.Text] = None
        self.pause_button: Optional[AppButton] = None
        self.cancel_button: Optional[AppButton] = None
        self.status_banner: Optional[StatusBanner] = None
    
    def build(self) -> ft.Control:
        """Build the migration progress screen UI.
        
        Creates the complete screen layout including:
        - Rotating sync icon
        - Current playlist/track information
        - Progress bar with percentage
        - Statistics (matched/failed counts)
        - Estimated time remaining
        - Tip banner
        - Pause and Cancel buttons
        
        Returns:
            ft.Control: The screen content container.
        """
        # Title
        title = ft.Text(
            value="Migration in Progress",
            size=app_config.HEADING_SIZE_LARGE,
            weight=ft.FontWeight.BOLD,
            color=app_config.TEXT_COLOR_LIGHT
        )
        
        # Animated sync icon (rotates continuously)
        self.sync_icon = ft.Icon(
            name=ft.Icons.SYNC,
            color=app_config.PRIMARY_COLOR,
            size=80,
            rotate=ft.Rotate(0),
            animate_rotation=ft.Animation(2000, ft.AnimationCurve.LINEAR)
        )
        
        # Start rotation animation
        self._start_sync_animation()
        
        # Current playlist info
        self.playlist_text = ft.Text(
            value="Preparing migration...",
            size=app_config.HEADING_SIZE_SMALL,
            weight=ft.FontWeight.BOLD,
            color=app_config.TEXT_COLOR_LIGHT
        )
        
        # Current track info
        self.track_text = ft.Text(
            value="Track 0 of 0",
            size=app_config.BODY_SIZE,
            color=app_config.TEXT_COLOR_LIGHT
        )
        
        # Current track name
        self.track_name_text = ft.Text(
            value="",
            size=app_config.BODY_SIZE,
            color=app_config.TEXT_COLOR_LIGHT,
            italic=True
        )
        
        # Progress bar
        self.progress_bar = ProgressBar(value=0.0)
        
        # Statistics
        self.matched_text = ft.Text(
            value="✅ Matched: 0 (0%)",
            size=app_config.BODY_SIZE,
            color=app_config.SUCCESS_COLOR,
            weight=ft.FontWeight.BOLD
        )
        
        self.failed_text = ft.Text(
            value="❌ Failed: 0",
            size=app_config.BODY_SIZE,
            color=app_config.ERROR_COLOR,
            weight=ft.FontWeight.BOLD
        )
        
        # Estimated time
        self.time_text = ft.Text(
            value="Estimated time: Calculating...",
            size=app_config.BODY_SIZE,
            color=app_config.TEXT_COLOR_LIGHT
        )
        
        # Tip banner (with width constraint)
        tip_banner = ft.Container(
            content=StatusBanner(
                message="💡 Tip: You can minimize this window. We'll notify you when done!",
                banner_type="info"
            ),
            width=600  # 50% less than typical full width
        )
        
        # Action buttons
        self.pause_button = AppButton(
            text="Pause",
            on_click=self.on_pause_click,
            primary=False
        )
        
        self.cancel_button = AppButton(
            text="Cancel",
            on_click=self.on_cancel_click,
            primary=False
        )
        
        buttons_row = ft.Row(
            controls=[
                self.pause_button,
                self.cancel_button
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            spacing=20
        )
        
        # Main content
        content = ft.Column(
            controls=[
                title,
                ft.Container(height=20),
                self.sync_icon,
                ft.Container(height=30),
                self.playlist_text,
                self.track_text,
                self.track_name_text,
                ft.Container(height=20),
                self.progress_bar,
                ft.Container(height=20),
                self.matched_text,
                self.failed_text,
                ft.Container(height=10),
                self.time_text,
                ft.Container(height=30),
                tip_banner,
                ft.Container(height=20),
                buttons_row
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=10
        )
        
        # Start migration after UI is built
        if hasattr(self.page, 'run_task'):
            self.page.run_task(self.start_migration)
        
        return content
    
    def _start_sync_animation(self):
        """Start the continuous rotation animation for the sync icon."""
        if self.sync_icon:
            # Trigger continuous rotation
            self.sync_icon.rotate.angle = 6.28319  # 2 * pi radians (full rotation)
            if hasattr(self.sync_icon, 'page') and self.sync_icon.page:
                self.sync_icon.update()
    
    async def start_migration(self) -> None:
        """Initialize and start the migration process.
        
        This method:
        1. Validates required data in app_state
        2. Creates MigrationManager instance
        3. Starts background worker
        4. Queues all selected playlists for migration
        5. Monitors completion
        
        Runs asynchronously in the background and updates UI via callbacks.
        """
        try:
            # Validate app_state
            if 'selected_playlists' not in self.app_state:
                self.show_error("No playlists selected for migration")
                return
            
            if 'spotify_client' not in self.app_state:
                self.show_error("Spotify client not initialized")
                return
            
            if 'youtube_client' not in self.app_state:
                self.show_error("YouTube Music client not initialized")
                return
            
            if 'cache_manager' not in self.app_state:
                self.show_error("Cache manager not initialized")
                return
            
            selected_playlists = self.app_state['selected_playlists']
            
            if not selected_playlists:
                self.show_error("No playlists selected")
                return
            
            # Initialize counts
            self.total_playlists = len(selected_playlists)
            self.total_tracks = sum(p.get('tracks_count', 0) for p in selected_playlists)
            self.start_time = time.time()
            
            # Show loading
            self.show_loading(True, "Initializing migration...")
            
            # Create MigrationManager
            self.migration_manager = MigrationManager(
                spotify_client=self.app_state['spotify_client'],
                ytmusic_client=self.app_state['youtube_client'],
                cache_manager=self.app_state['cache_manager']
            )
            
            # Publish the manager so app-level services (background-survival
            # window handling and OS sleep inhibition in main.py) can see that
            # a migration is active. Without this, close-with-job and
            # sleep-inhibition stay inert. See CONTEXT_CONTRACT §4.3.
            self.app_state['migration_manager'] = self.migration_manager

            # Start background worker
            self.migration_manager.start()
            
            # Hide loading
            self.show_loading(False)
            
            # Queue playlists for migration
            job_ids = self.migration_manager.migrate_playlists(
                playlists=selected_playlists,
                progress_callback=self.on_progress_update
            )
            
            # Store job IDs for tracking
            self.app_state['migration_job_ids'] = job_ids
            
        except Exception as e:
            self.show_loading(False)
            self.show_error(f"Failed to start migration: {str(e)}")
    
    def on_progress_update(
        self,
        playlist_name: str,
        current: int,
        total: int,
        track_name: str,
        matched: int = 0,
        failed: int = 0
    ) -> None:
        """Handle progress updates from background migration worker.
        
        This callback is invoked from background threads, so UI updates
        must be thread-safe and throttled to avoid overwhelming the UI.
        
        Args:
            playlist_name (str): Name of current playlist being migrated.
            current (int): Current track index (1-based).
            total (int): Total tracks in current playlist.
            track_name (str): Name of current track being processed.
            matched (int): Number of successfully matched tracks so far.
            failed (int): Number of failed tracks so far.
        """
        with self.update_lock:
            # Debug logging
            
            # Always update state (don't throttle state updates, only UI)
            self.current_playlist_name = playlist_name
            self.current_track_index = current
            self.current_track_name = track_name
            self.matched_count = matched
            self.failed_count = failed
            
            # Check if migration is complete
            # total_tracks is 0 until the migration reports its size; without
            # this guard every early callback looks complete and bypasses throttling
            is_complete = self.total_tracks > 0 and current >= self.total_tracks
            
            # Throttle UI updates to max 1 per second (but always update on completion)
            current_time = time.time()
            should_update_ui = (current_time - self.last_update_time >= 1.0) or is_complete
            
            if should_update_ui:
                self.last_update_time = current_time
                self._update_ui()
            
            # Trigger completion after final UI update
            if is_complete and not self.is_cancelled:
                # Schedule completion (use threading Timer since no event loop in this thread)
                import threading
                timer = threading.Timer(2.0, self.on_migration_complete)
                timer.daemon = True
                timer.start()
    
    def _update_ui(self) -> None:
        """Update all UI elements with current migration state.
        
        This method is called from background threads, so it uses
        page.update() to ensure thread-safe UI updates.
        """
        if not self.page:
            return
        
        # Update playlist info
        if self.playlist_text:
            if self.total_playlists > 1:
                # Multiple playlists - show which one
                playlist_num = self.current_playlist_index + 1
                self.playlist_text.value = (
                    f"Playlist {playlist_num} of {self.total_playlists}: "
                    f"{self.current_playlist_name}"
                )
            else:
                # Single playlist
                self.playlist_text.value = self.current_playlist_name
        
        # Update track info
        if self.track_text:
            self.track_text.value = f"Track {self.current_track_index} of {self.total_tracks}"
        
        # Update track name
        if self.track_name_text:
            self.track_name_text.value = f'"{self.current_track_name}"'
        
        # Update progress bar
        if self.progress_bar and self.total_tracks > 0:
            progress = self.current_track_index / self.total_tracks
            # Update progress bar values
            self.progress_bar.value = progress
            self.progress_bar.progress_bar.value = progress
            percentage = int(progress * 100)
            self.progress_bar.text_label.value = f"{percentage}%"
            # Only call update() if added to page
            if hasattr(self.progress_bar, 'page') and self.progress_bar.page:
                self.progress_bar.update()
        
        # Update statistics
        if self.matched_text:
            completed = self.matched_count + self.failed_count
            if completed > 0:
                match_percent = (self.matched_count / completed) * 100
                self.matched_text.value = (
                    f"✅ Matched: {self.matched_count} ({match_percent:.1f}%)"
                )
            else:
                self.matched_text.value = "✅ Matched: 0 (0%)"
        
        if self.failed_text:
            self.failed_text.value = f"❌ Failed: {self.failed_count}"
        
        # Update estimated time
        if self.time_text:
            estimated = self.calculate_estimated_time()
            self.time_text.value = f"Estimated time: {estimated}"
        
        # Update the page
        self.page.update()
    
    def calculate_estimated_time(self) -> str:
        """Calculate estimated time remaining for migration.
        
        Uses elapsed time and completed tracks to estimate remaining time.
        
        Returns:
            str: Formatted time string (e.g., "5 minutes", "1 hour 23 minutes").
        """
        if not self.start_time or self.total_tracks == 0:
            return "Calculating..."
        
        completed_tracks = self.matched_count + self.failed_count
        
        if completed_tracks == 0:
            return "Calculating..."
        
        # Calculate average time per track
        elapsed = time.time() - self.start_time
        avg_time_per_track = elapsed / completed_tracks
        
        # Calculate remaining tracks and time
        remaining_tracks = self.total_tracks - completed_tracks
        estimated_seconds = remaining_tracks * avg_time_per_track
        
        # Format time
        if estimated_seconds < 60:
            return "Less than 1 minute"
        elif estimated_seconds < 3600:
            minutes = int(estimated_seconds / 60)
            return f"{minutes} minute{'s' if minutes != 1 else ''}"
        else:
            hours = int(estimated_seconds / 3600)
            remaining_minutes = int((estimated_seconds % 3600) / 60)
            if remaining_minutes > 0:
                return (
                    f"{hours} hour{'s' if hours != 1 else ''} "
                    f"{remaining_minutes} minute{'s' if remaining_minutes != 1 else ''}"
                )
            else:
                return f"{hours} hour{'s' if hours != 1 else ''}"
    
    def on_pause_click(self, e) -> None:
        """Handle pause/resume button click.
        
        Toggles between paused and running states. When paused, the current
        track completes but no new tracks are started.
        
        Args:
            e: Flet event object.
        """
        if not self.migration_manager:
            return
        
        try:
            if self.is_paused:
                # Resume
                self.migration_manager.resume_migrations()
                self.is_paused = False
                
                # Update button
                if self.pause_button:
                    self.pause_button.text = "Pause"
                
                # Hide status banner
                if self.status_banner:
                    self.status_banner.visible = False
                
                self.page.update()
                
            else:
                # Pause
                self.migration_manager.pause_migrations()
                self.is_paused = True
                
                # Update button
                if self.pause_button:
                    self.pause_button.text = "Resume"
                
                # Show status banner
                if not self.status_banner:
                    self.status_banner = StatusBanner(
                        message="Migration paused. Click Resume to continue.",
                        banner_type="warning"
                    )
                    # Add to page overlay
                    self.page.overlay.append(self.status_banner)
                else:
                    self.status_banner.visible = True
                    self.status_banner.message = "Migration paused. Click Resume to continue."
                
                self.page.update()
                
        except Exception as ex:
            self.show_error(f"Failed to pause/resume migration: {str(ex)}")
    
    def on_cancel_click(self, e) -> None:
        """Handle cancel button click.
        
        Shows confirmation dialog before cancelling migration. If confirmed,
        stops all migrations and returns to playlist selection screen.
        
        Args:
            e: Flet event object.
        """
        self.show_confirmation(
            message="Are you sure you want to cancel? All progress will be lost.",
            on_confirm=self._handle_cancel_confirmed,
            on_cancel=None,
            confirm_text="Yes, Cancel",
            cancel_text="No, Continue"
        )
    
    def _handle_cancel_confirmed(self, e) -> None:
        """Handle confirmed cancellation.
        
        Stops migration manager, cleans up resources, and navigates back.
        
        Args:
            e: Flet event object.
        """
        try:
            self.is_cancelled = True
            
            # Stop migration manager
            if self.migration_manager:
                self.show_loading(True, "Cancelling migration...")
                cancelled_count = self.migration_manager.cancel_all(force=True)
                self.migration_manager.stop()
                self.show_loading(False)
            
            # Navigate back to playlist selection
            from src.ui.screens.playlist_selection_screen import PlaylistSelectionScreen
            self.navigate_to(PlaylistSelectionScreen, progress_text="Step 2 of 5")
            
        except Exception as ex:
            self.show_loading(False)
            self.show_error(f"Failed to cancel migration: {str(ex)}")
    
    def on_migration_complete(self) -> None:
        """Handle migration completion.
        
        Called when all migrations finish. Stores results in app_state
        and navigates to results screen.
        """
        # Store results in app_state
        self.app_state['migration_results'] = {
            'total_playlists': self.total_playlists,
            'total_tracks': self.total_tracks,
            'matched_count': self.matched_count,
            'failed_count': self.failed_count,
            'duration': time.time() - self.start_time if self.start_time else 0
        }
        
        # Navigate to results screen
        from src.ui.screens.results_screen import ResultsScreen
        self.navigate_to(ResultsScreen, progress_text="Step 5 of 5")
    
    def _handle_back(self, e):
        """Handle back button click.
        
        Back button is disabled during migration, so this should not be called.
        
        Args:
            e: Flet event object.
        """
        # Migration screen does not allow back navigation
        pass
