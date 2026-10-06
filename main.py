"""Spotify to YouTube Music Playlist Migrator - Main Entry Point.

This is the main application entry point that initializes the Flet UI,
sets up logging, configures the application window, and manages the
application lifecycle.

Features:
- Comprehensive logging to file
- Graceful shutdown and cleanup
- Global exception handling
- Application state management
- Window event handling

Example:
    Run the application:
    
    $ python main.py
"""

import sys

# Native-messaging host mode: the browser spawns "<app> --native-host". Dispatch
# BEFORE importing flet (or anything heavy) so the host starts in well under 1 s.
if "--native-host" in sys.argv[1:]:
    from src.capture.host import main as _native_host_main
    sys.exit(_native_host_main())

import flet as ft
import logging
import os
import threading
from pathlib import Path
from typing import Optional

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()  # Load .env file from current directory
    logging.info("Loaded environment variables from .env file")
except ImportError:
    logging.warning("python-dotenv not installed - .env file will not be loaded")

# Import application modules
from config import app_config
from src.ui.screens.welcome_screen import WelcomeScreen
from src.utils.cache_manager import CacheManager
from src.utils import power


# ============================================================================
# Logging Configuration
# ============================================================================

def setup_logging() -> None:
    """Configure application logging.
    
    Sets up logging to both file and console with appropriate levels
    and formatting. Log files are stored in the application directory.
    """
    # Ensure app directories exist
    app_config.ensure_app_directories()
    
    # Create log file path
    log_dir = Path.home() / ".playlist_migrator"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / "app.log"
    
    # Configure root logger
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            # File handler - detailed logging
            logging.FileHandler(log_file, encoding='utf-8'),
            # Console handler - important messages only
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    # Set specific log levels for noisy libraries
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('spotipy').setLevel(logging.WARNING)
    logging.getLogger('ytmusicapi').setLevel(logging.WARNING)
    
    logger = logging.getLogger(__name__)
    logger.info("=" * 70)
    logger.info("Spotify to YouTube Music Playlist Migrator")
    logger.info("=" * 70)
    logger.info(f"Log file: {log_file}")
    logger.info(f"Python version: {sys.version}")


# ============================================================================
# Application State Management
# ============================================================================

def initialize_app_state() -> dict:
    """Initialize the shared application state dictionary.
    
    The app_state dictionary is passed to all screens and contains
    shared data and services used throughout the application lifecycle.
    
    Returns:
        dict: Initialized application state dictionary with keys:
            - spotify_client: Authenticated Spotify client (None initially)
            - youtube_client: Authenticated YouTube Music client (None initially)
            - token_manager: OAuth token manager (None initially)
            - cache_manager: Cache and database manager
            - rate_limiter: API rate limiter (None initially)
            - selected_playlists: List of playlists selected for migration
            - migration_results: Overall migration statistics
            - playlist_results: Detailed per-playlist results
            - migration_manager: Migration orchestrator (None initially)
            - migration_job_ids: List of background job IDs
    """
    logger = logging.getLogger(__name__)
    logger.info("Initializing application state...")
    
    # Initialize cache manager
    try:
        cache_manager = CacheManager(db_path=app_config.CACHE_DB_PATH)
        logger.info(f"Cache manager initialized: {app_config.CACHE_DB_PATH}")
    except Exception as e:
        logger.error(f"Failed to initialize cache manager: {e}")
        cache_manager = None
    
    app_state = {
        # Authentication clients
        'spotify_client': None,
        'youtube_client': None,
        'token_manager': None,
        
        # Services
        'cache_manager': cache_manager,
        'rate_limiter': None,
        'migration_manager': None,
        
        # User selections and results
        'selected_playlists': [],
        'migration_results': {},
        'playlist_results': [],
        'migration_job_ids': [],
        'capture_hub': None,
    }

    # Capture hub: lets the browser extension (via the native host) hand over
    # the YouTube Music session. Failure must never block the app.
    if not os.environ.get("PLAYLIST_MIGRATOR_NO_HUB"):
        try:
            from src.capture.hub import CaptureHub
            hub = CaptureHub()
            hub.start()
            app_state['capture_hub'] = hub
        except Exception as e:
            logger.warning(f"Capture hub unavailable: {e}")
    
    logger.info("Application state initialized successfully")
    return app_state


# ============================================================================
# Application Lifecycle Management
# ============================================================================

