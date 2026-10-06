"""Tests for the "Include Liked Songs" toggle (CONTEXT_CONTRACT 4.6)."""

import asyncio
from types import SimpleNamespace
from unittest.mock import Mock, patch

import flet as ft
import pytest

from config import app_config
from src.utils import user_config
from src.ui.screens.playlist_selection_screen import PlaylistSelectionScreen

LIKED = {'id': 'liked_songs', 'name': 'Liked Songs', 'tracks_count': 120, 'synthetic': True}
REAL = [
    {'id': 'p1', 'name': 'Rock', 'tracks_count': 10, 'public': True},
    {'id': 'p2', 'name': 'Private Mix', 'tracks_count': 5, 'public': False},
]


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(app_config, "APP_DATA_DIR", tmp_path)
    return tmp_path


@pytest.fixture
def screen(home):
    page = Mock(spec=ft.Page)
    page.overlay = []
    page.run_task = Mock(return_value=None)
    s = PlaylistSelectionScreen(page, {'spotify_client': Mock(), 'cache_manager': Mock(),
                                       'rate_limiter': Mock()})
    s.show_loading = Mock()
    s.show_error = Mock()
    s.build()
    return s


def _fetcher():
    f = Mock()
    f.get_user_playlists.side_effect = (
        lambda use_cache=True, include_liked_songs=True:
        ([LIKED] if include_liked_songs else []) + REAL)
    return f


def _load(s):
    s.fetcher = _fetcher()
    real_sleep = asyncio.sleep
    with patch("asyncio.sleep", new=lambda *_: real_sleep(0)):
        asyncio.run(s.load_playlists())


def test_config_default_true_and_roundtrip(home):
    assert user_config.get_include_liked_songs() is True
    user_config.set_include_liked_songs(False)
    assert user_config.get_include_liked_songs() is False
    user_config.set_include_liked_songs(True)
    assert user_config.get_include_liked_songs() is True


def test_config_garbage_value_defaults_true(home):
    user_config.set(user_config.INCLUDE_LIKED_SONGS_KEY, "nope")
    assert user_config.get_include_liked_songs() is True


def test_build_reads_saved_preference(home):
    user_config.set_include_liked_songs(False)
    page = Mock(spec=ft.Page)
    page.run_task = Mock()
    s = PlaylistSelectionScreen(page, {})
    s.build()
    assert s.include_liked_songs is False
    assert s.liked_switch.value is False
    assert s.liked_switch.label == "Include Liked Songs"


def test_default_on_when_nothing_saved(screen):
    assert screen.liked_switch.value is True


def test_on_fetches_with_liked_and_select_all_includes_it(screen):
    _load(screen)
    screen.fetcher.get_user_playlists.assert_called_with(use_cache=True, include_liked_songs=True)
    screen.on_select_all_click(None)
    assert screen.selected_playlists == {'liked_songs', 'p1', 'p2'}


def test_off_excludes_liked_and_persists(screen, home):
    screen.on_liked_songs_toggle(SimpleNamespace(control=SimpleNamespace(value=False)))
    assert user_config.get_include_liked_songs() is False
    _load(screen)
    screen.fetcher.get_user_playlists.assert_called_with(use_cache=True, include_liked_songs=False)
    screen.on_select_all_click(None)
    assert screen.selected_playlists == {'p1', 'p2'}


def test_turning_off_drops_liked_from_selection(screen):
    screen.selected_playlists = {'liked_songs', 'p1'}
    screen.on_liked_songs_toggle(SimpleNamespace(control=SimpleNamespace(value=False)))
    assert screen.selected_playlists == {'p1'}
    screen.page.run_task.assert_called_with(screen.load_playlists)
