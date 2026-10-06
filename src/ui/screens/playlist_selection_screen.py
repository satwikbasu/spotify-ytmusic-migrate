"""Playlist Selection Screen - Browse and select playlists for migration.

This module implements the playlist selection screen where users can view
all their Spotify playlists and choose which ones to migrate to YouTube Music.
"""

import flet as ft
import logging
from typing import List, Dict, Any, Optional, Set

from src.ui.base_screen import BaseScreen
from src.ui.components import AppButton, PlaylistCard, LoadingIndicator
from src.fetchers.spotify_fetcher import SpotifyFetcher
from src.utils.rate_limiter import RateLimiter
from src.utils.cache_manager import CacheManager
from src.utils import user_config
from config import app_config


logger = logging.getLogger(__name__)


class PlaylistSelectionScreen(BaseScreen):
    """Playlist selection screen for choosing playlists to migrate.
    
    This screen displays all user playlists from Spotify and allows selection
    of which playlists to migrate to YouTube Music. Features include:
    - Fetching and displaying all public playlists
    - Select/Deselect all functionality
    - Search filtering
    - Real-time selection count
    - Validation before migration
    
    Layout (Screen 3):
        - Progress: "Select Playlists [2/5]"
        - Header: "Found X public playlists"
        - Action buttons: [Select All] [Deselect All]
        - Search bar
        - Scrollable playlist list with PlaylistCard components
        - Footer:
            * Selection summary: "Selected: X playlists (Total: Y songs)"
            * Buttons: [Back] [Start Migration]
    
    Attributes:
        playlists (List[Dict]): All fetched playlists.
        filtered_playlists (List[Dict]): Playlists after search filtering.
        selected_playlists (Set[str]): Set of selected playlist IDs.
        fetcher (Optional[SpotifyFetcher]): Spotify data fetcher.
        search_query (str): Current search filter text.
    """
    
    def __init__(self, page: ft.Page, app_state: dict):
        """Initialize the playlist selection screen.
        
        Args:
            page (ft.Page): Flet page object.
            app_state (dict): Shared application state.
        """
        super().__init__(page, app_state)
        
        # Data state
        self.playlists: List[Dict[str, Any]] = []
        self.filtered_playlists: List[Dict[str, Any]] = []
        self.selected_playlists: Set[str] = set()
        self.fetcher: Optional[SpotifyFetcher] = None
        self.search_query: str = ""
        self.include_liked_songs: bool = True
        self.liked_switch: Optional[ft.Switch] = None
        
        # UI component references
        self.header_text: Optional[ft.Text] = None
        self.search_field: Optional[ft.TextField] = None
        self.playlist_list: Optional[ft.ListView] = None
        self.selection_summary: Optional[ft.Text] = None
        self.start_button: Optional[AppButton] = None
        
        logger.debug("PlaylistSelectionScreen initialized")
    
    def build(self) -> ft.Control:
        """Build the playlist selection screen UI.
        
        Returns:
            ft.Control: The playlist selection screen content.
        """
        # Header
        title = ft.Text(
            "Select Playlists",
            size=app_config.HEADING_SIZE_LARGE,
            weight=ft.FontWeight.BOLD,
            color=app_config.TEXT_COLOR_LIGHT
        )
        
        # Playlist count header
        self.header_text = ft.Text(
            "Loading playlists...",
            size=app_config.BODY_SIZE,
            color=app_config.TEXT_COLOR_LIGHT,
            opacity=0.7
        )
        
        # "Include Liked Songs" switch (remembered between runs)
        self.include_liked_songs = user_config.get_include_liked_songs()
        self.liked_switch = ft.Switch(
            label="Include Liked Songs",
            value=self.include_liked_songs,
            active_color=app_config.PRIMARY_COLOR,
            on_change=self.on_liked_songs_toggle
        )
        liked_hint = ft.Text(
            "Your Liked Songs become a playlist called \"Liked Songs\" on YouTube Music.",
            size=app_config.BODY_SIZE - 2,
            color=app_config.TEXT_COLOR_LIGHT,
            opacity=0.6
        )
        
        # Action buttons row
        action_buttons = ft.Row(
            controls=[
                AppButton(
                    text="Select All",
                    on_click=self.on_select_all_click,
                    primary=False,
                    expand=False
                ),
                ft.Container(width=12),
                AppButton(
                    text="Deselect All",
                    on_click=self.on_deselect_all_click,
                    primary=False,
                    expand=False
                )
            ],
            alignment=ft.MainAxisAlignment.START
        )
        
        # Search bar
        self.search_field = ft.TextField(
            hint_text="Search playlists...",
            prefix_icon=ft.Icons.SEARCH,
            border_radius=8,
            bgcolor="#2A2A2A",
            border_color=app_config.PRIMARY_COLOR,
            focused_border_color=app_config.PRIMARY_COLOR,
            cursor_color=app_config.PRIMARY_COLOR,
            color=ft.Colors.WHITE,
            text_size=app_config.BODY_SIZE,
            on_change=self.on_search_change,
            expand=True
        )
        
        search_row = ft.Row(
            controls=[self.search_field],
            alignment=ft.MainAxisAlignment.START
        )
        
        # Playlist list (scrollable) - must use expand=1 for proper height calculation
        self.playlist_list = ft.ListView(
            spacing=12,
            padding=ft.padding.only(top=0, bottom=20, left=0, right=0),
            expand=1,
            auto_scroll=False
        )
        
        # Selection summary
        self.selection_summary = ft.Text(
            "Selected: 0 playlists (Total: 0 tracks)",
            size=app_config.BODY_SIZE,
            weight=ft.FontWeight.W_500,
            color=app_config.TEXT_COLOR_LIGHT
        )
        
        # Footer buttons
        back_button = AppButton(
            text="Back",
            on_click=self._handle_back,
            primary=False,
            expand=False
        )
        
        self.start_button = AppButton(
            text="Start Migration",
            on_click=self.on_start_migration_click,
            primary=True,
            gradient=True,
            disabled=True,
            expand=False
        )
        
        footer = ft.Container(
            content=ft.Column(
                controls=[
                    ft.Divider(height=1, color=app_config.TEXT_COLOR_DARK, opacity=0.2),
                    ft.Container(height=12),
                    self.selection_summary,
                    ft.Container(height=16),
                    ft.Row(
                        controls=[
                            back_button,
                            ft.Container(expand=True),
                            self.start_button
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN
                    )
                ],
                spacing=0
            ),
            padding=ft.padding.only(left=40, right=40, bottom=20, top=20)
        )
        
        # Main content layout - proper structure for scrolling
        # Key: Column with expand, Container with expand for ListView
        content = ft.Column(
            controls=[
                # Header section
                ft.Container(
                    content=ft.Column(
                        controls=[
                            title,
                            ft.Container(height=8),
                            self.header_text,
                            ft.Container(height=24),
                            self.liked_switch,
                            liked_hint,
                            ft.Container(height=12),
                            action_buttons,
                            ft.Container(height=16),
                            search_row
                        ],
                        spacing=0
                    ),
                    padding=ft.padding.only(left=40, right=40, top=20, bottom=16)
                ),
                # Scrollable area - Container with expand containing ListView
                ft.Container(
                    content=self.playlist_list,
                    expand=True,
                    padding=ft.padding.symmetric(horizontal=40)
                ),
                # Footer
                footer
            ],
            spacing=0,
            expand=True
        )
        
        # Load playlists after building UI
        self.page.run_task(self.load_playlists)
        
        return content
    
    async def load_playlists(self) -> None:
        """Load playlists from Spotify.
        
        Fetches all user playlists using SpotifyFetcher and updates the UI.
        Shows loading indicator during fetch and error dialog on failure.
        """
        logger.info("Loading playlists from Spotify")
        
        # Wait a moment for UI to fully initialize
        import asyncio
        await asyncio.sleep(0.1)
        
        # Show loading
        self.show_loading(True, "Fetching playlists from Spotify...")
        
        try:
            # Get Spotify client from app state
            spotify_client = self.app_state.get('spotify_client')
            if not spotify_client:
                raise ValueError("Spotify client not found in app state")
            
            # Initialize fetcher if not already done
            if self.fetcher is None:
                # Get or create cache manager
                cache_manager = self.app_state.get('cache_manager')
                if not cache_manager:
                    cache_manager = CacheManager()
                    self.app_state['cache_manager'] = cache_manager
                
                # Get or create rate limiter
                rate_limiter = self.app_state.get('rate_limiter')
                if not rate_limiter:
                    rate_limiter = RateLimiter(
                        per_minute_limit=60,
                        daily_limit=10000
                    )
                    self.app_state['rate_limiter'] = rate_limiter
                
                # Create fetcher
                self.fetcher = SpotifyFetcher(
                    spotify_client=spotify_client,
                    rate_limiter=rate_limiter,
                    cache_manager=cache_manager
                )
                logger.info("SpotifyFetcher initialized")
            
            # Fetch playlists
            self.playlists = self.fetcher.get_user_playlists(
                use_cache=True,
                include_liked_songs=self.include_liked_songs
            )
            self.filtered_playlists = self.playlists.copy()
            
            logger.info(f"Fetched {len(self.playlists)} playlists")
            
            # Update UI
            self._update_playlist_list()
            self._update_header()
            self._update_footer()
            
        except ValueError as e:
            logger.error(f"Configuration error: {e}")
            self.show_error(
                f"Configuration error: {str(e)}",
                title="Error Loading Playlists"
            )
            
        except Exception as e:
            logger.error(f"Failed to load playlists: {e}")
            self.show_error(
                f"Failed to load playlists from Spotify.\n\n"
                f"Error: {str(e)}\n\n"
                f"Please try again or check your connection.",
                title="Error Loading Playlists"
            )
            
        finally:
            # Hide loading
            self.show_loading(False)
    
    def _update_playlist_list(self) -> None:
        """Update the playlist list view with current filtered playlists."""
        # Clear existing list
        self.playlist_list.controls.clear()
        
        if not self.filtered_playlists:
            # Show empty state
            empty_message = ft.Container(
                content=ft.Column(
                    controls=[
                        ft.Icon(
                            name=ft.Icons.MUSIC_NOTE_OUTLINED,
                            size=64,
                            color=app_config.TEXT_COLOR_DARK,
                            opacity=0.3
                        ),
                        ft.Container(height=16),
                        ft.Text(
                            "No playlists found" if not self.search_query else "No playlists match your search",
                            size=app_config.BODY_SIZE,
                            color=app_config.TEXT_COLOR_LIGHT,
                            opacity=0.6,
                            text_align=ft.TextAlign.CENTER
                        )
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    alignment=ft.MainAxisAlignment.CENTER
                ),
                alignment=ft.alignment.center,
                expand=True
            )
            self.playlist_list.controls.append(empty_message)
        else:
            # Add playlist cards
            for i, playlist in enumerate(self.filtered_playlists):
                playlist_id = playlist.get('id', '')
                is_selected = playlist_id in self.selected_playlists
                
                # Debug: log first playlist data
                if i == 0:
                    logger.info(f"First playlist data: {playlist}")
                
                card = PlaylistCard(
                    playlist=playlist,
                    selected=is_selected,
                    on_click=lambda e, pid=playlist_id: self.on_playlist_toggle(pid)
                )
                
                self.playlist_list.controls.append(card)
        
        # Force update the page
        try:
            self.page.update()
        except AssertionError:
            # UI not fully initialized yet, skip update
            logger.debug("UI not ready for update, skipping")
    
    def _update_header(self) -> None:
        """Update the header text with playlist count."""
        total_count = len(self.playlists)
        filtered_count = len(self.filtered_playlists)
        
        if self.search_query:
            self.header_text.value = f"Showing {filtered_count} of {total_count} playlists"
        else:
            self.header_text.value = f"Found {total_count} public playlists"
        
        self.page.update()
    
    def _update_footer(self) -> None:
        """Update the footer with selection count and total tracks."""
        selected_count = len(self.selected_playlists)
        
        # Calculate total tracks in selected playlists
        total_tracks = 0
        for playlist in self.playlists:
            if playlist.get('id') in self.selected_playlists:
                total_tracks += playlist.get('tracks_count', 0)
        
        # Update summary text
        self.selection_summary.value = (
            f"Selected: {selected_count} playlists "
            f"(Total: {total_tracks:,} tracks)"
        )
        
        # Update start button state
        self.start_button.disabled = selected_count == 0
        
        # Update page if controls are attached
        if hasattr(self.selection_summary, 'page') and self.selection_summary.page:
            self.selection_summary.update()
        if hasattr(self.start_button, 'page') and self.start_button.page:
            self.start_button.update()
    
    def on_liked_songs_toggle(self, e) -> None:
        """Handle the "Include Liked Songs" switch.

        Saves the preference, drops Liked Songs from the selection when turned
        off, and reloads the list so "Select All" / Everything follow the switch.
        """
        self.include_liked_songs = bool(e.control.value)
        user_config.set_include_liked_songs(self.include_liked_songs)
        logger.info(f"Include Liked Songs: {self.include_liked_songs}")
        
        if not self.include_liked_songs:
            self.selected_playlists.discard(SpotifyFetcher.LIKED_SONGS_PLAYLIST_ID)
        
        self.page.run_task(self.load_playlists)
    
    def on_playlist_toggle(self, playlist_id: str) -> None:
        """Toggle playlist selection.
        
        Args:
            playlist_id (str): ID of the playlist to toggle.
        """
        if playlist_id in self.selected_playlists:
            self.selected_playlists.remove(playlist_id)
            logger.debug(f"Deselected playlist: {playlist_id}")
        else:
            self.selected_playlists.add(playlist_id)
            logger.debug(f"Selected playlist: {playlist_id}")
        
        # Update footer
        self._update_footer()
    
    def on_select_all_click(self, e) -> None:
        """Select all visible playlists.
        
        Args:
            e: Flet event object.
        """
        logger.info("Selecting all playlists")
        
        # Add all filtered playlist IDs to selection
        for playlist in self.filtered_playlists:
            playlist_id = playlist.get('id')
            if playlist_id:
                self.selected_playlists.add(playlist_id)
        
        # Update UI
        self._update_playlist_list()
        self._update_footer()
    
    def on_deselect_all_click(self, e) -> None:
        """Deselect all playlists.
        
        Args:
            e: Flet event object.
        """
        logger.info("Deselecting all playlists")
        
        # Clear selection
        self.selected_playlists.clear()
        
        # Update UI
        self._update_playlist_list()
        self._update_footer()
    
    def on_search_change(self, e) -> None:
        """Handle search query change.
        
        Filters playlists by name (case-insensitive).
        
        Args:
            e: Flet event object.
        """
        self.search_query = e.control.value.lower().strip()
        logger.debug(f"Search query: '{self.search_query}'")
        
        # Filter playlists
        if not self.search_query:
            # Show all playlists
            self.filtered_playlists = self.playlists.copy()
        else:
            # Filter by name - handle None values
            self.filtered_playlists = [
                playlist for playlist in self.playlists
                if playlist.get('name') and self.search_query in playlist.get('name').lower()
            ]
        
        # Update UI
        self._update_playlist_list()
        self._update_header()
    
    def on_start_migration_click(self, e) -> None:
        """Handle start migration button click.
        
        Validates selection and navigates to migration progress screen.
        
        Args:
            e: Flet event object.
        """
        # Validate selection
        if not self.selected_playlists:
            self.show_error(
                "Please select at least one playlist to migrate.",
                title="No Playlists Selected"
            )
            return
        
        selected_count = len(self.selected_playlists)
        logger.info(f"Starting migration for {selected_count} playlists")
        
        # Warn if many playlists selected
        if selected_count > 50:
            def proceed_with_migration():
                self._start_migration()
            
            self.show_confirmation(
                f"You have selected {selected_count} playlists. "
                f"This migration may take several hours to complete.\n\n"
                f"Are you sure you want to continue?",
                title="Large Migration Warning",
                on_confirm=proceed_with_migration,
                confirm_text="Continue",
                cancel_text="Go Back"
            )
        else:
            # Proceed directly
            self._start_migration()
    
    def _start_migration(self) -> None:
        """Start the migration process.
        
        Prepares selected playlists data and navigates to migration screen.
        """
        # Get selected playlist objects
        selected_playlist_objects = [
            playlist for playlist in self.playlists
            if playlist.get('id') in self.selected_playlists
        ]
        
        # Store in app state
        self.app_state['selected_playlists'] = selected_playlist_objects
        
        logger.info(f"Stored {len(selected_playlist_objects)} playlists in app state")
        
        # Navigate to MigrationProgressScreen
        from src.ui.screens.migration_progress_screen import MigrationProgressScreen
        self.navigate_to(MigrationProgressScreen, show_back=False, progress_text="Step 3 of 5")
    
    def _handle_back(self, e) -> None:
        """Handle back button click.
        
        Returns to welcome screen.
        
        Args:
            e: Flet event object.
        """
        logger.info("Navigating back to welcome screen")
        
        # Clear selected playlists
        self.selected_playlists.clear()
        
        # Navigate back to welcome screen
        from src.ui.screens.welcome_screen import WelcomeScreen
        self.navigate_to(WelcomeScreen, progress_text="Step 1 of 5")