def cleanup_app_state(app_state: dict) -> None:
    """Clean up application resources on shutdown.
    
    Stops background workers, closes database connections, and performs
    any other necessary cleanup to ensure graceful shutdown.
    
    Args:
        app_state (dict): Application state dictionary containing services.
    """
    logger = logging.getLogger(__name__)
    logger.info("Cleaning up application resources...")
    
    try:
        hub = app_state.get('capture_hub')
        if hub is not None:
            hub.stop()

        # Stop migration manager if running
        if app_state.get('migration_manager'):
            logger.info("Stopping migration manager...")
            migration_manager = app_state['migration_manager']
            if hasattr(migration_manager, 'stop'):
                migration_manager.stop()
        
        # Close cache manager
        if app_state.get('cache_manager'):
            logger.info("Closing cache manager...")
            cache_manager = app_state['cache_manager']
            if hasattr(cache_manager, 'close'):
                cache_manager.close()
        
        logger.info("Cleanup completed successfully")
    
    except Exception as e:
        logger.error(f"Error during cleanup: {e}", exc_info=True)


# ============================================================================
# Background survival (CONTEXT_CONTRACT §4.3)
#
# The user clicks Start and walks away. Closing the window with an active job
# must NOT kill the job: the window hides to a tray icon (or minimizes when no
# tray is available) and the migration keeps running. The OS is also asked not
# to sleep while a job is active. Nothing here edits MigrationManager; it only
# reads its existing get_migration_status() and calls stop().
# ============================================================================

SLEEP_GUARD_INTERVAL_SECONDS = 5.0
SLEEP_REASON = "Migrating playlists to YouTube Music"


def is_migration_active(app_state: dict) -> bool:
    """Return True if a migration job is running or queued.

    Reads ``MigrationManager.get_migration_status()`` (its existing public API).
    A job counts as active when the worker is running AND there is a current
    job, an in-progress job, or anything still queued. Any error (manager
    missing, stopped, or misbehaving) is treated as "not active" so that a
    broken manager can never trap the user in a window that refuses to close.

    Note: this relies on the progress screen publishing its manager under
    ``app_state['migration_manager']``.
    """
    manager = app_state.get('migration_manager') if app_state else None
    if manager is None:
        return False
    try:
        status = manager.get_migration_status()
        if not status.get('is_running', False):
            return False
        return bool(
            status.get('current_job')
            or status.get('in_progress_jobs', 0) > 0
            or status.get('queued_jobs', 0) > 0
            or status.get('queue_size', 0) > 0
        )
    except Exception as e:
        logging.getLogger(__name__).debug(f"Could not read migration status: {e}")
        return False


class SleepGuard:
    """Keep the OS awake while a migration is active.

    A small daemon thread polls :func:`is_migration_active` and acquires or
    releases an OS sleep inhibition (``src.utils.power``) to match. The same
    thread does both, which Windows' ``SetThreadExecutionState`` requires.
    """

    def __init__(self, app_state: dict, interval: float = SLEEP_GUARD_INTERVAL_SECONDS):
        self.app_state = app_state
        self.interval = interval
        self.handle: Optional[power.SleepInhibitor] = None
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._logger = logging.getLogger(__name__)

    @property
    def inhibiting(self) -> bool:
        return self.handle is not None and self.handle.active

    def tick(self) -> None:
        """One poll: reconcile the inhibition with the migration state."""
        try:
            active = is_migration_active(self.app_state)
            if active and self.handle is None:
                self.handle = power.inhibit_sleep(SLEEP_REASON)
                self._logger.info(f"Sleep guard engaged ({self.handle.backend})")
            elif not active and self.handle is not None:
                self.release()
        except Exception as e:
            self._logger.warning(f"Sleep guard tick failed: {e}")

    def release(self) -> None:
        if self.handle is not None:
            power.release_sleep(self.handle)
            self.handle = None
            self._logger.info("Sleep guard released")

    def _run(self) -> None:
        while not self._stop.wait(self.interval):
            self.tick()
        self.release()

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="sleep-guard", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=self.interval + 2)
        # If the thread never ran (or is gone), release from here.
        self.release()


