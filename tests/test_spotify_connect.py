"""Tests for the Spotify "Login with Spotify" experience (Option A wizard,
persisted Client ID, connect-first returning user, Premium gate)."""

import json
from unittest.mock import Mock, patch

import flet as ft
import pytest
import spotipy

from config import app_config
from src.ui.screens import welcome_screen as ws
from src.ui.screens.welcome_screen import WelcomeScreen, classify_spotify_error
from src.utils import user_config

GOOD_ID = "0123456789abcdef0123456789abcdef"


@pytest.fixture(autouse=True)
def temp_home(tmp_path, monkeypatch):
    monkeypatch.setattr(app_config, "APP_DATA_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def screen():
    page = Mock(spec=ft.Page)
    page.overlay = []
    page.controls = Mock()
    s = WelcomeScreen(page, {})
    s.build()
    return s


def me_client(product="premium", name="Sam"):
    c = Mock(spec=spotipy.Spotify)
    c.current_user.return_value = {"display_name": name, "id": "u1", "product": product}
    return c


class TestClientIdValidation:
    @pytest.mark.parametrize("value", [GOOD_ID, "a" * 32, "0" * 32])
    def test_good(self, value):
        assert user_config.is_valid_client_id(value)

    @pytest.mark.parametrize("value", [
        "", None, "abc", "g" * 32, "A" * 32, GOOD_ID + "0", GOOD_ID[:-1], "my app name",
    ])
    def test_bad(self, value):
        assert not user_config.is_valid_client_id(value)

    def test_whitespace_trimmed(self):
        assert user_config.is_valid_client_id(f"  {GOOD_ID}\n")
        assert user_config.clean_client_id(f"  {GOOD_ID}\n") == GOOD_ID

    def test_wizard_field_validation_and_button(self, screen):
        with patch.object(screen, "_open_url"):
            screen._open_wizard("A2")
        screen.client_id_field.value = "nope"
        screen._on_client_id_change()
        assert screen.wizard_connect_button.disabled is True
        assert "32 letters and numbers" in screen.client_id_helper.value
        screen.client_id_field.value = f"  {GOOD_ID} "
        screen._on_client_id_change()
        assert screen.wizard_connect_button.disabled is False
        assert "Looks right" in screen.client_id_helper.value


class TestUserConfig:
    def test_round_trip_under_temp_home(self, temp_home):
        assert user_config.get_spotify_client_id() is None
        user_config.set_spotify_client_id(f" {GOOD_ID} ")
        assert user_config.get_spotify_client_id() == GOOD_ID
        path = temp_home / "user_config.json"
        assert json.loads(path.read_text()) == {"spotify_client_id": GOOD_ID}

    def test_rejects_invalid(self):
        with pytest.raises(ValueError):
            user_config.set_spotify_client_id("short")

    def test_generic_get_set_and_corrupt_file(self, temp_home):
        user_config.set("x", 1)
        assert user_config.get("x") == 1
        (temp_home / "user_config.json").write_text("{not json")
        assert user_config.get("x", "d") == "d"
        assert user_config.get_spotify_client_id() is None

    def test_clear(self):
        user_config.set_spotify_client_id(GOOD_ID)
        user_config.clear()
        assert user_config.get_spotify_client_id() is None


class TestReturningUser:
    @patch.object(ws, "TokenManager")
    def test_renders_connected_as(self, tm_cls, screen):
        user_config.set_spotify_client_id(GOOD_ID)
        tm = tm_cls.return_value
        tm.is_spotify_authenticated.return_value = True
        tm.is_youtube_authenticated.return_value = False
        tm.get_spotify_client.return_value = me_client(name="Sam")

        screen.restore_session()

        assert screen.spotify_authenticated is True
        assert screen.spotify_status_text.value == "✅ Connected as Sam"
        assert screen.spotify_button.text == "Disconnect"
        assert screen.app_state["spotify_client"] is tm.get_spotify_client.return_value
        tm_cls.assert_called_once_with(spotify_client_id=GOOD_ID)

    @patch.object(ws, "TokenManager")
    def test_lands_on_connect_screen_not_skipped(self, tm_cls, screen):
        """Continue is available, but nothing navigates automatically."""
        user_config.set_spotify_client_id(GOOD_ID)
        tm = tm_cls.return_value
        tm.is_spotify_authenticated.return_value = True
        tm.is_youtube_authenticated.return_value = True
        tm.get_spotify_client.return_value = me_client()
        tm.get_youtube_client.return_value = Mock()
        with patch.object(screen, "navigate_to") as nav:
            screen.restore_session()
        nav.assert_not_called()
        assert screen.continue_button.disabled is False

    @patch.object(ws, "TokenManager")
    def test_no_stored_id_does_nothing(self, tm_cls, screen):
        screen.restore_session()
        tm_cls.assert_not_called()
        assert screen.spotify_authenticated is False

    @patch.object(ws, "TokenManager")
    def test_failure_is_silent(self, tm_cls, screen):
        user_config.set_spotify_client_id(GOOD_ID)
        tm_cls.return_value.is_spotify_authenticated.side_effect = RuntimeError("x")
        with patch.object(screen, "show_error") as err:
            screen.restore_session()
        err.assert_not_called()
        assert screen.spotify_authenticated is False


class TestPremiumGate:
    @patch.object(ws, "TokenManager")
    def test_free_account_shown_message_and_not_connected(self, tm_cls, screen):
        user_config.set_spotify_client_id(GOOD_ID)
        tm = tm_cls.return_value
        tm.authenticate_spotify.return_value = me_client(product="free")

        screen.on_spotify_connect_click(None)

        assert screen.spotify_authenticated is False
        assert screen.spotify_error_kind == "premium"
        text = screen.spotify_error_text.value
        assert "Spotify Premium required right now" in text
        assert "Free support is coming in a future update" in text
        assert "spotify_client" not in screen.app_state
        tm.clear_spotify_token.assert_called_once()
        assert screen.continue_button.disabled is True

    @patch.object(ws, "TokenManager")
    def test_open_product_also_blocked(self, tm_cls, screen):
        user_config.set_spotify_client_id(GOOD_ID)
        tm_cls.return_value.authenticate_spotify.return_value = me_client(product="open")
        screen.on_spotify_connect_click(None)
        assert screen.spotify_authenticated is False

    def test_premium_variants(self):
        assert ws.is_premium("premium") and ws.is_premium("premium_family")
        assert not ws.is_premium("free") and not ws.is_premium(None)

    @patch.object(ws, "TokenManager")
    def test_continue_never_proceeds_for_free(self, tm_cls, screen):
        user_config.set_spotify_client_id(GOOD_ID)
        tm_cls.return_value.authenticate_spotify.return_value = me_client(product="free")
        screen.on_spotify_connect_click(None)
        screen.youtube_authenticated = True
        with patch.object(screen, "show_error") as err, patch.object(screen, "navigate_to") as nav:
            screen.on_continue_click(None)
        err.assert_called_once()
        nav.assert_not_called()


class TestErrorCatalog:
    @pytest.mark.parametrize("exc,kind", [
        (RuntimeError("INVALID_CLIENT: Invalid redirect URI"), "redirect"),
        (RuntimeError("invalid_client"), "invalid_client"),
        (RuntimeError("User not registered in the Developer Dashboard"), "not_allowed"),
        (RuntimeError("User denied authorization"), "cancelled"),
        (RuntimeError("Spotify authentication timed out"), "cancelled"),
        (RuntimeError("Connection refused"), "network"),
        (spotipy.SpotifyException(401, -1, "Spotify authentication failed: x. Check the "
                                  "Client ID and that redirect URI"), "auth_rejected"),
        (ValueError("weird"), "generic"),
    ])
    def test_classify(self, exc, kind):
        assert classify_spotify_error(exc) == kind

    @pytest.mark.parametrize("kind", list(ws.SPOTIFY_ERRORS))
    def test_every_error_has_plain_message_and_remedy(self, kind):
        msg, remedies = ws.SPOTIFY_ERRORS[kind]
        assert msg and remedies
        assert "Traceback" not in msg and "HTTP" not in msg

    @patch.object(ws, "TokenManager")
    def test_redirect_error_has_remedy_buttons(self, tm_cls, screen):
        user_config.set_spotify_client_id(GOOD_ID)
        tm_cls.return_value.authenticate_spotify.side_effect = RuntimeError("Invalid redirect URI")
        screen.on_spotify_connect_click(None)
        assert screen.spotify_error_kind == "redirect"
        assert "http://127.0.0.1/callback" in screen.spotify_error_text.value
        assert len(screen.spotify_error_row.controls) == 3


class TestWizard:
    def test_a0_to_a1_opens_dashboard_and_copies_redirect(self, screen):
        with patch.object(screen, "_open_url") as opener:
            screen._open_wizard("A0")
            assert screen.wizard_step == "A0"
            screen._wizard_go("A1")
        opener.assert_called_once_with("https://developer.spotify.com/dashboard")
        screen.page.set_clipboard.assert_called_with("http://127.0.0.1/callback")
        assert screen.wizard_step == "A1"

    @patch.object(ws, "TokenManager")
    def test_connect_saves_id_runs_auth_and_closes(self, tm_cls, screen):
        tm_cls.return_value.authenticate_spotify.return_value = me_client()
        with patch.object(screen, "_open_url"):
            screen._open_wizard("A2")
        screen.client_id_field.value = f" {GOOD_ID} "
        screen._on_wizard_connect()
        assert user_config.get_spotify_client_id() == GOOD_ID
        assert screen.spotify_authenticated is True
        assert screen.wizard_dialog.open is False

    def test_invalid_id_not_saved(self, screen):
        with patch.object(screen, "_open_url"):
            screen._open_wizard("A2")
        screen.client_id_field.value = "bad"
        screen._on_wizard_connect()
        assert user_config.get_spotify_client_id() is None

    def test_no_premium_button_shows_message(self, screen):
        screen._open_wizard("A0")
        screen._on_no_premium()
        assert screen.spotify_error_kind == "premium"
        assert screen.wizard_dialog.open is False


class TestNoGoogleCreds:
    @patch.object(ws, "TokenManager")
    def test_connect_works_with_youtube_env_unset(self, tm_cls, screen):
        user_config.set_spotify_client_id(GOOD_ID)
        tm_cls.return_value.authenticate_spotify.return_value = me_client()
        with patch.object(app_config, "YOUTUBE_CLIENT_ID", ""), \
             patch.object(app_config, "YOUTUBE_CLIENT_SECRET", ""), \
             patch.object(screen, "show_error") as err:
            screen.on_spotify_connect_click(None)
        err.assert_not_called()
        assert screen.spotify_authenticated is True
        assert tm_cls.call_args.kwargs == {"spotify_client_id": GOOD_ID}
