"""Tests for background survival in main.py (CONTEXT_CONTRACT §4.3).

Closing the window with an active migration must hide the app (tray, or
minimize when no tray is available) instead of stopping the job; with no job it
exits as before. The sleep guard must inhibit OS sleep only while a job is
active. All GUI/tray/OS calls are mocked; nothing needs a display.
"""

from unittest.mock import Mock, MagicMock, patch

import pytest

import main
from src.utils import power


def _status(**overrides):
    status = {
        'total_jobs': 0, 'completed_jobs': 0, 'failed_jobs': 0,
        'queued_jobs': 0, 'in_progress_jobs': 0, 'current_job': None,
        'queue_size': 0, 'is_paused': False, 'error_count': 0,
        'is_running': True,
    }
    status.update(overrides)
    return status


def _manager(**overrides):
    manager = Mock()
    manager.get_migration_status = Mock(return_value=_status(**overrides))
    manager.stop = Mock()
    return manager


def _page():
    page = MagicMock()
    page.window = MagicMock()
    return page


def _close_event():
    event = Mock()
    event.data = "close"
    return event


class TestIsMigrationActive:
    def test_no_manager(self):
        assert main.is_migration_active({}) is False
        assert main.is_migration_active({'migration_manager': None}) is False

    def test_idle_worker_running_but_nothing_queued(self):
        assert main.is_migration_active({'migration_manager': _manager()}) is False

    def test_current_job_counts_as_active(self):
        mgr = _manager(current_job={'job_id': 'j1'}, in_progress_jobs=1)
        assert main.is_migration_active({'migration_manager': mgr}) is True

    def test_queued_jobs_count_as_active(self):
        mgr = _manager(queued_jobs=3)
        assert main.is_migration_active({'migration_manager': mgr}) is True

    def test_worker_stopped_is_inactive_even_with_jobs(self):
        mgr = _manager(queued_jobs=3, is_running=False)
        assert main.is_migration_active({'migration_manager': mgr}) is False

    def test_paused_job_is_still_active(self):
        """Pausing (e.g. for re-capture) must not let the close button kill the job."""
        mgr = _manager(current_job={'job_id': 'j1'}, is_paused=True)
        assert main.is_migration_active({'migration_manager': mgr}) is True

    def test_broken_status_is_inactive(self):
        mgr = Mock()
        mgr.get_migration_status = Mock(side_effect=RuntimeError("boom"))
        assert main.is_migration_active({'migration_manager': mgr}) is False


class TestWindowCloseWithActiveJob:
    def test_close_hides_to_tray_and_keeps_job(self):
        mgr = _manager(current_job={'job_id': 'j1'}, in_progress_jobs=1)
        app_state = {'migration_manager': mgr, 'cache_manager': Mock()}
        page = _page()

        with patch.object(main.TrayIcon, 'start', return_value=True):
            main.handle_window_event(_close_event(), app_state, page)

        mgr.stop.assert_not_called()
        app_state['cache_manager'].close.assert_not_called()
        page.window.destroy.assert_not_called()
        assert isinstance(app_state.get('tray_icon'), main.TrayIcon)
        assert page.window.visible is False
        assert page.window.skip_task_bar is True

    def test_close_without_tray_minimizes_and_keeps_job(self):
        mgr = _manager(queued_jobs=2)
        app_state = {'migration_manager': mgr, 'cache_manager': Mock()}
        page = _page()

        with patch.object(main.TrayIcon, 'start', return_value=False):
            mode = main.hide_to_background(page, app_state)

        assert mode == 'minimized'
        assert page.window.minimized is True
        mgr.stop.assert_not_called()
        page.window.destroy.assert_not_called()
        assert 'tray_icon' not in app_state

    def test_tray_start_failure_never_raises(self):
        """Importing pystray can itself blow up headless; must degrade."""
        tray = main.TrayIcon(on_show=Mock(), on_quit=Mock())
        with patch.dict('sys.modules', {'pystray': None}):
            assert tray.start() is False
        tray.stop()  # no icon: safe

    def test_tray_show_restores_window(self):
        app_state = {}
        page = _page()
        tray = Mock()
        app_state['tray_icon'] = tray

        main.show_window(page, app_state)

        tray.stop.assert_called_once()
        assert 'tray_icon' not in app_state
        assert page.window.visible is True
        assert page.window.skip_task_bar is False

    def test_tray_quit_stops_migration_and_destroys_window(self):
        mgr = _manager(current_job={'job_id': 'j1'})
        cache = Mock()
        tray = Mock()
        app_state = {'migration_manager': mgr, 'cache_manager': cache, 'tray_icon': tray}
        page = _page()

        main.quit_application(page, app_state)

        tray.stop.assert_called_once()
        mgr.stop.assert_called_once()
        cache.close.assert_called_once()
        page.window.destroy.assert_called_once()

    def test_tray_menu_callbacks_are_wired(self):
        """hide_to_background wires Show -> show_window and Quit -> quit_application."""
        mgr = _manager(current_job={'job_id': 'j1'})
        app_state = {'migration_manager': mgr, 'cache_manager': None}
        page = _page()
        captured = {}

        def fake_start(self):
            captured['tray'] = self
            return True

        with patch.object(main.TrayIcon, 'start', fake_start):
            main.hide_to_background(page, app_state)

        tray = captured['tray']
        tray.on_show()
        assert page.window.visible is True
        tray.on_quit()
        mgr.stop.assert_called_once()
        page.window.destroy.assert_called_once()