class TrayIcon:
    """Optional system-tray / menubar icon shown while the window is hidden.

    Uses ``pystray`` + ``Pillow`` if they are installed and a display exists.
    Both are optional: :meth:`start` returns False (and the caller falls back
    to minimizing) whenever the tray cannot be created. Never raises.
    """

    def __init__(self, on_show, on_quit, title: str = "Playlist Migrator"):
        self.on_show = on_show
        self.on_quit = on_quit
        self.title = title
        self._icon = None
        self._logger = logging.getLogger(__name__)

    @staticmethod
    def _make_image():
        from PIL import Image, ImageDraw  # optional dependency
        size = 64
        image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.ellipse((4, 4, size - 4, size - 4), fill=(29, 185, 84, 255))
        draw.polygon([(24, 18), (24, 46), (46, 32)], fill=(255, 255, 255, 255))
        return image

    def start(self) -> bool:
        try:
            import pystray  # importing can itself fail headless (no $DISPLAY)
            menu = pystray.Menu(
                pystray.MenuItem("Show", lambda icon, item: self.on_show(), default=True),
                pystray.MenuItem("Quit (stops migration)", lambda icon, item: self.on_quit()),
            )
            self._icon = pystray.Icon(
                "playlist_migrator", self._make_image(), self.title, menu
            )
            self._icon.run_detached()
            self._logger.info("Tray icon shown; migration continues in background")
            return True
        except Exception as e:
            self._icon = None
            self._logger.info(f"System tray unavailable ({e}); falling back to minimize")
            return False

    def stop(self) -> None:
        icon, self._icon = self._icon, None
        if icon is not None:
            try:
                icon.stop()
            except Exception as e:
                self._logger.debug(f"Tray stop failed: {e}")


def _set_window_hidden(page, hidden: bool) -> None:
    """Hide/show the Flet window without destroying it. Never raises."""
    try:
        window = page.window
        if hidden:
            window.skip_task_bar = True
            window.visible = False
        else:
            window.skip_task_bar = False
            window.visible = True
            window.minimized = False
        page.update()
        if not hidden:
            try:
                window.to_front()
            except Exception:
                pass
    except Exception as e:
        logging.getLogger(__name__).debug(f"Window visibility change failed: {e}")


def show_window(page, app_state: dict) -> None:
    """Restore the window from the tray (tray menu 'Show')."""
    tray = app_state.pop('tray_icon', None)
    if tray is not None:
        tray.stop()
    _set_window_hidden(page, False)


def quit_application(page, app_state: dict) -> None:
    """Really quit: stop the migration, release resources, destroy the window."""
    logger = logging.getLogger(__name__)
    logger.info("Quitting application")
    tray = app_state.pop('tray_icon', None)
    if tray is not None:
        tray.stop()
    cleanup_app_state(app_state)
    if page is not None:
        try:
            page.window.destroy()
        except Exception as e:
            logger.debug(f"Window destroy failed: {e}")
    logger.info("Application shutdown complete")


def hide_to_background(page, app_state: dict) -> str:
    """Keep the job running and get the window out of the way.

    Returns ``'tray'`` if a tray icon was created, else ``'minimized'``.
    """
    logger = logging.getLogger(__name__)
    logger.info("Migration active; hiding window instead of exiting")
    tray = TrayIcon(
        on_show=lambda: show_window(page, app_state),
        on_quit=lambda: quit_application(page, app_state),
    )
    if tray.start():
        app_state['tray_icon'] = tray
        _set_window_hidden(page, True)
        return 'tray'
    # No tray: minimize and keep running (never crash, never kill the job).
    try:
        page.window.minimized = True
        page.update()
    except Exception as e:
        logger.debug(f"Minimize failed: {e}")
    return 'minimized'


def handle_window_event(e: ft.ControlEvent, app_state: dict, page=None,
                        sleep_guard: Optional["SleepGuard"] = None) -> None:
    """Handle window events (close, minimize, etc.).

    On close: if a migration is active, hide to tray / minimize and keep the
    job alive; otherwise clean up and exit as before.

    Args:
        e (ft.ControlEvent): Window event.
        app_state (dict): Application state dictionary.
        page (ft.Page, optional): Page whose window is being closed. Needed to
            hide the window or to destroy it when ``prevent_close`` is set.
        sleep_guard (SleepGuard, optional): Guard to stop on a real exit.
    """
    logger = logging.getLogger(__name__)

    if e.data == "close":
        logger.info("Window close event received")
        if page is not None and is_migration_active(app_state):
            hide_to_background(page, app_state)
            return
        if sleep_guard is not None:
            sleep_guard.stop()
        quit_application(page, app_state)


# ============================================================================
# Global Exception Handler
# ============================================================================

