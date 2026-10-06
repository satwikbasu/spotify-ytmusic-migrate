"""Tests for WelcomeScreen."""

import pytest
import flet as ft
from unittest.mock import Mock, MagicMock, patch, PropertyMock
import spotipy
from ytmusicapi import YTMusic

from src.ui.screens.welcome_screen import WelcomeScreen
from config import app_config


@pytest.fixture
def mock_page():
    """Create a mock Flet page."""
    page = Mock(spec=ft.Page)
    page.controls = Mock()
    page.overlay = []
    page.update = Mock()
    page.add = Mock()
    return page


@pytest.fixture(autouse=True)
def temp_home(tmp_path, monkeypatch):
    """Redirect ~/.playlist_migrator to a temp dir so tests never touch the real one."""
    monkeypatch.setattr(app_config, 'APP_DATA_DIR', str(tmp_path))
    return tmp_path


@pytest.fixture
def saved_id():
    """A Spotify Client ID the user already entered once."""
    from src.utils import user_config
    return user_config.set_spotify_client_id('a' * 32)


def premium_client(product='premium', name='Sam'):
    client = Mock(spec=spotipy.Spotify)
    client.current_user.return_value = {'display_name': name, 'id': 'sam1', 'product': product}
    return client


@pytest.fixture
def app_state():
    """Create a fresh app state."""
    return {}


@pytest.fixture
def welcome_screen(mock_page, app_state):
    """Create a WelcomeScreen instance."""
    return WelcomeScreen(mock_page, app_state)


class TestWelcomeScreenInitialization:
    """Test WelcomeScreen initialization."""
    
    def test_init_creates_welcome_screen(self, mock_page, app_state):
        """Test WelcomeScreen initializes correctly."""
        screen = WelcomeScreen(mock_page, app_state)
        
        assert screen.page is mock_page
        assert screen.app_state is app_state
        assert screen.spotify_authenticated is False
        assert screen.youtube_authenticated is False
        assert screen.spotify_client is None
        assert screen.youtube_client is None
        assert screen.token_manager is None
    
    def test_init_sets_ui_references_to_none(self, welcome_screen):
        """Test UI component references are initially None."""
        assert welcome_screen.spotify_status_text is None
        assert welcome_screen.spotify_button is None
        assert welcome_screen.youtube_status_text is None
        assert welcome_screen.youtube_button is None
        assert welcome_screen.continue_button is None


class TestWelcomeScreenBuild:
    """Test WelcomeScreen build method."""
    
    def test_build_returns_control(self, welcome_screen):
        """Test build() returns a Flet control."""
        result = welcome_screen.build()
        
        assert isinstance(result, ft.Control)
    
    def test_build_creates_spotify_card(self, welcome_screen):
        """Test build() creates Spotify authentication card."""
        welcome_screen.build()
        
        assert welcome_screen.spotify_status_text is not None
        assert welcome_screen.spotify_button is not None
        assert welcome_screen.spotify_status_text.value == "Not connected"
        assert welcome_screen.spotify_button.text == "Connect"
    
    def test_build_creates_youtube_card(self, welcome_screen):
        """Test build() creates YouTube authentication card."""
        welcome_screen.build()
        
        assert welcome_screen.youtube_status_text is not None
        assert welcome_screen.youtube_button is not None
        assert welcome_screen.youtube_status_text.value == "Not connected"
        assert welcome_screen.youtube_button.text == "Connect"
    
    def test_build_creates_continue_button(self, welcome_screen):
        """Test build() creates continue button."""
        welcome_screen.build()
        
        assert welcome_screen.continue_button is not None
        assert welcome_screen.continue_button.disabled is True
    
    def test_build_uses_config_colors(self, welcome_screen):
        """Test build() uses colors from app_config."""
        result = welcome_screen.build()
        
        # Just verify it doesn't crash
        assert result is not None


