"""YouTube Music connect UI wiring (CaptureHub) + extension manifest sanity."""

import asyncio
import json
import os
from unittest.mock import Mock, patch

import flet as ft
import pytest

from config import app_config
from src.capture import constants
from src.ui.screens import welcome_screen as ws
from src.ui.screens.migration_progress_screen import MigrationProgressScreen
from src.ui.screens.welcome_screen import WelcomeScreen

EXT = os.path.join(os.path.dirname(__file__), "..", "extension")


@pytest.fixture(autouse=True)
def temp_home(tmp_path, monkeypatch):
    monkeypatch.setattr(app_config, "APP_DATA_DIR", str(tmp_path))


def _page():
    p = Mock(spec=ft.Page)
    p.overlay = []
    p.controls = Mock()
    return p


@pytest.fixture
def hub():
    h = Mock()
    h.ports.return_value = []
    h.subscribe.return_value = Mock()
    return h


@pytest.fixture
def screen(hub):
    s = WelcomeScreen(_page(), {"capture_hub": hub})
    s.build()
    s.show_loading = Mock()
    s.show_error = Mock()
    return s


def res(ok, code=None, name="", client=None):
    return Mock(ok=ok, code=code, account_name=name, client=client)


def test_no_extension_shows_install_state_and_auto_advances(screen, hub):
    screen.on_youtube_connect_click(None)
    assert screen.youtube_error_kind == "no_extension"
    assert "browser extension" in screen.youtube_error_text.value
    labels = [b.text for b in screen.youtube_error_row.controls]
    assert labels == ["Add to Chrome", "Add to Edge", "Add to Firefox", "Check again"]
    hub.connect_youtube.assert_not_called()
    hub.subscribe.assert_called_once()

    # extension says hello -> connect starts by itself
    cb = hub.subscribe.call_args[0][0]
    hub.ports.return_value = [{"port_id": "p"}]
    cb("hello", {})
    hub.connect_youtube.assert_called_once()
    assert screen.youtube_error_kind is None

    yt = Mock()
    hub.connect_youtube.call_args[0][0](res(True, name="Sam", client=yt))
    assert screen.youtube_authenticated is True
    assert "Connected as Sam" in screen.youtube_status_text.value
    assert screen.app_state["youtube_client"] is yt


def test_connect_with_live_port_calls_hub(screen, hub):
    hub.ports.return_value = [{"port_id": "p"}]
    screen.on_youtube_connect_click(None)
    hub.connect_youtube.assert_called_once()


def test_does_not_require_spotify_first(screen, hub):
    hub.ports.return_value = [{"port_id": "p"}]
    screen.on_youtube_connect_click(None)
    screen.show_error.assert_not_called()


@pytest.mark.parametrize("code,fragment", [
    ("signed_out", "not signed in to YouTube Music"),
    ("rejected", "didn't accept"),
    ("network", "internet connection"),
    ("rate_limited", "slow down"),
    ("timeout", "Restarting the app"),
    ("no_extension", "browser extension"),
])
def test_failures_map_to_plain_messages(screen, hub, code, fragment):
    hub.ports.return_value = [{"port_id": "p"}]
    screen.on_youtube_connect_click(None)
    hub.connect_youtube.call_args[0][0](res(False, code=code))
    assert screen.youtube_authenticated is False
    assert fragment in screen.youtube_error_text.value
    assert screen.youtube_error_text.visible is True


def test_signed_out_offers_open_youtube(screen, hub):
    hub.ports.return_value = [{"port_id": "p"}]
    screen.on_youtube_connect_click(None)
    hub.connect_youtube.call_args[0][0](res(False, code="signed_out"))
    assert [b.text for b in screen.youtube_error_row.controls] == ["Open YouTube Music", "Try again"]


def test_no_hub_shows_helper_message():
    s = WelcomeScreen(_page(), {})
    s.build()
    s.on_youtube_connect_click(None)
    assert s.youtube_error_kind == "no_helper"


def test_store_urls_use_placeholder_ids():
    assert constants.CHROME_WEB_STORE_ID in ws.CHROME_STORE_URL
    assert constants.EDGE_ADDONS_ID in ws.EDGE_STORE_URL


