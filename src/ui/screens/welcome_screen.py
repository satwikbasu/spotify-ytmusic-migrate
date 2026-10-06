"""Welcome Screen - Authentication interface for Spotify and YouTube Music.

This module implements the first screen of the application where users
authenticate with both Spotify and YouTube Music services.
"""

import flet as ft
import logging
import webbrowser
from typing import Optional, Tuple

from src.ui.base_screen import BaseScreen
from src.ui.components import AppButton, AppTextField
from src.auth.token_manager import TokenManager
from src.utils import user_config
from config import app_config


logger = logging.getLogger(__name__)

DASHBOARD_URL = "https://developer.spotify.com/dashboard"
REDIRECT_URI = "http://127.0.0.1/callback"

PREMIUM_REQUIRED_MESSAGE = (
    "Spotify Premium required right now \u2014 Free support is coming in a future update."
)

# Plain-language Spotify connect problems (docs/UX_FLOW.md section 7, E1-E6, E18).
# kind -> (message, [remedy button ids])
SPOTIFY_ERRORS = {
    "premium": (
        "This Spotify account is on the Free plan. " + PREMIUM_REQUIRED_MESSAGE,
        ["different_account"],
    ),
    "redirect": (
        "Spotify didn't accept the redirect address. In your app's Settings on the "
        "Spotify dashboard, the Redirect URI must be exactly " + REDIRECT_URI,
        ["copy_address", "open_dashboard", "try_again"],
    ),
    "auth_rejected": (
        "Spotify didn't accept the login. Check that the Client ID is right and that "
        "the Redirect URI in your app's Settings is exactly " + REDIRECT_URI,
        ["fix_client_id", "copy_address", "open_dashboard", "try_again"],
    ),
    "invalid_client": (
        "Spotify doesn't recognise that Client ID. Check you copied the whole code "
        "from your app's Settings page.",
        ["fix_client_id"],
    ),
    "not_allowed": (
        "Spotify says this account isn't allowed to use the app yet. Open your app's "
        "User Management page and add the email of the Spotify account you're logging into.",
        ["open_dashboard", "try_again"],
    ),
    "cancelled": (
        "Spotify login was cancelled. Click Connect to try again.",
        ["try_again"],
    ),
    "network": (
        "Can't reach the internet right now. Nothing is lost \u2014 check your "
        "connection and try again.",
        ["try_again"],
    ),
    "generic": (
        "Something went wrong while connecting to Spotify. Please try again.",
        ["try_again"],
    ),
}

CLIENT_ID_INVALID_HELP = (
    "That doesn't look like a Client ID \u2014 it should be exactly 32 letters and "
    "numbers. Make sure you copied Client ID, not the app name or the secret."
)


def classify_spotify_error(exc: BaseException) -> str:
    """Map a connect/test failure to a key of ``SPOTIFY_ERRORS`` (no jargon leaks out)."""
    parts = []
    cur: Optional[BaseException] = exc
    while cur is not None and len(parts) < 4:
        parts.append(str(cur).lower())
        cur = cur.__cause__
    text = " ".join(parts)

    if "invalid redirect" in text:
        return "redirect"
    if "invalid_client" in text or "invalid client" in text:
        return "invalid_client"
    if "not registered" in text or "user management" in text:
        return "not_allowed"
    if any(w in text for w in ("denied", "cancel", "timed out", "timeout")):
        return "cancelled"
    if any(w in text for w in ("connection", "network", "name resolution", "max retries", "unreachable")):
        return "network"
    if "spotify authentication failed" in text:
        return "auth_rejected"
    if getattr(exc, "http_status", None) == 403:
        return "not_allowed"
    return "generic"