class TestWelcomeScreenTokenManager:
    """TokenManager is built from the saved Spotify Client ID only."""

    @patch('src.ui.screens.welcome_screen.TokenManager')
    def test_initialize_token_manager_success(self, mock_tm_class, welcome_screen, saved_id):
        assert welcome_screen._initialize_token_manager() is True
        mock_tm_class.assert_called_once_with(spotify_client_id=saved_id)

    @patch('src.ui.screens.welcome_screen.TokenManager')
    def test_no_google_credentials_required(self, mock_tm_class, welcome_screen, saved_id):
        """Old gate aborted with 'Configuration Error' without YOUTUBE_CLIENT_ID."""
        with patch.object(app_config, 'YOUTUBE_CLIENT_ID', ''), \
             patch.object(app_config, 'YOUTUBE_CLIENT_SECRET', ''), \
             patch.object(welcome_screen, 'show_error') as mock_error:
            assert welcome_screen._initialize_token_manager() is True
        mock_error.assert_not_called()

    @patch('src.ui.screens.welcome_screen.TokenManager')
    def test_no_saved_client_id_returns_false_quietly(self, mock_tm_class, welcome_screen):
        with patch.object(welcome_screen, 'show_error') as mock_error:
            assert welcome_screen._initialize_token_manager() is False
        mock_error.assert_not_called()
        mock_tm_class.assert_not_called()

    @patch('src.ui.screens.welcome_screen.TokenManager')
    def test_initialize_token_manager_exception(self, mock_tm_class, welcome_screen, saved_id):
        mock_tm_class.side_effect = Exception("Init error")
        with patch.object(welcome_screen, 'show_error') as mock_error:
            assert welcome_screen._initialize_token_manager() is False
        mock_error.assert_called_once()


class TestWelcomeScreenCardState:
    """Test authentication card state updates."""
    
    def test_update_spotify_card_authenticated(self, welcome_screen):
        """Test updating Spotify card to authenticated state."""
        welcome_screen.build()
        
        welcome_screen._update_card_state(is_spotify=True, authenticated=True)
        
        assert "Connected" in welcome_screen.spotify_status_text.value
        assert welcome_screen.spotify_button.text == "Disconnect"
        assert welcome_screen.spotify_button.primary is False
    
    def test_update_spotify_card_not_authenticated(self, welcome_screen):
        """Test updating Spotify card to not authenticated state."""
        welcome_screen.build()
        welcome_screen.spotify_authenticated = True
        
        welcome_screen._update_card_state(is_spotify=True, authenticated=False)
        
        assert welcome_screen.spotify_status_text.value == "Not connected"
        assert welcome_screen.spotify_button.text == "Connect"
        assert welcome_screen.spotify_button.primary is True
    
    def test_update_youtube_card_authenticated(self, welcome_screen):
        """Test updating YouTube card to authenticated state."""
        welcome_screen.build()
        
        welcome_screen._update_card_state(is_spotify=False, authenticated=True)
        
        assert "Connected" in welcome_screen.youtube_status_text.value
        assert welcome_screen.youtube_button.text == "Disconnect"
        assert welcome_screen.youtube_button.primary is False
    
    def test_update_youtube_card_not_authenticated(self, welcome_screen):
        """Test updating YouTube card to not authenticated state."""
        welcome_screen.build()
        welcome_screen.youtube_authenticated = True
        
        welcome_screen._update_card_state(is_spotify=False, authenticated=False)
        
        assert welcome_screen.youtube_status_text.value == "Not connected"
        assert welcome_screen.youtube_button.text == "Connect"
        assert welcome_screen.youtube_button.primary is True


