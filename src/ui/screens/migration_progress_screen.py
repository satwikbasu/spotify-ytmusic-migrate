"""Migration Progress Screen for real-time migration monitoring.

This screen displays live progress updates during playlist migrations, including:
- Current playlist and track being processed
- Overall progress bar with percentage (across ALL selected playlists)
- Success/failure statistics
- Estimated time remaining
- Why the job is waiting (reconnect needed / throttled), when it is
- Pause/resume and cancel controls

Two update sources feed the screen:

1. Per-track progress callbacks from the worker (``on_progress_update``) give
   the live "which song right now" text. They are per playlist and cannot say
   whether the whole batch is done.
2. A 1 s poll of ``MigrationManager.get_batch_progress(job_ids)`` /
   ``get_migration_status()`` drives the overall progress bar, the aggregate
   counters, the auth/throttle banners, and the completion decision. The
   persisted job rows are the source of truth, so this is correct for 1 or
   50 playlists and for jobs resumed after a restart.

Example:
    >>> screen = MigrationProgressScreen(page, app_state)
    >>> screen.show(show_back=False, progress_text="Step 3 of 5")
    >>> # Migration starts automatically on show
"""

import flet as ft
import logging
import time
import threading
from typing import Optional, Dict, Any, List
from datetime import datetime

from src.ui.base_screen import BaseScreen
from src.ui.components import AppButton, ProgressBar, StatusBanner
from src.migrators.migration_manager import MigrationManager
from config import app_config

logger = logging.getLogger(__name__)