class TestWindowCloseWithoutJob:
    def test_close_exits_normally(self):
        mgr = _manager()  # worker running, nothing queued
        cache = Mock()
        guard = Mock()
        app_state = {'migration_manager': mgr, 'cache_manager': cache}
        page = _page()

        with patch.object(main.TrayIcon, 'start') as tray_start:
            main.handle_window_event(_close_event(), app_state, page, guard)

        tray_start.assert_not_called()
        guard.stop.assert_called_once()
        mgr.stop.assert_called_once()
        cache.close.assert_called_once()
        page.window.destroy.assert_called_once()

    def test_close_with_no_manager_destroys_window(self):
        page = _page()
        main.handle_window_event(_close_event(), {'migration_manager': None, 'cache_manager': None}, page)
        page.window.destroy.assert_called_once()

    def test_non_close_event_ignored(self):
        event = Mock()
        event.data = "focus"
        page = _page()
        mgr = _manager(current_job={'job_id': 'j1'})
        main.handle_window_event(event, {'migration_manager': mgr}, page)
        mgr.stop.assert_not_called()
        page.window.destroy.assert_not_called()


class TestMainWiring:
    def test_main_sets_prevent_close_and_window_handler(self):
        import flet as ft
        page = MagicMock(spec=ft.Page)
        page.overlay = []
        page.window = MagicMock()
        app_state = {}

        with patch('main.initialize_app_state', return_value=app_state), \
             patch('main.WelcomeScreen'), \
             patch.object(main.SleepGuard, 'start') as guard_start:
            main.main(page)

        assert page.window.prevent_close is True
        assert callable(page.window.on_event)
        guard_start.assert_called_once()
        # app_state is left untouched for the screens
        assert app_state == {}


class TestSleepGuard:
    def test_tick_inhibits_when_active_and_releases_when_idle(self, monkeypatch):
        mgr = _manager(current_job={'job_id': 'j1'})
        app_state = {'migration_manager': mgr}
        guard = main.SleepGuard(app_state, interval=0.01)

        inhibit = Mock(return_value=power.SleepInhibitor("r", power.BACKEND_LINUX, active=True))
        release = Mock()
        monkeypatch.setattr(main.power, 'inhibit_sleep', inhibit)
        monkeypatch.setattr(main.power, 'release_sleep', release)

        guard.tick()
        inhibit.assert_called_once()
        assert guard.inhibiting is True

        guard.tick()  # still active: no second acquire
        inhibit.assert_called_once()

        mgr.get_migration_status.return_value = _status()  # job finished
        guard.tick()
        release.assert_called_once()
        assert guard.handle is None

    def test_stop_releases_and_never_touches_os_when_idle(self, monkeypatch):
        inhibit = Mock()
        monkeypatch.setattr(main.power, 'inhibit_sleep', inhibit)
        guard = main.SleepGuard({'migration_manager': None}, interval=0.01)
        guard.start()
        guard.tick()
        guard.stop()
        inhibit.assert_not_called()
        assert guard.inhibiting is False

    def test_tick_survives_power_errors(self, monkeypatch):
        mgr = _manager(current_job={'job_id': 'j1'})
        monkeypatch.setattr(main.power, 'inhibit_sleep', Mock(side_effect=RuntimeError("x")))
        guard = main.SleepGuard({'migration_manager': mgr})
        guard.tick()  # must not raise
        assert guard.handle is None