def show_error_dialog(page: ft.Page, error_message: str) -> None:
    """Show a user-friendly error dialog.
    
    Args:
        page (ft.Page): Flet page instance.
        error_message (str): Error message to display.
    """
    logger = logging.getLogger(__name__)
    logger.error(f"Showing error dialog: {error_message}")
    
    dialog = ft.AlertDialog(
        title=ft.Text("Application Error"),
        content=ft.Text(
            value=error_message,
            size=14
        ),
        actions=[
            ft.TextButton(
                text="Close",
                on_click=lambda e: close_dialog(dialog, page)
            )
        ],
        actions_alignment=ft.MainAxisAlignment.END
    )
    
    page.overlay.append(dialog)
    dialog.open = True
    page.update()


def close_dialog(dialog: ft.AlertDialog, page: ft.Page) -> None:
    """Close an error dialog.
    
    Args:
        dialog (ft.AlertDialog): Dialog to close.
        page (ft.Page): Flet page instance.
    """
    dialog.open = False
    page.update()


def handle_exception(page: ft.Page, exception: Exception) -> None:
    """Handle unhandled exceptions gracefully.
    
    Logs the exception and shows a user-friendly error dialog.
    
    Args:
        page (ft.Page): Flet page instance.
        exception (Exception): The unhandled exception.
    """
    logger = logging.getLogger(__name__)
    logger.error("Unhandled exception occurred", exc_info=exception)
    
    error_message = (
        f"An unexpected error occurred:\n\n"
        f"{type(exception).__name__}: {str(exception)}\n\n"
        f"Please check the log file for details."
    )
    
    show_error_dialog(page, error_message)


# ============================================================================
# Main Application Entry Point
# ============================================================================

def main(page: ft.Page) -> None:
    """Main application entry point.
    
    Initializes the Flet application, configures the window, sets up
    application state, and displays the welcome screen.
    
    Args:
        page (ft.Page): Flet page instance provided by the framework.
    """
    logger = logging.getLogger(__name__)
    
    try:
        logger.info("Starting application initialization...")
        
        # Configure page properties
        page.title = app_config.WINDOW_TITLE
        page.window_width = app_config.WINDOW_WIDTH
        page.window_height = app_config.WINDOW_HEIGHT
        page.window_resizable = app_config.WINDOW_RESIZABLE
        page.theme_mode = ft.ThemeMode.SYSTEM  # Follow OS theme
        page.padding = 0
        
        logger.info(f"Window configured: {page.window_width}x{page.window_height}")
        
        # Initialize application state
        app_state = initialize_app_state()

        # Set up window event handler for cleanup / background survival.
        # prevent_close makes the OS close button raise a "close" event instead
        # of exiting, so an active migration can hide to the tray; when idle the
        # handler destroys the window itself.
        # Keep the OS awake while a job is active (CONTEXT_CONTRACT §4.3)
        sleep_guard = SleepGuard(app_state)
        sleep_guard.start()

        handler = lambda e: handle_window_event(e, app_state, page, sleep_guard)
        page.on_window_event = handler  # legacy attribute (kept for compatibility)
        try:
            page.window.prevent_close = True
            page.window.on_event = handler
        except Exception as e:
            logger.warning(f"Could not configure window close handling: {e}")

        # Show welcome screen (first screen in the flow)
        logger.info("Creating WelcomeScreen...")
        welcome_screen = WelcomeScreen(page, app_state)
        welcome_screen.show(show_back=False, progress_text="Step 1 of 5")
        
        logger.info("Application initialized successfully")
        logger.info("Ready for user interaction")
    
    except Exception as e:
        logger.error("Failed to initialize application", exc_info=e)
        handle_exception(page, e)


# ============================================================================
# Application Entry Point
# ============================================================================

if __name__ == "__main__":
    # Set up logging before anything else
    setup_logging()
    
    logger = logging.getLogger(__name__)
    
    try:
        # Ensure application directories exist
        logger.info("Ensuring application directories exist...")
        app_config.ensure_app_directories()

        # Re-register the native-messaging host for every detected browser
        # (a browser may have been installed after the app). Never fatal.
        try:
            from src.capture.registry import register_all
            register_all()
        except Exception as e:
            logger.warning(f"Native host registration skipped: {e}")
        
        # Start the Flet application
        logger.info("Starting Flet application...")
        ft.app(target=main)
        
    except KeyboardInterrupt:
        logger.info("Application interrupted by user")
        sys.exit(0)
    
    except Exception as e:
        logger.critical("Critical error during application startup", exc_info=e)
        print(f"\nCritical Error: {e}", file=sys.stderr)
        print("Check the log file for details.", file=sys.stderr)
        sys.exit(1)
