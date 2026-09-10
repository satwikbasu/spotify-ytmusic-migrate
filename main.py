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

import flet as ft
import logging
import sys
import os
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
    }
    
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


def handle_window_event(e: ft.ControlEvent, app_state: dict) -> None:
    """Handle window events (close, minimize, etc.).
    
    Args:
        e (ft.ControlEvent): Window event.
        app_state (dict): Application state dictionary.
    """
    logger = logging.getLogger(__name__)
    
    if e.data == "close":
        logger.info("Window close event received")
        cleanup_app_state(app_state)
        logger.info("Application shutdown complete")


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
        
        # Set up window event handler for cleanup
        page.on_window_event = lambda e: handle_window_event(e, app_state)
        
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