class MigrationProgressScreen(BaseScreen):
    """Screen for monitoring real-time migration progress.

    Displays live updates as playlists are migrated from Spotify to YouTube Music.
    Features include:
    - Animated sync icon that rotates continuously
    - Real-time track and playlist progress
    - Overall progress across every selected playlist
    - Success/failure counters
    - Estimated time remaining calculation
    - "Reconnect needed" / "Waiting — throttled until HH:MM" banners
    - Pause/resume functionality
    - Cancel with confirmation dialog
    - Thread-safe UI updates from background workers

    Attributes:
        migration_manager (Optional[MigrationManager]): Migration orchestrator.
        job_ids (List[str]): Job ids of this run (one per queued playlist).
        current_playlist_index (int): Index of current playlist (0-based).
        current_playlist_name (str): Name of currently processing playlist.
        current_track_index (int): Index of current track in that playlist (1-based).
        current_playlist_total (int): Tracks in the current playlist.
        total_playlists (int): Total number of playlists to migrate.
        total_tracks (int): Total number of tracks across all playlists.
        processed_tracks (int): Tracks processed across all playlists.
        matched_count (int): Number of successfully matched tracks (all playlists).
        failed_count (int): Number of failed track migrations (all playlists).
        start_time (Optional[float]): Unix timestamp when migration started.
        is_paused (bool): Whether migration is currently paused.
        is_cancelled (bool): Whether migration has been cancelled.
        is_complete (bool): Whether the whole batch reached a terminal state.
        last_update_time (float): Unix timestamp of last UI update.
        update_lock (threading.Lock): Thread lock for safe UI updates.
    """

    # Cadence of the status poll (and of per-track UI refreshes).
    POLL_INTERVAL_SECONDS = 1.0
    # Short delay so the final 100% state is visible before Results.
    COMPLETION_DELAY_SECONDS = 2.0

    AUTH_BANNER_TEXT = (
        "YouTube Music sign-in expired — reconnect to resume. "
        "Your progress is saved; nothing is lost."
    )

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
        self.job_ids: List[str] = []
        self.current_playlist_index = 0
        self.current_playlist_name = ""
        self.current_track_index = 0
        self.current_playlist_total = 0
        self.current_track_name = ""
        self.total_playlists = 0
        self.total_tracks = 0
        self.processed_tracks = 0
        self.matched_count = 0
        self.failed_count = 0
        self.start_time: Optional[float] = None
        self.is_paused = False
        self.is_cancelled = False
        self.is_complete = False
        self.last_batch: Optional[Dict[str, Any]] = None

        # UI update throttling
        self.last_update_time = 0.0
        self.update_lock = threading.Lock()
        self._poll_timer: Optional[threading.Timer] = None

        # UI component references
        self.sync_icon: Optional[ft.Icon] = None
        self.playlist_text: Optional[ft.Text] = None
        self.track_text: Optional[ft.Text] = None
        self.track_name_text: Optional[ft.Text] = None
        self.overall_text: Optional[ft.Text] = None
        self.progress_bar: Optional[ProgressBar] = None
        self.matched_text: Optional[ft.Text] = None
        self.failed_text: Optional[ft.Text] = None
        self.time_text: Optional[ft.Text] = None
        self.pause_button: Optional[AppButton] = None
        self.cancel_button: Optional[AppButton] = None
        self.status_banner: Optional[StatusBanner] = None
        # Holder for the "why are we waiting" banner (auth / throttle).
        self.wait_banner_holder: Optional[ft.Container] = None
        self.wait_banner_kind: Optional[str] = None
        self.wait_banner_text: str = ""
        self.reconnect_button: Optional[ft.TextButton] = None
        self.reconnect_row: Optional[ft.Row] = None
        self.reconnect_status: Optional[ft.Text] = None

    def build(self) -> ft.Control:
        """Build the migration progress screen UI.

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

        # Current track info (within the current playlist)
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

        # Overall progress across all playlists
        self.overall_text = ft.Text(
            value="",
            size=app_config.CAPTION_SIZE,
            color=app_config.TEXT_COLOR_LIGHT
        )

        # Progress bar (overall)
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

        # "Why are we waiting" banner: hidden until auth/throttle says so
        self.wait_banner_holder = ft.Container(content=None, visible=False, width=600)
        # Manual Reconnect for the auth banner (shown only while auth is needed)
        self.reconnect_button = ft.TextButton(
            text="Reconnect YouTube Music", on_click=self._on_reconnect_click
        )
        self.reconnect_status = ft.Text(value="", size=app_config.CAPTION_SIZE)
        self.reconnect_row = ft.Row(
            controls=[self.reconnect_button, self.reconnect_status],
            visible=False, width=600,
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
                self.overall_text,
                ft.Container(height=20),
                self.matched_text,
                self.failed_text,
                ft.Container(height=10),
                self.time_text,
                ft.Container(height=20),
                self.wait_banner_holder,
                self.reconnect_row,
                ft.Container(height=10),
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
        5. Starts the status poll that tracks the whole batch to completion
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

            # Initialize counts (refined from the job rows once queued)
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

            # Wire auth-pause -> silent re-capture through the extension bridge.
            hub = self.app_state.get('capture_hub')
            if hub is not None:
                try:
                    hub.attach_engine(self.migration_manager)
                except Exception as e:
                    logger.warning(f"Could not attach capture hub: {e}")

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
            self.job_ids = list(job_ids or [])
            self.app_state['migration_job_ids'] = self.job_ids
            self.total_playlists = len(self.job_ids) or self.total_playlists

            if not self.job_ids:
                self.show_error(
                    "Nothing to migrate — the selected playlists have no songs."
                )
                return

            # Track the whole batch from the job rows
            self._schedule_poll(delay=0.0)

        except Exception as e:
            self.show_loading(False)
            self.show_error(f"Failed to start migration: {str(e)}")

    # ------------------------------------------------------------------
    # Status poll (batch progress, completion, auth/throttle visibility)
    # ------------------------------------------------------------------

    def _schedule_poll(self, delay: Optional[float] = None) -> None:
        """Schedule the next status refresh on a daemon timer."""
        if self.is_cancelled or self.is_complete:
            return
        interval = self.POLL_INTERVAL_SECONDS if delay is None else delay
        timer = threading.Timer(interval, self._poll_status)
        timer.daemon = True
        self._poll_timer = timer
        timer.start()

    def _cancel_poll(self) -> None:
        """Stop any pending status refresh."""
        timer = self._poll_timer
        self._poll_timer = None
        if timer is not None:
            timer.cancel()

    def _poll_status(self) -> None:
        """Timer target: refresh once, then either finish or reschedule."""
        try:
            done = self.refresh_from_manager()
        except Exception:
            done = False
        if self.is_cancelled:
            return
        if done:
            self._finish(self.last_batch)
        else:
            self._schedule_poll()

    def refresh_from_manager(self) -> bool:
        """Pull batch progress and status from the manager and update the UI.

        Returns:
            bool: True when every job of this run is in a terminal state
                (completed/failed). A ``paused_auth`` job or a throttled wait
                returns False — the batch is waiting, not done.
        """
        if not self.migration_manager or not self.job_ids:
            return False

        batch = self.migration_manager.get_batch_progress(self.job_ids)
        status: Dict[str, Any] = {}
        try:
            status = self.migration_manager.get_migration_status() or {}
        except Exception:
            status = {}

        with self.update_lock:
            self._apply_batch(batch)
            self._apply_wait_state(batch, status)
            self.last_batch = batch
            self.last_update_time = time.time()
            self._update_ui()

        return bool(batch.get('all_done')) and not self.is_cancelled

    def _apply_batch(self, batch: Dict[str, Any]) -> None:
        """Copy aggregate numbers from a batch-progress dict into screen state."""
        jobs = batch.get('jobs') or []
        if jobs:
            self.total_playlists = len(jobs)
        if batch.get('total_tracks'):
            self.total_tracks = int(batch['total_tracks'])
        self.processed_tracks = int(batch.get('processed_tracks') or 0)
        self.matched_count = int(batch.get('matched_tracks') or 0)
        self.failed_count = int(batch.get('failed_tracks') or 0)

        # Which playlist is "current": the running one, else the next waiting
        # one, else the last one (all terminal).
        running = [i for i, j in enumerate(jobs) if j.get('status') == 'in_progress']
        waiting = [
            i for i, j in enumerate(jobs)
            if j.get('status') in ('queued', MigrationManager.PAUSED_AUTH_STATUS)
        ]
        if running:
            idx = running[0]
        elif waiting:
            idx = waiting[0]
        elif jobs:
            idx = len(jobs) - 1
        else:
            idx = 0
        self.current_playlist_index = idx
        if jobs:
            job = jobs[idx]
            self.current_playlist_name = job.get('playlist_name') or self.current_playlist_name
            self.current_playlist_total = int(job.get('total_tracks') or 0)
            if job.get('status') in ('completed', 'failed'):
                self.current_track_index = self.current_playlist_total

    def _apply_wait_state(self, batch: Dict[str, Any], status: Dict[str, Any]) -> None:
        """Decide which (if any) waiting banner to show."""
        auth_required = bool(batch.get('auth_required') or status.get('auth_required'))
        throttle = status.get('throttle') or batch.get('throttle') or {}

        if auth_required:
            self._set_wait_banner('auth', self.AUTH_BANNER_TEXT)
        elif throttle.get('throttled'):
            self._set_wait_banner('throttle', self._throttle_message(throttle))
        else:
            self._set_wait_banner(None, "")

    @staticmethod
    def _throttle_message(throttle: Dict[str, Any]) -> str:
        """Build the non-technical throttle banner text."""
        until = throttle.get('until')
        when = ""
        if until:
            try:
                when = datetime.fromtimestamp(float(until)).strftime('%H:%M')
            except (TypeError, ValueError, OSError, OverflowError):
                when = ""
        if when:
            return (
                f"Waiting — throttled until {when}. YouTube Music asked us to "
                "slow down; the migration continues automatically."
            )
        message = (throttle.get('message') or "").strip()
        if message:
            return f"Waiting — {message}"
        return "Waiting — YouTube Music asked us to slow down; the migration continues automatically."

    def _set_wait_banner(self, kind: Optional[str], text: str) -> None:
        """Show/hide the waiting banner. Rebuilds the control only on change."""
        if kind == self.wait_banner_kind and text == self.wait_banner_text:
            return
        self.wait_banner_kind = kind
        self.wait_banner_text = text
        if not self.wait_banner_holder:
            return
        if self.reconnect_row is not None:
            self.reconnect_row.visible = (kind == 'auth')
        if kind is None:
            self.wait_banner_holder.content = None
            self.wait_banner_holder.visible = False
        else:
            self.wait_banner_holder.content = StatusBanner(
                message=text,
                banner_type="error" if kind == 'auth' else "warning"
            )
            self.wait_banner_holder.visible = True

    def _on_reconnect_click(self, e=None) -> None:
        """Manual Reconnect on the auth banner: ask the extension for a fresh sign-in."""
        hub = self.app_state.get('capture_hub')
        if hub is None:
            self._set_reconnect_status(
                "The connection helper isn't running. Please restart the app.")
            return
        self._set_reconnect_status("Reconnecting...")
        if self.reconnect_button is not None:
            self.reconnect_button.disabled = True

        def work():
            try:
                res = hub.request_capture("reauth")
            except Exception as ex:
                logger.error(f"Reconnect failed: {type(ex).__name__}")
                res = None
            self._on_reconnect_result(res)

        threading.Thread(target=work, name="yt-reconnect", daemon=True).start()

    RECONNECT_MESSAGES = {
        "no_extension": "We can't see the browser extension. Open your browser, then try again.",
        "signed_out": "You're not signed in to YouTube Music in your browser. Sign in there, then try again.",
        "network": "We couldn't reach YouTube Music. Check your internet and try again.",
        "rate_limited": "YouTube Music asked us to slow down. Wait a minute, then try again.",
    }

    def _on_reconnect_result(self, res) -> None:
        if self.reconnect_button is not None:
            self.reconnect_button.disabled = False
        if res is not None and getattr(res, "ok", False):
            self.app_state['youtube_client'] = res.client
            self._set_reconnect_status("Reconnected.")
            # The engine swaps the client and re-queues parked jobs; the next
            # poll clears the banner once auth_required is no longer set.
        else:
            code = getattr(res, "code", None)
            self._set_reconnect_status(self.RECONNECT_MESSAGES.get(
                code, "We couldn't reconnect. Make sure you're signed in to YouTube Music, then try again."))

    def _set_reconnect_status(self, text: str) -> None:
        if self.reconnect_status is not None:
            self.reconnect_status.value = text
        try:
            self.page.update()
        except Exception:
            pass

    def _finish(self, batch: Optional[Dict[str, Any]]) -> None:
        """Mark the batch complete and move to Results after a short beat."""
        if self.is_complete or self.is_cancelled:
            return
        self.is_complete = True
        self._cancel_poll()
        timer = threading.Timer(
            self.COMPLETION_DELAY_SECONDS, self.on_migration_complete, kwargs={'batch': batch}
        )
        timer.daemon = True
        timer.start()

    # ------------------------------------------------------------------
    # Per-track progress (live "which song" text)
    # ------------------------------------------------------------------

    def on_progress_update(
        self,
        playlist_name: str,
        current: int,
        total: int,
        track_name: str,
        matched: int = 0,
        failed: int = 0
    ) -> None:
        """Handle per-track progress updates from the background worker.

        Updates the live playlist/track text. Completion and the overall
        progress bar are NOT derived here — ``current``/``total`` belong to
        one playlist — they come from ``refresh_from_manager()``.

        Args:
            playlist_name (str): Name of current playlist being migrated.
            current (int): Current track index within that playlist (1-based).
            total (int): Total tracks in that playlist.
            track_name (str): Name of current track being processed.
            matched (int): Matched tracks so far in that playlist.
            failed (int): Failed tracks so far in that playlist.
        """
        with self.update_lock:
            self.current_playlist_name = playlist_name
            self.current_track_index = current
            self.current_playlist_total = total
            self.current_track_name = track_name

            # Before the first poll result arrives, the per-playlist counters
            # are the best numbers we have. After it, the batch owns them.
            if self.last_batch is None:
                self.matched_count = matched
                self.failed_count = failed
                self.processed_tracks = current

            # Throttle UI updates to max 1 per second
            current_time = time.time()
            if current_time - self.last_update_time >= self.POLL_INTERVAL_SECONDS:
                self.last_update_time = current_time
                self._update_ui()

    def _update_ui(self) -> None:
        """Update all UI elements with current migration state.

        Called from background threads; uses page.update() for thread-safe
        UI updates.
        """
        if not self.page:
            return

        # Update playlist info
        if self.playlist_text:
            if self.total_playlists > 1:
                playlist_num = min(self.current_playlist_index + 1, self.total_playlists)
                self.playlist_text.value = (
                    f"Playlist {playlist_num} of {self.total_playlists}: "
                    f"{self.current_playlist_name}"
                )
            else:
                self.playlist_text.value = self.current_playlist_name

        # Update track info (within the current playlist)
        if self.track_text:
            per_playlist_total = self.current_playlist_total or self.total_tracks
            self.track_text.value = f"Track {self.current_track_index} of {per_playlist_total}"

        # Update track name
        if self.track_name_text:
            self.track_name_text.value = f'"{self.current_track_name}"' if self.current_track_name else ""

        # Overall progress across playlists
        overall_done = min(self.processed_tracks, self.total_tracks) if self.total_tracks else self.processed_tracks
        if self.overall_text:
            if self.total_playlists > 1 and self.total_tracks:
                self.overall_text.value = (
                    f"{overall_done:,} of {self.total_tracks:,} songs across "
                    f"{self.total_playlists} playlists"
                )
            else:
                self.overall_text.value = ""

        # Update progress bar (overall)
        if self.progress_bar and self.total_tracks > 0:
            progress = max(0.0, min(1.0, overall_done / self.total_tracks))
            self.progress_bar.value = progress
            self.progress_bar.progress_bar.value = progress
            percentage = int(progress * 100)
            self.progress_bar.text_label.value = f"{percentage}%"
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
            if self.wait_banner_kind == 'auth':
                self.time_text.value = "Waiting for you to reconnect YouTube Music"
            else:
                estimated = self.calculate_estimated_time()
                self.time_text.value = f"Estimated time: {estimated}"

        # Update the page
        self.page.update()

    def calculate_estimated_time(self) -> str:
        """Calculate estimated time remaining for migration.

        Uses elapsed time and completed tracks (across all playlists) to
        estimate remaining time.

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
        remaining_tracks = max(0, self.total_tracks - completed_tracks)
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
            self._cancel_poll()

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

    def build_results(self, batch: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Build the aggregate results handed to the Results screen.

        Args:
            batch: A ``get_batch_progress()`` dict. When None, the screen's own
                counters are used (single-source fallback).

        Returns:
            Dict with ``migration_results`` (totals) and ``playlist_results``
            (per-playlist breakdown, or [] when no batch is available).
        """
        duration = time.time() - self.start_time if self.start_time else 0
        if not batch:
            return {
                'migration_results': {
                    'total_playlists': self.total_playlists,
                    'total_tracks': self.total_tracks,
                    'matched_count': self.matched_count,
                    'failed_count': self.failed_count,
                    'playlists_created': 0,
                    'failed_playlists': 0,
                    'duration': duration,
                },
                'playlist_results': [],
            }

        jobs = batch.get('jobs') or []
        per_playlist = []
        for job in jobs:
            ids = list(job.get('youtube_playlist_ids') or [])
            per_playlist.append({
                'name': job.get('playlist_name') or 'Playlist',
                'status': job.get('status'),
                'total_tracks': int(job.get('total_tracks') or 0),
                'matched_tracks': int(job.get('matched_tracks') or 0),
                'failed_count': int(job.get('failed_tracks') or 0),
                'failed_tracks': [],  # per-track detail is not persisted
                'youtube_playlist_ids': ids,
                'youtube_playlist_url': (
                    f"https://music.youtube.com/playlist?list={ids[0]}" if ids else ''
                ),
                'shard_count': len(ids),
                'error_message': job.get('error_message'),
            })

        return {
            'migration_results': {
                'total_playlists': int(batch.get('total_jobs') or len(jobs)),
                'total_tracks': int(batch.get('total_tracks') or 0),
                'matched_count': int(batch.get('matched_tracks') or 0),
                'failed_count': int(batch.get('failed_tracks') or 0),
                'playlists_created': int(batch.get('playlists_created') or 0),
                'failed_playlists': int(batch.get('failed_jobs') or 0),
                'duration': duration,
            },
            'playlist_results': per_playlist,
        }

    def on_migration_complete(self, batch: Optional[Dict[str, Any]] = None) -> None:
        """Handle migration completion.

        Called when every job of this run is completed/failed. Stores the
        aggregate results in app_state and navigates to the results screen.

        Args:
            batch: The final ``get_batch_progress()`` dict, if available.
        """
        if self.is_cancelled:
            return
        self.is_complete = True
        self._cancel_poll()

        results = self.build_results(batch if batch is not None else self.last_batch)
        self.app_state['migration_results'] = results['migration_results']
        self.app_state['playlist_results'] = results['playlist_results']

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