class TestWelcomeScreenContinueButton:
    """Test continue button state logic."""
    
    def test_continue_button_disabled_when_none_authenticated(self, welcome_screen):
        """Test continue button is disabled when neither service is authenticated."""
        welcome_screen.build()
        
        welcome_screen._update_continue_button()
        
        assert welcome_screen.continue_button.disabled is True
    
    def test_continue_button_disabled_when_only_spotify_authenticated(self, welcome_screen):
        """Test continue button is disabled when only Spotify is authenticated."""
        welcome_screen.build()
        welcome_screen.spotify_authenticated = True
        
        welcome_screen._update_continue_button()
        
        assert welcome_screen.continue_button.disabled is True
    
    def test_continue_button_disabled_when_only_youtube_authenticated(self, welcome_screen):
        """Test continue button is disabled when only YouTube is authenticated."""
        welcome_screen.build()
        welcome_screen.youtube_authenticated = True
        
        welcome_screen._update_continue_button()
        
        assert welcome_screen.continue_button.disabled is True
    
    def test_continue_button_enabled_when_both_authenticated(self, welcome_screen):
        """Test continue button is enabled when both services are authenticated."""
        welcome_screen.build()
        welcome_screen.spotify_authenticated = True
        welcome_screen.youtube_authenticated = True
        
        welcome_screen._update_continue_button()
        
        assert welcome_screen.continue_button.disabled is False
    
    def test_continue_button_has_animation_when_enabled(self, welcome_screen):
        """Test continue button has pulsing animation when enabled."""
        welcome_screen.build()
        welcome_screen.spotify_authenticated = True
        welcome_screen.youtube_authenticated = True
        
        welcome_screen._update_continue_button()
        
        assert welcome_screen.continue_button.animate_opacity is not None


class TestWelcomeScreenSpotifyConnect:
    """Spotify connection flow (saved Client ID -> PKCE -> /me)."""

    @patch('src.ui.screens.welcome_screen.TokenManager')
    def test_spotify_connect_success(self, mock_tm_class, welcome_screen, saved_id):
        welcome_screen.build()
        tm = Mock()
        client = premium_client()
        tm.authenticate_spotify.return_value = client
        mock_tm_class.return_value = tm

        welcome_screen.on_spotify_connect_click(None)

        assert welcome_screen.spotify_authenticated is True
        assert welcome_screen.spotify_client is client
        assert welcome_screen.app_state['spotify_client'] is client
        assert "Connected as Sam" in welcome_screen.spotify_status_text.value
        tm.authenticate_spotify.assert_called_once()

    @patch('src.ui.screens.welcome_screen.TokenManager')
    def test_connect_error_shows_plain_message(self, mock_tm_class, welcome_screen, saved_id):
        welcome_screen.build()
        tm = Mock()
        tm.authenticate_spotify.side_effect = RuntimeError("Auth failed")
        mock_tm_class.return_value = tm

        welcome_screen.on_spotify_connect_click(None)

        assert welcome_screen.spotify_authenticated is False
        assert welcome_screen.spotify_error_kind == 'generic'
        assert 'Traceback' not in welcome_screen.spotify_error_text.value
        assert 'Auth failed' not in welcome_screen.spotify_error_text.value

    def test_connect_without_client_id_opens_wizard(self, welcome_screen):
        welcome_screen.build()
        with patch.object(welcome_screen, '_open_url'), \
             patch.object(welcome_screen, 'show_error') as mock_error:
            welcome_screen.on_spotify_connect_click(None)
        mock_error.assert_not_called()
        assert welcome_screen.wizard_step == 'A0'