def is_premium(product: Optional[str]) -> bool:
    """Spotify reports ``premium`` (or ``premium_*``) for paying accounts."""
    return isinstance(product, str) and product.lower().startswith("premium")


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
        self._token_manager_client_id: Optional[str] = None
        self.spotify_name: Optional[str] = None
        self.spotify_error_kind: Optional[str] = None

        # Wizard state (Option A: A0 why, A1 create app, A2 paste ID, A3 log in)
        self.wizard_step: Optional[str] = None
        self.wizard_dialog: Optional[ft.AlertDialog] = None
        self.client_id_field: Optional[AppTextField] = None
        self.client_id_valid: bool = False
        self.client_id_helper: Optional[ft.Text] = None
        self.wizard_connect_button: Optional[ft.Control] = None
        self.spotify_error_text: Optional[ft.Text] = None
        self.spotify_error_row: Optional[ft.Row] = None
        
        # UI component references (will be set in build())
        self.spotify_status_text: Optional[ft.Text] = None
        self.spotify_button: Optional[AppButton] = None
        self.youtube_status_text: Optional[ft.Text] = None
        self.youtube_button: Optional[AppButton] = None
        self.continue_button: Optional[AppButton] = None
        
        logger.debug("WelcomeScreen initialized")
    
    def _initialize_token_manager(self) -> bool:
        """Create the TokenManager from the saved Spotify Client ID.

        Only the Spotify Client ID is needed. No Google/YouTube credentials are
        required (YouTube Music uses captured browser sign-in, not OAuth).

        Returns:
            bool: True if a TokenManager is ready. False when no Client ID is
            saved yet (the caller opens the setup wizard) or setup failed.
        """
        client_id = user_config.get_spotify_client_id()
        if not client_id:
            return False

        if self.token_manager is not None and self._token_manager_client_id == client_id:
            return True

        try:
            self.token_manager = TokenManager(spotify_client_id=client_id)
            self._token_manager_client_id = client_id
            logger.info("TokenManager initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize TokenManager: {e}")
            self.show_error(
                "We couldn't prepare the sign-in on this computer. "
                "Please restart the app and try again.",
                title="Something went wrong"
            )
            return False

    def build(self) -> ft.Control:
        """Build the welcome screen UI.
        
        Returns:
            ft.Control: The welcome screen content.
        """
        # Title
        title = ft.Text(
            "Connect your two accounts",
            size=app_config.HEADING_SIZE_LARGE,
            weight=ft.FontWeight.BOLD,
            color=app_config.TEXT_COLOR_DARK,
            text_align=ft.TextAlign.CENTER
        )
        
        # Subtitle
        subtitle = ft.Text(
            "Spotify is where your music is now. YouTube Music is where it's going. Nothing leaves this computer.",
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
                        ] + (self._build_spotify_error_controls() if is_spotify else []),
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
    
    def _safe_update(self) -> None:
        """page.update() that tolerates a page that is not mounted yet."""
        try:
            self.page.update()
        except AssertionError:
            logger.debug("UI not ready for update, skipping")

    def _update_card_state(
        self, is_spotify: bool, authenticated: bool, name: Optional[str] = None
    ) -> None:
        """Update the UI state of an authentication card.

        Args:
            is_spotify (bool): Whether to update Spotify (True) or YouTube (False).
            authenticated (bool): Whether the service is authenticated.
            name (Optional[str]): Account name to show ("connected as <name>").
        """
        status = self.spotify_status_text if is_spotify else self.youtube_status_text
        button = self.spotify_button if is_spotify else self.youtube_button

        if authenticated:
            status.value = f"\u2705 Connected as {name}" if name else "\u2705 Connected"
            status.color = app_config.SUCCESS_COLOR
            status.opacity = 1.0
            button.text = "Disconnect"
            button.primary = False
        else:
            status.value = "Not connected"
            status.color = app_config.TEXT_COLOR_DARK
            status.opacity = 0.6
            button.text = "Connect"
            button.primary = True

        if is_spotify and authenticated:
            self._set_spotify_error(None)

        # Update continue button state
        self._update_continue_button()
        self._safe_update()

    # ------------------------------------------------------------------
    # Spotify: error panel
    # ------------------------------------------------------------------

    def _build_spotify_error_controls(self) -> list:
        self.spotify_error_text = ft.Text(
            value="", size=app_config.CAPTION_SIZE, color=app_config.ERROR_COLOR,
            visible=False,
        )
        self.spotify_error_row = ft.Row(controls=[], wrap=True, spacing=8, visible=False)
        return [self.spotify_error_text, self.spotify_error_row]

    def _remedy_button(self, key: str) -> ft.Control:
        labels = {
            "try_again": ("Try again", self._on_try_again),
            "different_account": ("Try a different account", self._on_try_again),
            "fix_client_id": ("Fix Client ID", self._on_fix_client_id),
            "copy_address": ("Copy address again", self._on_copy_redirect),
            "open_dashboard": ("Open my app settings", self._on_open_dashboard),
        }
        text, handler = labels[key]
        return ft.TextButton(text=text, on_click=handler)

    def _set_spotify_error(self, kind: Optional[str]) -> None:
        """Show (or clear, with None) a plain-language Spotify problem on the card."""
        self.spotify_error_kind = kind
        if self.spotify_error_text is None:
            return
        if kind is None:
            self.spotify_error_text.value = ""
            self.spotify_error_text.visible = False
            self.spotify_error_row.controls = []
            self.spotify_error_row.visible = False
        else:
            message, remedies = SPOTIFY_ERRORS[kind]
            self.spotify_error_text.value = message
            self.spotify_error_text.visible = True
            self.spotify_error_row.controls = [self._remedy_button(k) for k in remedies]
            self.spotify_error_row.visible = True
        self._safe_update()

    def _on_try_again(self, e=None) -> None:
        self._set_spotify_error(None)
        self._start_spotify_connect()

    def _on_fix_client_id(self, e=None) -> None:
        self._set_spotify_error(None)
        self._open_wizard("A2")

    def _on_copy_redirect(self, e=None) -> None:
        try:
            self.page.set_clipboard(REDIRECT_URI)
        except Exception as ex:  # clipboard is a convenience only
            logger.debug(f"Clipboard unavailable: {ex}")

    def _on_open_dashboard(self, e=None) -> None:
        self._open_url(DASHBOARD_URL)

    @staticmethod
    def _open_url(url: str) -> None:
        try:
            webbrowser.open(url)
        except Exception as ex:
            logger.debug(f"Could not open browser: {ex}")

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
            self._handle_disconnect(is_spotify=True)
        else:
            self._start_spotify_connect()

    def _start_spotify_connect(self) -> None:
        """One click if a Client ID is saved; otherwise run the setup wizard."""
        if user_config.get_spotify_client_id():
            self._authenticate_spotify()
        else:
            self._open_wizard("A0")

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
        if is_spotify:
            self._start_spotify_connect()
            return

        logger.info("Attempting to connect YouTube Music")
        if not user_config.get_spotify_client_id():
            self.show_error(
                "Please connect Spotify first, then connect YouTube Music.",
                title="Connect Spotify first"
            )
            return

        self.show_loading(True, "Connecting to YouTube Music...")
        try:
            if not self._initialize_token_manager():
                return
            self.youtube_client = self.token_manager.authenticate_youtube()
            self.youtube_authenticated = True
            logger.info("YouTube Music authentication successful")
            self._update_card_state(False, True)
            self.show_success(
                "Successfully connected to YouTube Music!", title="Connected"
            )
        except Exception as e:
            logger.error(f"YouTube Music authentication failed: {e}")
            self.show_error(
                "We couldn't connect to YouTube Music. Make sure you're signed in "
                "to YouTube Music in your browser, then try again.",
                title="Connection Error"
            )
        finally:
            self.show_loading(False)

    # ------------------------------------------------------------------
    # Spotify: authenticate + /me diagnosis
    # ------------------------------------------------------------------

    def _authenticate_spotify(self) -> None:
        """Log in with the saved Client ID (PKCE, opens the browser) and verify with /me."""
        self._set_spotify_error(None)
        self.show_loading(True, "Waiting for you in your browser...")
        try:
            if not self._initialize_token_manager():
                return
            client = self.token_manager.authenticate_spotify()
            self._complete_spotify(client)
        except Exception as e:
            logger.error(f"Spotify connect failed: {e}")
            self._set_spotify_error(classify_spotify_error(e))
        finally:
            self.show_loading(False)
            self._close_wizard()

    def _diagnose_me(self, client) -> Tuple[str, Optional[str]]:
        """Call /me once and return ("ok"|"premium", display name).

        Raises whatever the client raises; callers classify it.
        """
        me = client.current_user() or {}
        name = me.get("display_name") or me.get("id") or "your Spotify account"
        if not is_premium(me.get("product")):
            return "premium", name
        return "ok", name

    def _complete_spotify(self, client) -> bool:
        """Apply the /me result: connected, or Premium-required (does NOT proceed)."""
        verdict, name = self._diagnose_me(client)
        if verdict == "premium":
            logger.info("Spotify account is not Premium; not proceeding")
            try:
                self.token_manager.clear_spotify_token()
            except Exception as ex:
                logger.debug(f"Could not clear token: {ex}")
            self.spotify_client = None
            self.spotify_authenticated = False
            self.spotify_name = None
            self._update_card_state(True, False)
            self._set_spotify_error("premium")
            return False

        self.spotify_client = client
        self.spotify_authenticated = True
        self.spotify_name = name
        self.app_state['spotify_client'] = client
        self.app_state['token_manager'] = self.token_manager
        self._update_card_state(True, True, name=name)
        logger.info("Spotify connected")
        return True

    def restore_session(self) -> None:
        """Returning user: reuse the saved Client ID and cached token silently.

        Never raises or shows a dialog; anything that fails just leaves the card
        on "Not connected" so the user can click Connect.
        """
        try:
            if not user_config.get_spotify_client_id():
                return
            if not self._initialize_token_manager():
                return
            tm = self.token_manager
            if tm.is_spotify_authenticated():
                client = tm.get_spotify_client()
                if client is not None:
                    self._complete_spotify(client)
            if tm.is_youtube_authenticated():
                yt = tm.get_youtube_client()
                if yt is not None:
                    self.youtube_client = yt
                    self.youtube_authenticated = True
                    self._update_card_state(False, True)
        except Exception as e:
            logger.warning(f"Could not restore previous session: {e}")

    def show(self, show_back: bool = False, progress_text: Optional[str] = None) -> None:
        """Show the screen, then silently restore any saved connections."""
        super().show(show_back=show_back, progress_text=progress_text)
        self.restore_session()

    # ------------------------------------------------------------------
    # Spotify: Client ID wizard (Option A)
    # ------------------------------------------------------------------

    def _open_wizard(self, step: str = "A0") -> None:
        if self.wizard_dialog is None:
            self.wizard_dialog = ft.AlertDialog(modal=True)
            self.page.overlay.append(self.wizard_dialog)
        self.wizard_dialog.open = True
        self._wizard_go(step)

    def _close_wizard(self, e=None) -> None:
        if self.wizard_dialog is not None and self.wizard_dialog.open:
            self.wizard_dialog.open = False
            self._safe_update()

    def _wizard_text(self, value: str, bold: bool = False, mono: bool = False) -> ft.Text:
        return ft.Text(
            value=value,
            size=app_config.BODY_SIZE,
            color=ft.Colors.WHITE,
            weight=ft.FontWeight.BOLD if bold else None,
            font_family="monospace" if mono else None,
            selectable=True,
        )

    def _wizard_go(self, step: str) -> None:
        """Render wizard step A0-A3 into the dialog."""
        self.wizard_step = step
        self.wizard_connect_button = None
        cancel = ft.TextButton(text="Cancel", on_click=self._close_wizard)

        if step == "A0":
            title = "One-time setup (about 2 minutes)"
            body = [self._wizard_text(
                "Spotify only lets apps talk to a handful of people each \u2014 so "
                "instead of sharing one app with everyone, you'll create your own "
                "private one. It's free, and nobody else can use it. "
                "You'll need Spotify Premium."
            )]
            actions = [
                cancel,
                ft.TextButton(text="I don't have Premium", on_click=self._on_no_premium),
                AppButton(text="Let's do it", primary=True,
                          on_click=lambda e: self._wizard_go("A1")),
            ]
        elif step == "A1":
            title = "1. Create your app on Spotify"
            self._open_url(DASHBOARD_URL)
            self._on_copy_redirect()
            body = [
                self._wizard_text("Spotify's dashboard just opened in your browser. "
                                  "Click Create app and fill in:"),
                self._wizard_text("\u2022 App name \u2014 anything, e.g. My Playlist Mover"),
                self._wizard_text("\u2022 Redirect URI \u2014 paste this exactly "
                                  "(already copied to your clipboard):"),
                ft.Row(controls=[
                    self._wizard_text(REDIRECT_URI, bold=True, mono=True),
                    ft.IconButton(icon=ft.Icons.CONTENT_COPY, tooltip="Copy",
                                  on_click=self._on_copy_redirect),
                ]),
                self._wizard_text("\u2022 Which API/SDKs \u2014 tick Web API"),
                self._wizard_text("\u2022 Agree to the terms, then click Save"),
            ]
            actions = [
                cancel,
                ft.TextButton(text="Open it again", on_click=self._on_open_dashboard),
                AppButton(text="Done \u2014 I created it", primary=True,
                          on_click=lambda e: self._wizard_go("A2")),
            ]
        elif step == "A2":
            title = "2. Paste your Client ID"
            saved = user_config.get_spotify_client_id() or ""
            self.client_id_field = AppTextField(
                label="Client ID", value=saved, on_change=self._on_client_id_change,
                autofocus=True, text_style=ft.TextStyle(font_family="monospace"),
            )
            self.client_id_helper = ft.Text(value="", size=app_config.CAPTION_SIZE)
            self.wizard_connect_button = AppButton(
                text="Connect", primary=True, disabled=True,
                on_click=self._on_wizard_connect,
            )
            body = [
                self._wizard_text(
                    "On your new app's page, click Settings. Copy the Client ID "
                    "(a 32-character code) and paste it here. You do NOT need the "
                    "Client Secret."
                ),
                self.client_id_field,
                self.client_id_helper,
            ]
            actions = [cancel, self.wizard_connect_button]
            self._validate_client_id_field()
        else:  # A3
            title = "3. Log in on Spotify"
            body = [
                ft.ProgressRing(width=32, height=32),
                self._wizard_text(
                    "Spotify opened in your browser. Log in and click Agree. "
                    "We'll finish here automatically."
                ),
            ]
            actions = []

        self.wizard_dialog.title = ft.Text(
            value=title, size=app_config.HEADING_SIZE_SMALL,
            weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE,
        )
        self.wizard_dialog.content = ft.Column(controls=body, tight=True, spacing=10, width=460)
        self.wizard_dialog.actions = actions
        self._safe_update()

    def _on_no_premium(self, e=None) -> None:
        self._close_wizard()
        self._set_spotify_error("premium")

    def _validate_client_id_field(self) -> bool:
        """Validate the pasted Client ID (trimmed) and update helper + button."""
        value = user_config.clean_client_id(self.client_id_field.value)
        if not value:
            self.client_id_valid = False
            self.client_id_helper.value = ""
        elif user_config.is_valid_client_id(value):
            self.client_id_valid = True
            self.client_id_helper.value = "\u2713 Looks right"
            self.client_id_helper.color = app_config.SUCCESS_COLOR
        else:
            self.client_id_valid = False
            self.client_id_helper.value = CLIENT_ID_INVALID_HELP
            self.client_id_helper.color = app_config.ERROR_COLOR
        if self.wizard_connect_button is not None:
            self.wizard_connect_button.disabled = not self.client_id_valid
        return self.client_id_valid

    def _on_client_id_change(self, e=None) -> None:
        self._validate_client_id_field()
        self._safe_update()

    def _on_wizard_connect(self, e=None) -> None:
        """Save the validated Client ID, then log in (A3)."""
        if not self._validate_client_id_field():
            self._safe_update()
            return
        user_config.set_spotify_client_id(self.client_id_field.value)
        self._wizard_go("A3")
        self._authenticate_spotify()

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
                self.spotify_name = None
                if self.token_manager is not None:
                    try:
                        self.token_manager.clear_spotify_token()
                    except Exception as ex:
                        logger.warning(f"Could not clear Spotify token: {ex}")
            else:
                self.youtube_client = None
                self.youtube_authenticated = False
            
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
        
        # Navigate to PlaylistSelectionScreen
        from src.ui.screens.playlist_selection_screen import PlaylistSelectionScreen
        self.navigate_to(PlaylistSelectionScreen, show_back=True, progress_text="Step 2 of 5")
