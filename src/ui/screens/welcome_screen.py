"""Welcome Screen - Authentication interface for Spotify and YouTube Music.

This module implements the first screen of the application where users
authenticate with both Spotify and YouTube Music services.
"""

import flet as ft
import logging
from typing import Optional

from src.ui.base_screen import BaseScreen
from src.ui.components import AppButton
from src.auth.token_manager import TokenManager
from config import app_config


logger = logging.getLogger(__name__)


class WelcomeScreen(BaseScreen):
    """Welcome screen for service authentication.
    
    This screen allows users to connect their Spotify and YouTube Music accounts
    via OAuth authentication. It displays two authentication cards with connection
    status and enables navigation to playlist selection once both services are
    authenticated.
    
    Layout (Screen 1):
        - Progress indicator: "Connect Your Accounts [1/5]"
        - Spotify authentication card:
            * Spotify icon
            * Status: "Not connected" / "✅ Connected"
            * Button: "Connect" / "Disconnect"
        - YouTube Music authentication card:
            * YouTube icon
            * Status: "Not connected" / "✅ Connected"
            * Button: "Connect" / "Disconnect"
        - Continue button (disabled until both connected, pulsing when enabled)
    
    Attributes:
        spotify_authenticated (bool): Whether Spotify is connected.
        youtube_authenticated (bool): Whether YouTube Music is connected.
        token_manager (Optional[TokenManager]): Token manager instance.
        spotify_client: Authenticated Spotify client (if connected).
        youtube_client: Authenticated YouTube Music client (if connected).
    """
    
    def __init__(self, page: ft.Page, app_state: dict):
        """Initialize the welcome screen.
        
        Args:
            page (ft.Page): Flet page object.
            app_state (dict): Shared application state.
        """
        super().__init__(page, app_state)
        
        # Authentication state
        self.spotify_authenticated = False
        self.youtube_authenticated = False
        
        # Client references
        self.spotify_client = None
        self.youtube_client = None
        self.token_manager: Optional[TokenManager] = None
        
        # UI component references (will be set in build())
        self.spotify_status_text: Optional[ft.Text] = None
        self.spotify_button: Optional[AppButton] = None
        self.youtube_status_text: Optional[ft.Text] = None
        self.youtube_button: Optional[AppButton] = None
        self.continue_button: Optional[AppButton] = None
        
        logger.debug("WelcomeScreen initialized")
    
    def _initialize_token_manager(self) -> bool:
        """Initialize the token manager with credentials from config.
        
        Returns:
            bool: True if initialization successful, False otherwise.
        """
        try:
            # Check if credentials are configured
            if not app_config.SPOTIFY_CLIENT_ID or not app_config.SPOTIFY_CLIENT_SECRET:
                logger.error("Spotify credentials not configured")
                self.show_error(
                    "Spotify API credentials are not configured. "
                    "Please set SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET "
                    "environment variables.",
                    title="Configuration Error"
                )
                return False
            
            if not app_config.YOUTUBE_CLIENT_ID or not app_config.YOUTUBE_CLIENT_SECRET:
                logger.error("YouTube credentials not configured")
                self.show_error(
                    "YouTube API credentials are not configured. "
                    "Please set YOUTUBE_CLIENT_ID and YOUTUBE_CLIENT_SECRET "
                    "environment variables.",
                    title="Configuration Error"
                )
                return False
            
            # Initialize token manager
            self.token_manager = TokenManager(
                spotify_client_id=app_config.SPOTIFY_CLIENT_ID,
                spotify_client_secret=app_config.SPOTIFY_CLIENT_SECRET,
                youtube_client_id=app_config.YOUTUBE_CLIENT_ID,
                youtube_client_secret=app_config.YOUTUBE_CLIENT_SECRET
            )
            
            logger.info("TokenManager initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize TokenManager: {e}")
            self.show_error(
                f"Failed to initialize authentication system: {str(e)}",
                title="Initialization Error"
            )
            return False
    
    def build(self) -> ft.Control:
        """Build the welcome screen UI.
        
        Returns:
            ft.Control: The welcome screen content.
        """
        # Title
        title = ft.Text(
            "Connect Your Accounts",
            size=app_config.HEADING_SIZE_LARGE,
            weight=ft.FontWeight.BOLD,
            color=app_config.TEXT_COLOR_DARK,
            text_align=ft.TextAlign.CENTER
        )
        
        # Subtitle
        subtitle = ft.Text(
            "Authenticate with both services to begin migrating playlists",
            size=app_config.BODY_SIZE,
            color=app_config.TEXT_COLOR_DARK,
            opacity=0.7,
            text_align=ft.TextAlign.CENTER
        )
        
        # Spotify authentication card
        spotify_card = self._build_auth_card(
            service_name="Spotify",
            icon=ft.Icons.MUSIC_NOTE,
            icon_color=app_config.SPOTIFY_GREEN,
            is_spotify=True
        )
        
        # YouTube Music authentication card
        youtube_card = self._build_auth_card(
            service_name="YouTube Music",
            icon=ft.Icons.PLAY_CIRCLE_OUTLINE,
            icon_color=app_config.YOUTUBE_RED,
            is_spotify=False
        )
        
        # Continue button
        self.continue_button = AppButton(
            text="Continue to Playlist Selection",
            primary=True,
            gradient=True,
            on_click=self.on_continue_click,
            disabled=True,
            expand=False
        )
        
        # Main content layout
        content = ft.Container(
            content=ft.Column(
                controls=[
                    title,
                    ft.Container(height=8),
                    subtitle,
                    ft.Container(height=40),
                    spotify_card,
                    ft.Container(height=20),
                    youtube_card,
                    ft.Container(height=40),
                    ft.Row(
                        controls=[self.continue_button],
                        alignment=ft.MainAxisAlignment.CENTER
                    )
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=0
            ),
            padding=40,
            alignment=ft.alignment.center,
            expand=True
        )
        
        return content
    
    def _build_auth_card(
        self,
        service_name: str,
        icon: str,
        icon_color: str,
        is_spotify: bool
    ) -> ft.Card:
        """Build an authentication card for a service.
        
        Args:
            service_name (str): Name of the service ("Spotify" or "YouTube Music").
            icon (str): Flet icon to display.
            icon_color (str): Color for the icon.
            is_spotify (bool): Whether this is the Spotify card.
        
        Returns:
            ft.Card: Authentication card control.
        """
        # Status text
        status_text = ft.Text(
            value="Not connected",
            size=app_config.BODY_SIZE,
            color=app_config.TEXT_COLOR_DARK,
            opacity=0.6,
            weight=ft.FontWeight.W_400
        )
        
        # Connect/Disconnect button
        button = AppButton(
            text="Connect",
            primary=True,
            on_click=self.on_spotify_connect_click if is_spotify else self.on_youtube_connect_click,
            expand=False
        )
        
        # Store references
        if is_spotify:
            self.spotify_status_text = status_text
            self.spotify_button = button
        else:
            self.youtube_status_text = status_text
            self.youtube_button = button
        
        # Card content
        card_content = ft.Container(
            content=ft.Row(
                controls=[
                    # Icon
                    ft.Container(
                        content=ft.Icon(
                            name=icon,
                            size=48,
                            color=icon_color
                        ),
                        width=80,
                        height=80,
                        border_radius=8,
                        bgcolor=f"{icon_color}15",  # 15 = ~8% opacity in hex
                        alignment=ft.alignment.center
                    ),
                    
                    # Spacer
                    ft.Container(width=20),
                    
                    # Service info
                    ft.Column(
                        controls=[
                            ft.Text(
                                value=service_name,
                                size=app_config.HEADING_SIZE_SMALL,
                                weight=ft.FontWeight.BOLD,
                                color=app_config.TEXT_COLOR_DARK
                            ),
                            ft.Container(height=4),
                            status_text
                        ],
                        spacing=0,
                        expand=True
                    ),
                    
                    # Spacer
                    ft.Container(width=20),
                    
                    # Button
                    button
                ],
                alignment=ft.MainAxisAlignment.START,
                vertical_alignment=ft.CrossAxisAlignment.CENTER
            ),
            padding=24,
            border_radius=12
        )
        
        return ft.Card(
            content=card_content,
            elevation=2,
            width=600
        )
    
    def _update_card_state(self, is_spotify: bool, authenticated: bool) -> None:
        """Update the UI state of an authentication card.
        
        Args:
            is_spotify (bool): Whether to update Spotify (True) or YouTube (False).
            authenticated (bool): Whether the service is authenticated.
        """
        if is_spotify:
            if authenticated:
                self.spotify_status_text.value = "✅ Connected"
                self.spotify_status_text.color = app_config.SUCCESS_COLOR
                self.spotify_status_text.opacity = 1.0
                self.spotify_button.text = "Disconnect"
                self.spotify_button.primary = False
            else:
                self.spotify_status_text.value = "Not connected"
                self.spotify_status_text.color = app_config.TEXT_COLOR_DARK
                self.spotify_status_text.opacity = 0.6
                self.spotify_button.text = "Connect"
                self.spotify_button.primary = True
        else:
            if authenticated:
                self.youtube_status_text.value = "✅ Connected"
                self.youtube_status_text.color = app_config.SUCCESS_COLOR
                self.youtube_status_text.opacity = 1.0
                self.youtube_button.text = "Disconnect"
                self.youtube_button.primary = False
            else:
                self.youtube_status_text.value = "Not connected"
                self.youtube_status_text.color = app_config.TEXT_COLOR_DARK
                self.youtube_status_text.opacity = 0.6
                self.youtube_button.text = "Connect"
                self.youtube_button.primary = True
        
        # Update continue button state
        self._update_continue_button()
        
        # Update page
        self.page.update()
    
    def _update_continue_button(self) -> None:
        """Update the continue button state based on authentication status."""
        both_authenticated = self.spotify_authenticated and self.youtube_authenticated
        
        self.continue_button.disabled = not both_authenticated
        
        # Add pulsing animation when enabled
        if both_authenticated:
            # Enable with animation (opacity pulse)
            self.continue_button.animate_opacity = 1000  # 1 second pulse
        else:
            # Disable animation
            self.continue_button.animate_opacity = None
    
    def on_spotify_connect_click(self, e) -> None:
        """Handle Spotify connect/disconnect button click.
        
        Args:
            e: Flet event object.
        """
        if self.spotify_authenticated:
            # Disconnect
            self._handle_disconnect(is_spotify=True)
        else:
            # Connect
            self._handle_connect(is_spotify=True)
    
    def on_youtube_connect_click(self, e) -> None:
        """Handle YouTube Music connect/disconnect button click.
        
        Args:
            e: Flet event object.
        """
        if self.youtube_authenticated:
            # Disconnect
            self._handle_disconnect(is_spotify=False)
        else:
            # Connect
            self._handle_connect(is_spotify=False)
    
    def _handle_connect(self, is_spotify: bool) -> None:
        """Handle service connection.
        
        Args:
            is_spotify (bool): Whether connecting Spotify (True) or YouTube (False).
        """
        service_name = "Spotify" if is_spotify else "YouTube Music"
        logger.info(f"Attempting to connect {service_name}")
        
        # Show loading
        self.show_loading(True, f"Connecting to {service_name}...")
        
        try:
            # Initialize token manager if needed
            if self.token_manager is None:
                if not self._initialize_token_manager():
                    self.show_loading(False)
                    return
            
            # Authenticate
            if is_spotify:
                self.spotify_client = self.token_manager.authenticate_spotify()
                self.spotify_authenticated = True
                logger.info("Spotify authentication successful")
            else:
                self.youtube_client = self.token_manager.authenticate_youtube()
                self.youtube_authenticated = True
                logger.info("YouTube Music authentication successful")
            
            # Update UI
            self._update_card_state(is_spotify, True)
            
            # Show success message
            self.show_success(
                f"Successfully connected to {service_name}!",
                title="Connected"
            )
            
        except ValueError as e:
            # Configuration error
            logger.error(f"{service_name} configuration error: {e}")
            self.show_error(
                f"Configuration error: {str(e)}. "
                f"Please check your {service_name} API credentials.",
                title="Configuration Error"
            )
            
        except RuntimeError as e:
            # Authentication error
            logger.error(f"{service_name} authentication failed: {e}")
            self.show_error(
                f"Failed to authenticate with {service_name}. "
                f"Please try again or check your credentials.\n\n"
                f"Error: {str(e)}",
                title="Authentication Failed"
            )
            
        except Exception as e:
            # Unexpected error
            logger.error(f"Unexpected error during {service_name} authentication: {e}")
            self.show_error(
                f"An unexpected error occurred while connecting to {service_name}.\n\n"
                f"Error: {str(e)}",
                title="Connection Error"
            )
            
        finally:
            # Hide loading
            self.show_loading(False)
    
    def _handle_disconnect(self, is_spotify: bool) -> None:
        """Handle service disconnection.
        
        Args:
            is_spotify (bool): Whether disconnecting Spotify (True) or YouTube (False).
        """
        service_name = "Spotify" if is_spotify else "YouTube Music"
        
        def do_disconnect():
            logger.info(f"Disconnecting {service_name}")
            
            if is_spotify:
                self.spotify_client = None
                self.spotify_authenticated = False
                # TODO: Clear cached tokens if needed
            else:
                self.youtube_client = None
                self.youtube_authenticated = False
                # TODO: Clear cached tokens if needed
            
            # Update UI
            self._update_card_state(is_spotify, False)
            
            logger.info(f"{service_name} disconnected")
        
        # Confirm disconnection
        self.show_confirmation(
            f"Are you sure you want to disconnect from {service_name}?",
            title=f"Disconnect {service_name}",
            on_confirm=do_disconnect,
            confirm_text="Disconnect",
            cancel_text="Cancel"
        )
    
    def on_continue_click(self, e) -> None:
        """Handle continue button click.
        
        Navigates to playlist selection screen if both services are authenticated.
        
        Args:
            e: Flet event object.
        """
        if not (self.spotify_authenticated and self.youtube_authenticated):
            self.show_error(
                "Please connect both Spotify and YouTube Music to continue.",
                title="Authentication Required"
            )
            return
        
        logger.info("Both services authenticated, proceeding to playlist selection")
        
        # Store clients in app state
        self.app_state['spotify_client'] = self.spotify_client
        self.app_state['youtube_client'] = self.youtube_client
        self.app_state['token_manager'] = self.token_manager
        
        # TODO: Navigate to PlaylistSelectionScreen once implemented
        # from src.ui.screens.playlist_selection_screen import PlaylistSelectionScreen
        # self.navigate_to(PlaylistSelectionScreen, show_back=True, progress_text="Step 2 of 5")
        
        # For now, show success
        self.show_success(
            "Authentication complete! Playlist selection screen coming soon.",
            title="Ready to Migrate"
        )