class TestWelcomeScreenYouTubeConnect:
    """YouTube Music connect now goes through CaptureHub (see tests/test_youtube_connect_wiring.py)."""

    def test_youtube_connect_success(self, welcome_screen):
        welcome_screen.build()
        hub = Mock()
        hub.ports.return_value = [{"port_id": "p"}]
        yt = Mock(spec=YTMusic)
        hub.connect_youtube.side_effect = lambda cb: cb(
            Mock(ok=True, client=yt, account_name="Sam", code=None))
        welcome_screen.app_state['capture_hub'] = hub

        welcome_screen.on_youtube_connect_click(None)

        assert welcome_screen.youtube_authenticated is True
        assert welcome_screen.youtube_client is yt
        hub.connect_youtube.assert_called_once()

    def test_youtube_connect_error(self, welcome_screen):
        welcome_screen.build()
        hub = Mock()
        hub.ports.return_value = [{"port_id": "p"}]
        hub.connect_youtube.side_effect = lambda cb: cb(
            Mock(ok=False, client=None, account_name="", code="signed_out"))
        welcome_screen.app_state['capture_hub'] = hub

        welcome_screen.on_youtube_connect_click(None)

        assert welcome_screen.youtube_authenticated is False


class TestWelcomeScreenDisconnect:
    """Test disconnection flow."""
    
    def test_spotify_disconnect_click_shows_confirmation(self, welcome_screen):
        """Test Spotify disconnect shows confirmation dialog."""
        welcome_screen.build()
        welcome_screen.spotify_authenticated = True
        
        with patch.object(welcome_screen, 'show_confirmation') as mock_confirm:
            welcome_screen.on_spotify_connect_click(None)
            
            mock_confirm.assert_called_once()
            call_args = mock_confirm.call_args
            assert "Spotify" in call_args[0][0]
    
    def test_youtube_disconnect_click_shows_confirmation(self, welcome_screen):
        """Test YouTube disconnect shows confirmation dialog."""
        welcome_screen.build()
        welcome_screen.youtube_authenticated = True
        
        with patch.object(welcome_screen, 'show_confirmation') as mock_confirm:
            welcome_screen.on_youtube_connect_click(None)
            
            mock_confirm.assert_called_once()
            call_args = mock_confirm.call_args
            assert "YouTube" in call_args[0][0]
    
    def test_spotify_disconnect_clears_state(self, welcome_screen):
        """Test Spotify disconnect clears authentication state."""
        welcome_screen.build()
        welcome_screen.spotify_authenticated = True
        welcome_screen.spotify_client = Mock()
        
        # Capture the confirmation callback and execute it
        with patch.object(welcome_screen, 'show_confirmation') as mock_confirm:
            welcome_screen._handle_disconnect(is_spotify=True)
            
            # Get the on_confirm callback and call it
            on_confirm = mock_confirm.call_args[1]['on_confirm']
            on_confirm()
        
        assert welcome_screen.spotify_authenticated is False
        assert welcome_screen.spotify_client is None
    
    def test_youtube_disconnect_clears_state(self, welcome_screen):
        """Test YouTube disconnect clears authentication state."""
        welcome_screen.build()
        welcome_screen.youtube_authenticated = True
        welcome_screen.youtube_client = Mock()
        
        # Capture the confirmation callback and execute it
        with patch.object(welcome_screen, 'show_confirmation') as mock_confirm:
            welcome_screen._handle_disconnect(is_spotify=False)
            
            # Get the on_confirm callback and call it
            on_confirm = mock_confirm.call_args[1]['on_confirm']
            on_confirm()
        
        assert welcome_screen.youtube_authenticated is False
        assert welcome_screen.youtube_client is None