def test_restore_session_shows_youtube_connected(screen):
    from src.utils import user_config
    user_config.set_spotify_client_id("a" * 32)
    tm = Mock()
    tm.is_spotify_authenticated.return_value = False
    tm.is_youtube_authenticated.return_value = True
    tm.get_youtube_client.return_value = Mock()
    tm.youtube_session_store.load.return_value = ({}, "Sam")
    with patch.object(ws, "TokenManager", return_value=tm):
        screen.restore_session()
    assert screen.youtube_authenticated is True
    assert "Connected as Sam" in screen.youtube_status_text.value


# ---- migration progress wiring ----------------------------------------------

def _progress(hub):
    st = {"spotify_client": Mock(), "youtube_client": Mock(), "cache_manager": Mock(),
          "selected_playlists": [{"id": "1", "name": "A", "tracks_count": 1}],
          "capture_hub": hub}
    s = MigrationProgressScreen(_page(), st)
    s.build()
    return s


def test_start_migration_attaches_engine_to_hub(hub):
    s = _progress(hub)
    mgr = Mock()
    mgr.migrate_playlists.return_value = ["j1"]
    s.show_loading, s.show_error, s._schedule_poll = Mock(), Mock(), Mock()
    with patch("src.ui.screens.migration_progress_screen.MigrationManager", return_value=mgr):
        asyncio.run(s.start_migration())
    hub.attach_engine.assert_called_once_with(mgr)


def test_reconnect_button_shown_for_auth_and_calls_hub(hub):
    s = _progress(hub)
    s._set_wait_banner("auth", "x")
    assert s.reconnect_row.visible is True
    hub.request_capture.return_value = res(True, client=Mock())

    class Inline:
        def __init__(self, target, **kw): self.t = target
        def start(self): self.t()
    with patch("src.ui.screens.migration_progress_screen.threading.Thread", Inline):
        s._on_reconnect_click()
    hub.request_capture.assert_called_once_with("reauth")
    assert s.reconnect_status.value == "Reconnected."
    s._set_wait_banner(None, "")
    assert s.reconnect_row.visible is False


def test_reconnect_failure_message(hub):
    s = _progress(hub)
    s._set_wait_banner("auth", "x")
    hub.request_capture.return_value = res(False, code="signed_out")
    class Inline:
        def __init__(self, target, **kw): self.t = target
        def start(self): self.t()
    with patch("src.ui.screens.migration_progress_screen.threading.Thread", Inline):
        s._on_reconnect_click()
    assert "not signed in" in s.reconnect_status.value


# ---- extension manifests ----------------------------------------------------

def _load(name):
    with open(os.path.join(EXT, name), encoding="utf-8") as fh:
        return json.load(fh)


@pytest.mark.parametrize("name", ["manifest.json", "manifest.firefox.json"])
def test_manifest_minimal_permissions(name):
    m = _load(name)
    assert m["manifest_version"] == 3
    for k in ("name", "version", "description", "action", "background"):
        assert k in m
    assert sorted(m["permissions"]) == ["alarms", "cookies", "nativeMessaging"]
    assert "storage" not in m["permissions"]
    assert m["host_permissions"] == ["https://music.youtube.com/*"]
    assert "127.0.0.1" not in json.dumps(m)


def test_chromium_manifest_has_dev_key():
    m = _load("manifest.json")
    assert m["key"] == constants.DEV_CHROMIUM_EXTENSION_KEY
    assert m["background"] == {"service_worker": "background.js"}


def test_firefox_manifest_has_gecko_id():
    m = _load("manifest.firefox.json")
    assert m["browser_specific_settings"]["gecko"]["id"] == constants.FIREFOX_GECKO_ID
    assert "key" not in m
    assert m["background"]["scripts"] == ["background.js"]


def test_extension_has_no_token_input_or_localhost():
    for f in ("popup.html", "popup.js", "background.js"):
        text = open(os.path.join(EXT, f), encoding="utf-8").read()
        assert "127.0.0.1" not in text and "localhost" not in text
        assert "<input" not in text
    assert constants.HOST_NAME in open(os.path.join(EXT, "background.js")).read()