class TestWelcomeScreenContinue:
    """Test continue button flow."""
    
    def test_continue_click_requires_both_authenticated(self, welcome_screen):
        """Test continue requires both services authenticated."""
        welcome_screen.build()
        welcome_screen.spotify_authenticated = True
        welcome_screen.youtube_authenticated = False
        
        with patch.object(welcome_screen, 'show_error') as mock_error:
            welcome_screen.on_continue_click(None)
            
            mock_error.assert_called_once()
    
    def test_continue_click_stores_clients_in_app_state(self, welcome_screen):
        """Test continue stores clients in app_state."""
        welcome_screen.build()
        welcome_screen.spotify_authenticated = True
        welcome_screen.youtube_authenticated = True
        welcome_screen.spotify_client = Mock()
        welcome_screen.youtube_client = Mock()
        welcome_screen.token_manager = Mock()
        
        welcome_screen.on_continue_click(None)
        
        assert welcome_screen.app_state['spotify_client'] is welcome_screen.spotify_client
        assert welcome_screen.app_state['youtube_client'] is welcome_screen.youtube_client
        assert welcome_screen.app_state['token_manager'] is welcome_screen.token_manager
    
    def test_continue_click_when_both_authenticated(self, welcome_screen):
        """Test continue click navigates when both authenticated."""
        welcome_screen.build()
        welcome_screen.spotify_authenticated = True
        welcome_screen.youtube_authenticated = True
        welcome_screen.spotify_client = Mock()
        welcome_screen.youtube_client = Mock()
        welcome_screen.token_manager = Mock()
        
        # Should not raise error
        welcome_screen.on_continue_click(None)


class TestWelcomeScreenIntegration:
    """Integration tests for WelcomeScreen."""
    
    @patch('src.ui.screens.welcome_screen.TokenManager')
    def test_full_authentication_flow(self, mock_token_manager_class, welcome_screen, saved_id):
        """Test complete authentication flow for both services."""
        # Setup
        welcome_screen.build()
        mock_token_manager = Mock()
        mock_spotify_client = premium_client()
        mock_youtube_client = Mock(spec=YTMusic)
        mock_token_manager.authenticate_spotify.return_value = mock_spotify_client
        mock_token_manager.authenticate_youtube.return_value = mock_youtube_client
        mock_token_manager_class.return_value = mock_token_manager
        hub = Mock()
        hub.ports.return_value = [{"port_id": "p"}]
        hub.connect_youtube.side_effect = lambda cb: cb(
            Mock(ok=True, client=mock_youtube_client, account_name="Sam", code=None))
        welcome_screen.app_state['capture_hub'] = hub
        
        with patch.object(app_config, 'SPOTIFY_CLIENT_ID', 'spotify_id'), \
             patch.object(app_config, 'SPOTIFY_CLIENT_SECRET', 'spotify_secret'), \
             patch.object(app_config, 'YOUTUBE_CLIENT_ID', 'youtube_id'), \
             patch.object(app_config, 'YOUTUBE_CLIENT_SECRET', 'youtube_secret'):
            
            # Authenticate Spotify
            welcome_screen.on_spotify_connect_click(None)
            assert welcome_screen.spotify_authenticated is True
            
            # Continue button should still be disabled
            assert welcome_screen.continue_button.disabled is True
            
            # Authenticate YouTube
            welcome_screen.on_youtube_connect_click(None)
            assert welcome_screen.youtube_authenticated is True
            
            # Continue button should now be enabled
            welcome_screen._update_continue_button()
            assert welcome_screen.continue_button.disabled is False
            
            # Continue should work
            welcome_screen.on_continue_click(None)
            assert 'spotify_client' in welcome_screen.app_state
            assert 'youtube_client' in welcome_screen.app_state
    
    def test_show_with_progress_text(self, welcome_screen):
        """Test showing screen with progress indicator."""
        # Build and show screen
        welcome_screen.show(progress_text="Step 1 of 5")
        
        # Verify page was updated
        welcome_screen.page.add.assert_called()
        welcome_screen.page.update.assert_called()


class TestWelcomeScreenErrorHandling:
    """Error handling in WelcomeScreen."""

    @patch('src.ui.screens.welcome_screen.TokenManager')
    def test_unexpected_exception_shows_plain_message(self, mock_tm_class, welcome_screen, saved_id):
        welcome_screen.build()
        tm = Mock()
        tm.authenticate_spotify.side_effect = Exception("boom")
        mock_tm_class.return_value = tm

        welcome_screen.on_spotify_connect_click(None)

        assert welcome_screen.spotify_error_kind == 'generic'
        assert "Something went wrong" in welcome_screen.spotify_error_text.value
