"""Tests for MigrationProgressScreen."""

import pytest
from unittest.mock import Mock, patch, MagicMock, call
import time
import threading

from src.ui.screens.migration_progress_screen import MigrationProgressScreen
import flet as ft


@pytest.fixture
def mock_page():
    """Create a mock Flet page."""
    page = Mock(spec=ft.Page)
    page.controls = Mock()
    page.overlay = []
    page.update = Mock()
    page.add = Mock()
    page.run_task = Mock(return_value=None)
    return page


@pytest.fixture
def app_state():
    """Create mock app state with all required components."""
    return {
        'spotify_client': Mock(),
        'youtube_client': Mock(),
        'cache_manager': Mock(),
        'selected_playlists': [
            {
                'id': 'playlist1',
                'name': 'Rock Classics',
                'track_count': 50
            },
            {
                'id': 'playlist2',
                'name': 'Pop Hits',
                'track_count': 30
            }
        ]
    }


@pytest.fixture
def screen(mock_page, app_state):
    """Create a MigrationProgressScreen instance."""
    return MigrationProgressScreen(mock_page, app_state)


class TestMigrationProgressScreenInitialization:
    """Test screen initialization."""
    
    def test_init_creates_screen(self, mock_page, app_state):
        """Test that screen can be instantiated."""
        screen = MigrationProgressScreen(mock_page, app_state)
        assert screen is not None
        assert screen.page == mock_page
        assert screen.app_state == app_state
    
    def test_init_sets_default_state(self, screen):
        """Test that initialization sets default state values."""
        assert screen.migration_manager is None
        assert screen.current_playlist_index == 0
        assert screen.current_playlist_name == ""
        assert screen.current_track_index == 0
        assert screen.current_track_name == ""
        assert screen.total_playlists == 0
        assert screen.total_tracks == 0
        assert screen.matched_count == 0
        assert screen.failed_count == 0
        assert screen.start_time is None
        assert screen.is_paused is False
        assert screen.is_cancelled is False
    
    def test_init_sets_ui_references_to_none(self, screen):
        """Test that UI component references start as None."""
        assert screen.sync_icon is None
        assert screen.playlist_text is None
        assert screen.track_text is None
        assert screen.track_name_text is None
        assert screen.progress_bar is None
        assert screen.matched_text is None
        assert screen.failed_text is None
        assert screen.time_text is None
        assert screen.pause_button is None
        assert screen.cancel_button is None


class TestMigrationProgressScreenBuild:
    """Test screen build method."""
    
    def test_build_returns_control(self, screen):
        """Test that build returns a Flet control."""
        content = screen.build()
        assert content is not None
        assert isinstance(content, ft.Control)
    
    def test_build_creates_ui_components(self, screen):
        """Test that build creates all UI components."""
        screen.build()
        
        # Check that all UI references are set
        assert screen.sync_icon is not None
        assert screen.playlist_text is not None
        assert screen.track_text is not None
        assert screen.track_name_text is not None
        assert screen.progress_bar is not None
        assert screen.matched_text is not None
        assert screen.failed_text is not None
        assert screen.time_text is not None
        assert screen.pause_button is not None
        assert screen.cancel_button is not None
    
    def test_build_sets_initial_text_values(self, screen):
        """Test that build sets initial text values."""
        screen.build()
        
        assert screen.playlist_text.value == "Preparing migration..."
        assert screen.track_text.value == "Track 0 of 0"
        assert screen.track_name_text.value == ""
        assert "Matched: 0" in screen.matched_text.value
        assert "Failed: 0" in screen.failed_text.value
    
    def test_build_creates_sync_icon_with_animation(self, screen):
        """Test that sync icon is created with rotation animation."""
        screen.build()
        
        assert screen.sync_icon is not None
        assert screen.sync_icon.name == ft.Icons.SYNC
        assert screen.sync_icon.rotate is not None
    
    def test_build_creates_pause_and_cancel_buttons(self, screen):
        """Test that action buttons are created."""
        screen.build()
        
        assert screen.pause_button is not None
        assert screen.pause_button.text == "Pause"
        assert screen.cancel_button is not None
        assert screen.cancel_button.text == "Cancel"
    
    def test_build_calls_run_task_to_start_migration(self, screen):
        """Test that build triggers migration start."""
        screen.build()
        
        # Should call page.run_task with start_migration
        screen.page.run_task.assert_called_once()


class TestMigrationProgressScreenProgressUpdates:
    """Test progress update functionality."""
    
    def test_on_progress_update_updates_state(self, screen):
        """Test that progress callback updates internal state."""
        screen.last_update_time = 0  # Force update
        
        screen.on_progress_update(
            playlist_name="Rock Classics",
            current=10,
            total=50,
            track_name="Bohemian Rhapsody"
        )
        
        assert screen.current_playlist_name == "Rock Classics"
        assert screen.current_track_index == 10
        assert screen.current_track_name == "Bohemian Rhapsody"
    
    def test_on_progress_update_calculates_stats(self, screen):
        """Test that progress update calculates success/failure stats."""
        screen.last_update_time = 0
        
        # BackgroundWorker.progress_wrapper supplies matched/failed explicitly
        screen.on_progress_update(
            playlist_name="Rock Classics",
            current=20,
            total=50,
            track_name="Test Track",
            matched=15,
            failed=4
        )
        
        assert screen.matched_count == 15
        assert screen.failed_count == 4
    
    def test_on_progress_update_throttles_updates(self, screen):
        """Test that updates are throttled to avoid UI lag."""
        screen.page.update = Mock()
        screen.last_update_time = time.time()  # Set to now
        
        # Call update immediately - should be throttled
        screen.on_progress_update("Test", 1, 10, "Track")
        
        # UI should not be updated due to throttling
        screen.page.update.assert_not_called()


class TestMigrationProgressScreenUIUpdates:
    """Test UI update functionality."""
    
    def test_update_ui_updates_playlist_text(self, screen):
        """Test that UI update changes playlist text."""
        screen.build()
        screen.current_playlist_name = "Rock Classics"
        screen.current_playlist_index = 0
        screen.total_playlists = 2
        
        screen._update_ui()
        
        assert "Rock Classics" in screen.playlist_text.value
        assert "1 of 2" in screen.playlist_text.value
    
    def test_update_ui_updates_track_text(self, screen):
        """Test that UI update changes track text."""
        screen.build()
        screen.current_track_index = 15
        screen.total_tracks = 80
        
        screen._update_ui()
        
        assert "Track 15 of 80" in screen.track_text.value
    
    def test_update_ui_updates_track_name(self, screen):
        """Test that UI update changes current track name."""
        screen.build()
        screen.current_track_name = "Bohemian Rhapsody"
        
        screen._update_ui()
        
        assert "Bohemian Rhapsody" in screen.track_name_text.value
    
    def test_update_ui_updates_progress_bar(self, screen):
        """Test that UI update changes progress bar."""
        screen.build()
        # The bar is OVERALL progress (all playlists), not the per-playlist index
        screen.processed_tracks = 40
        screen.current_track_index = 3
        screen.total_tracks = 80

        screen._update_ui()

        # Should update to 50% (40/80)
        assert screen.progress_bar.value == 0.5
        assert screen.progress_bar.progress_bar.value == 0.5
        assert "50%" in screen.progress_bar.text_label.value
    
    def test_update_ui_updates_statistics(self, screen):
        """Test that UI update changes matched/failed counts."""
        screen.build()
        screen.matched_count = 35
        screen.failed_count = 5
        
        screen._update_ui()
        
        assert "35" in screen.matched_text.value
        assert "5" in screen.failed_text.value
    
    def test_update_ui_calls_page_update(self, screen):
        """Test that UI update calls page.update()."""
        screen.build()
        screen.page.update = Mock()
        
        screen._update_ui()
        
        screen.page.update.assert_called_once()


class TestMigrationProgressScreenTimeEstimation:
    """Test time estimation functionality."""
    
    def test_calculate_estimated_time_initial(self, screen):
        """Test time estimation before migration starts."""
        result = screen.calculate_estimated_time()
        assert result == "Calculating..."
    
    def test_calculate_estimated_time_no_completed_tracks(self, screen):
        """Test time estimation with no completed tracks."""
        screen.start_time = time.time()
        screen.total_tracks = 100
        screen.matched_count = 0
        screen.failed_count = 0
        
        result = screen.calculate_estimated_time()
        assert result == "Calculating..."
    
    def test_calculate_estimated_time_under_minute(self, screen):
        """Test time estimation for short durations."""
        screen.start_time = time.time() - 10  # 10 seconds ago
        screen.total_tracks = 100
        screen.matched_count = 50
        screen.failed_count = 0
        
        result = screen.calculate_estimated_time()
        assert "Less than 1 minute" in result
    
    def test_calculate_estimated_time_minutes(self, screen):
        """Test time estimation in minutes."""
        screen.start_time = time.time() - 60  # 1 minute ago
        screen.total_tracks = 100
        screen.matched_count = 25
        screen.failed_count = 0
        
        result = screen.calculate_estimated_time()
        assert "minute" in result
    
    def test_calculate_estimated_time_hours(self, screen):
        """Test time estimation in hours."""
        screen.start_time = time.time() - 3600  # 1 hour ago
        screen.total_tracks = 1000
        screen.matched_count = 100
        screen.failed_count = 0
        
        result = screen.calculate_estimated_time()
        assert "hour" in result


class TestMigrationProgressScreenPauseResume:
    """Test pause/resume functionality."""
    
    def test_on_pause_click_pauses_migration(self, screen):
        """Test that pause button pauses migration."""
        screen.build()
        screen.migration_manager = Mock()
        screen.is_paused = False
        
        screen.on_pause_click(Mock())
        
        screen.migration_manager.pause_migrations.assert_called_once()
        assert screen.is_paused is True
        assert screen.pause_button.text == "Resume"
    
    def test_on_pause_click_resumes_migration(self, screen):
        """Test that resume button resumes migration."""
        screen.build()
        screen.migration_manager = Mock()
        screen.is_paused = True
        screen.pause_button.text = "Resume"
        
        screen.on_pause_click(Mock())
        
        screen.migration_manager.resume_migrations.assert_called_once()
        assert screen.is_paused is False
        assert screen.pause_button.text == "Pause"
    
    def test_on_pause_click_without_manager(self, screen):
        """Test pause click when migration manager not initialized."""
        screen.build()
        screen.migration_manager = None
        
        # Should not raise exception
        screen.on_pause_click(Mock())
    
    def test_pause_shows_status_banner(self, screen):
        """Test that pausing shows a status banner."""
        screen.build()
        screen.migration_manager = Mock()
        screen.is_paused = False
        
        screen.on_pause_click(Mock())
        
        # Should add status banner to overlay
        assert len(screen.page.overlay) > 0


class TestMigrationProgressScreenCancel:
    """Test cancel functionality."""
    
    def test_on_cancel_click_shows_confirmation(self, screen):
        """Test that cancel button shows confirmation dialog."""
        screen.build()
        
        with patch.object(screen, 'show_confirmation') as mock_confirm:
            screen.on_cancel_click(Mock())
            
            mock_confirm.assert_called_once()
            # Check that message contains warning
            args = mock_confirm.call_args
            assert "sure" in args[1]['message'].lower()
    
    def test_handle_cancel_confirmed_stops_migration(self, screen):
        """Test that confirmed cancel stops migration."""
        screen.migration_manager = Mock()
        screen.migration_manager.cancel_all.return_value = 2
        
        with patch.object(screen, 'show_loading'):
            with patch.object(screen, 'navigate_to'):
                screen._handle_cancel_confirmed(Mock())
                
                screen.migration_manager.cancel_all.assert_called_once_with(force=True)
                screen.migration_manager.stop.assert_called_once()
    
    def test_handle_cancel_confirmed_navigates_back(self, screen):
        """Test that confirmed cancel navigates to playlist selection."""
        screen.migration_manager = Mock()
        
        with patch.object(screen, 'show_loading'):
            with patch.object(screen, 'navigate_to') as mock_nav:
                screen._handle_cancel_confirmed(Mock())
                
                mock_nav.assert_called_once()
                # Should navigate to PlaylistSelectionScreen
                from src.ui.screens.playlist_selection_screen import PlaylistSelectionScreen
                assert mock_nav.call_args[0][0] == PlaylistSelectionScreen
    
    def test_handle_cancel_confirmed_sets_cancelled_flag(self, screen):
        """Test that cancel sets the cancelled flag."""
        screen.migration_manager = Mock()
        screen.is_cancelled = False
        
        with patch.object(screen, 'show_loading'):
            with patch.object(screen, 'navigate_to'):
                screen._handle_cancel_confirmed(Mock())
                
                assert screen.is_cancelled is True


class TestMigrationProgressScreenMigrationComplete:
    """Test migration completion handling."""
    
    def test_on_migration_complete_stores_results(self, screen):
        """Test that completion stores results in app_state."""
        screen.total_playlists = 5
        screen.total_tracks = 250
        screen.matched_count = 240
        screen.failed_count = 10
        screen.start_time = time.time() - 1800  # 30 minutes ago
        
        with patch.object(screen, 'show_success'):
            screen.on_migration_complete()
            
            assert 'migration_results' in screen.app_state
            results = screen.app_state['migration_results']
            assert results['total_playlists'] == 5
            assert results['total_tracks'] == 250
            assert results['matched_count'] == 240
            assert results['failed_count'] == 10
    
    def test_on_migration_complete_shows_success(self, screen):
        """Test that completion shows success message."""
        screen.total_playlists = 2
        screen.total_tracks = 80
        screen.matched_count = 75
        screen.failed_count = 5
        screen.start_time = time.time()
        
        # Completion stores the results and moves on to the results screen
        with patch.object(screen, 'navigate_to') as mock_navigate:
            screen.on_migration_complete()

            mock_navigate.assert_called_once()
            results = screen.app_state['migration_results']
            assert results['matched_count'] == 75
            assert results['failed_count'] == 5
            assert results['total_tracks'] == 80


class TestMigrationProgressScreenIntegration:
    """Test integrated screen functionality."""
    
    def test_full_progress_flow(self, screen):
        """Test complete progress update flow."""
        screen.build()
        screen.total_tracks = 100
        screen.last_update_time = 0
        
        # Simulate progress updates
        screen.on_progress_update("Playlist 1", 10, 100, "Track 10")
        assert screen.current_track_index == 10
        
        screen.last_update_time = 0
        screen.on_progress_update("Playlist 1", 50, 100, "Track 50")
        assert screen.current_track_index == 50
        
        screen.last_update_time = 0
        screen.on_progress_update("Playlist 1", 100, 100, "Track 100")
        assert screen.current_track_index == 100
    
    def test_pause_resume_flow(self, screen):
        """Test pause and resume flow."""
        screen.build()
        screen.migration_manager = Mock()
        
        # Pause
        screen.on_pause_click(Mock())
        assert screen.is_paused is True
        
        # Resume
        screen.on_pause_click(Mock())
        assert screen.is_paused is False
    
    def test_thread_safety(self, screen):
        """Test that concurrent updates are thread-safe."""
        screen.build()
        screen.total_tracks = 100
        errors = []
        
        def update_progress(n):
            try:
                for i in range(10):
                    screen.last_update_time = 0
                    screen.on_progress_update(f"Playlist {n}", i, 10, f"Track {i}")
                    time.sleep(0.001)
            except Exception as e:
                errors.append(e)
        
        # Create multiple threads updating concurrently
        threads = [threading.Thread(target=update_progress, args=(i,)) for i in range(3)]
        
        for t in threads:
            t.start()
        
        for t in threads:
            t.join()
        
        # Should not have any errors
        assert len(errors) == 0


class TestMigrationProgressScreenEdgeCases:
    """Test edge cases and error handling."""
    
    def test_update_ui_without_page(self, screen):
        """Test that UI update handles missing page gracefully."""
        screen.build()
        screen.page = None
        
        # Should not raise exception
        screen._update_ui()
    
    def test_progress_update_with_zero_total_tracks(self, screen):
        """Test progress update when total tracks is zero."""
        screen.build()
        screen.total_tracks = 0
        screen.last_update_time = 0
        
        # Should not raise division by zero
        screen.on_progress_update("Test", 0, 0, "")
        screen._update_ui()
    
    def test_calculate_time_with_zero_total_tracks(self, screen):
        """Test time calculation with zero total tracks."""
        screen.start_time = time.time()
        screen.total_tracks = 0
        
        result = screen.calculate_estimated_time()
        assert result == "Calculating..."
    
    def test_sync_animation_without_page(self, screen):
        """Test sync animation when component has no page."""
        screen.sync_icon = Mock()
        screen.sync_icon.page = None
        screen.sync_icon.rotate = Mock()
        screen.sync_icon.rotate.angle = 0
        
        # Should not raise exception
        screen._start_sync_animation()


class TestMigrationProgressScreenAppStateWiring:
    """The manager must be published to app_state so main.py's background
    survival (close-with-job + sleep inhibition) can detect an active job.
    See CONTEXT_CONTRACT §4.3."""

    def test_start_migration_publishes_manager_to_app_state(self, screen, app_state):
        import asyncio

        assert app_state.get('migration_manager') is None

        fake_manager = Mock()
        fake_manager.migrate_playlists.return_value = ['job1']

        with patch(
            'src.ui.screens.migration_progress_screen.MigrationManager',
            return_value=fake_manager,
        ):
            screen.show_loading = Mock()
            screen.show_error = Mock()
            asyncio.run(screen.start_migration())

        # The exact instance the screen created is exposed under the key that
        # is_migration_active() / SleepGuard read in main.py.
        assert app_state['migration_manager'] is fake_manager
        assert screen.migration_manager is fake_manager


# ---------------------------------------------------------------------------
# Multi-playlist completion + waiting-state visibility (CONTEXT_CONTRACT §4.3,
# "multi-playlist completion"; §1 seamless status). The screen drives the
# overall bar and the done decision from MigrationManager.get_batch_progress()
# over this run's job rows, never from one playlist's track index.
# ---------------------------------------------------------------------------

def _job(name, status, processed, total, matched, failed, ids=None, error=None):
    return {
        'job_id': f'job-{name}',
        'playlist_name': name,
        'status': status,
        'processed_tracks': processed,
        'total_tracks': total,
        'matched_tracks': matched,
        'failed_tracks': failed,
        'youtube_playlist_ids': list(ids or []),
        'error_message': error,
    }


def _batch(jobs, throttle=None):
    completed = sum(1 for j in jobs if j['status'] == 'completed')
    failed = sum(1 for j in jobs if j['status'] == 'failed')
    paused = sum(1 for j in jobs if j['status'] == 'paused_auth')
    return {
        'total_jobs': len(jobs),
        'completed_jobs': completed,
        'failed_jobs': failed,
        'in_progress_jobs': sum(1 for j in jobs if j['status'] == 'in_progress'),
        'queued_jobs': sum(1 for j in jobs if j['status'] == 'queued'),
        'paused_auth_jobs': paused,
        'processed_tracks': sum(
            j['total_tracks'] if j['status'] == 'completed' else j['processed_tracks']
            for j in jobs
        ),
        'total_tracks': sum(j['total_tracks'] for j in jobs),
        'matched_tracks': sum(j['matched_tracks'] for j in jobs),
        'failed_tracks': sum(j['failed_tracks'] for j in jobs),
        'playlists_created': sum(len(j['youtube_playlist_ids']) for j in jobs),
        'all_done': bool(jobs) and completed + failed == len(jobs),
        'auth_required': paused > 0,
        'throttle': throttle or {'throttled': False, 'reason': None, 'until': None, 'message': ''},
        'jobs': jobs,
    }


def _status(auth_required=False, throttle=None):
    return {
        'total_jobs': 2, 'completed_jobs': 0, 'failed_jobs': 0, 'queued_jobs': 0,
        'in_progress_jobs': 1, 'current_job': None, 'queue_size': 0,
        'is_paused': False, 'error_count': 0, 'is_running': True,
        'throttle': throttle or {'throttled': False, 'reason': None, 'until': None, 'message': ''},
        'paused_auth_jobs': 1 if auth_required else 0,
        'auth_required': auth_required,
    }


@pytest.fixture
def polling_screen(screen):
    """A built screen wired to a mocked MigrationManager with two jobs."""
    screen.build()
    screen.page.update = Mock()
    screen.migration_manager = Mock()
    screen.job_ids = ['job-Rock Classics', 'job-Pop Hits']
    screen.start_time = time.time() - 60
    screen.total_playlists = 2
    # Never let the real timers fire in tests
    screen._schedule_poll = Mock()
    return screen


class TestMultiPlaylistCompletion:

    def test_mid_run_two_playlists_is_not_complete_and_bar_is_overall(self, polling_screen):
        s = polling_screen
        jobs = [
            _job('Rock Classics', 'completed', 50, 50, 48, 2, ids=['yt1']),
            _job('Pop Hits', 'in_progress', 10, 30, 9, 1, ids=['yt2']),
        ]
        s.migration_manager.get_batch_progress.return_value = _batch(jobs)
        s.migration_manager.get_migration_status.return_value = _status()

        done = s.refresh_from_manager()

        assert done is False
        assert s.total_tracks == 80
        assert s.processed_tracks == 60
        assert s.matched_count == 57
        assert s.failed_count == 3
        # 60/80 = 75% overall, not 10/30 of the current playlist
        assert s.progress_bar.value == 0.75
        assert "75%" in s.progress_bar.text_label.value
        # Current playlist is the running one (index 1 -> "2 of 2")
        assert "Playlist 2 of 2: Pop Hits" in s.playlist_text.value
        assert "across 2 playlists" in s.overall_text.value
        assert s.wait_banner_holder.visible is False
        s.migration_manager.get_batch_progress.assert_called_once_with(s.job_ids)

    def test_two_playlists_all_done_navigates_to_results_with_aggregates(self, polling_screen):
        s = polling_screen
        jobs = [
            _job('Rock Classics', 'completed', 50, 50, 48, 2, ids=['yt1']),
            _job('Pop Hits', 'completed', 30, 30, 30, 0, ids=['yt2a', 'yt2b']),
        ]
        s.migration_manager.get_batch_progress.return_value = _batch(jobs)
        s.migration_manager.get_migration_status.return_value = _status()

        assert s.refresh_from_manager() is True
        assert s.progress_bar.value == 1.0

        with patch.object(s, 'navigate_to') as nav:
            s.on_migration_complete(batch=s.last_batch)

            from src.ui.screens.results_screen import ResultsScreen
            nav.assert_called_once()
            assert nav.call_args[0][0] == ResultsScreen

        r = s.app_state['migration_results']
        assert r['total_playlists'] == 2
        assert r['total_tracks'] == 80
        assert r['matched_count'] == 78
        assert r['failed_count'] == 2
        assert r['playlists_created'] == 3   # one playlist was sharded
        assert r['failed_playlists'] == 0
        assert r['duration'] > 0

        per = s.app_state['playlist_results']
        assert [p['name'] for p in per] == ['Rock Classics', 'Pop Hits']
        assert per[0]['matched_tracks'] == 48 and per[0]['failed_count'] == 2
        assert per[0]['youtube_playlist_url'].endswith('list=yt1')
        assert per[1]['shard_count'] == 2

    def test_poll_cycle_finishes_once_all_jobs_terminal(self, polling_screen):
        """Simulate the poll: progress, progress, then all done -> _finish."""
        s = polling_screen
        running = _batch([
            _job('Rock Classics', 'in_progress', 20, 50, 19, 1),
            _job('Pop Hits', 'queued', 0, 30, 0, 0),
        ])
        done = _batch([
            _job('Rock Classics', 'completed', 50, 50, 48, 2, ids=['a']),
            _job('Pop Hits', 'failed', 12, 30, 11, 1, ids=['b'], error='boom'),
        ])
        s.migration_manager.get_batch_progress.side_effect = [running, running, done]
        s.migration_manager.get_migration_status.return_value = _status()

        with patch.object(s, '_finish') as finish:
            s._poll_status()
            s._poll_status()
            assert finish.call_count == 0
            assert s._schedule_poll.call_count == 2
            s._poll_status()
            finish.assert_called_once()
            # A failed playlist still counts as terminal: the batch is done
            assert finish.call_args[0][0]['all_done'] is True

    def test_finish_schedules_completion_and_stops_polling(self, polling_screen):
        s = polling_screen
        with patch('src.ui.screens.migration_progress_screen.threading.Timer') as timer_cls:
            s._finish({'all_done': True, 'jobs': []})
            timer_cls.assert_called_once()
            assert timer_cls.call_args[0][1] == s.on_migration_complete
            timer_cls.return_value.start.assert_called_once()
        assert s.is_complete is True
        # Second call is a no-op
        with patch('src.ui.screens.migration_progress_screen.threading.Timer') as timer_cls:
            s._finish({'all_done': True, 'jobs': []})
            timer_cls.assert_not_called()

    def test_single_playlist_still_completes(self, polling_screen):
        s = polling_screen
        s.job_ids = ['job-Only']
        s.total_playlists = 1
        jobs = [_job('Only', 'completed', 14, 14, 14, 0, ids=['yt'])]
        s.migration_manager.get_batch_progress.return_value = _batch(jobs)
        s.migration_manager.get_migration_status.return_value = _status()

        assert s.refresh_from_manager() is True
        assert s.progress_bar.value == 1.0
        assert s.playlist_text.value == "Only"          # no "1 of 1" prefix
        assert s.track_text.value == "Track 14 of 14"

        with patch.object(s, 'navigate_to') as nav:
            s.on_migration_complete(batch=s.last_batch)
            nav.assert_called_once()
        assert s.app_state['migration_results']['total_tracks'] == 14
        assert s.app_state['migration_results']['matched_count'] == 14

    def test_per_track_callback_never_completes_the_batch(self, polling_screen):
        """The per-playlist index reaching the global total must not finish."""
        s = polling_screen
        s.total_tracks = 80
        s.last_update_time = 0
        with patch.object(s, 'on_migration_complete') as complete, \
             patch.object(s, '_finish') as finish:
            s.on_progress_update("Rock Classics", 80, 80, "Last song")
            time.sleep(0.05)
            complete.assert_not_called()
            finish.assert_not_called()
        assert s.track_text.value == "Track 80 of 80"

    def test_on_migration_complete_without_batch_uses_screen_counters(self, screen):
        screen.total_playlists = 1
        screen.total_tracks = 12
        screen.matched_count = 12
        screen.failed_count = 0
        screen.start_time = time.time()
        with patch.object(screen, 'navigate_to'):
            screen.on_migration_complete()
        assert screen.app_state['migration_results']['matched_count'] == 12
        assert screen.app_state['playlist_results'] == []

    def test_cancelled_screen_ignores_completion(self, polling_screen):
        s = polling_screen
        s.is_cancelled = True
        with patch.object(s, 'navigate_to') as nav:
            s.on_migration_complete(batch=_batch([_job('A', 'completed', 1, 1, 1, 0)]))
            nav.assert_not_called()

    def test_start_migration_begins_polling_and_handles_empty_queue(self, screen, app_state):
        import asyncio
        fake_manager = Mock()
        fake_manager.migrate_playlists.return_value = ['j1', 'j2']
        with patch('src.ui.screens.migration_progress_screen.MigrationManager',
                   return_value=fake_manager):
            screen.show_loading = Mock()
            screen.show_error = Mock()
            screen._schedule_poll = Mock()
            asyncio.run(screen.start_migration())
        assert screen.job_ids == ['j1', 'j2']
        assert app_state['migration_job_ids'] == ['j1', 'j2']
        screen._schedule_poll.assert_called_once()
        screen.show_error.assert_not_called()

        # Nothing queued (all playlists empty): tell the user, don't poll
        screen2 = MigrationProgressScreen(screen.page, dict(app_state))
        fake_manager.migrate_playlists.return_value = []
        with patch('src.ui.screens.migration_progress_screen.MigrationManager',
                   return_value=fake_manager):
            screen2.show_loading = Mock()
            screen2.show_error = Mock()
            screen2._schedule_poll = Mock()
            asyncio.run(screen2.start_migration())
        screen2.show_error.assert_called_once()
        screen2._schedule_poll.assert_not_called()


class TestWaitingStateBanners:

    def test_paused_auth_shows_reconnect_banner_and_is_not_complete(self, polling_screen):
        s = polling_screen
        jobs = [
            _job('Rock Classics', 'completed', 50, 50, 48, 2, ids=['yt1']),
            _job('Pop Hits', 'paused_auth', 10, 30, 9, 1, ids=['yt2'],
                 error='YouTube Music sign-in expired - reconnect to resume'),
        ]
        s.migration_manager.get_batch_progress.return_value = _batch(jobs)
        s.migration_manager.get_migration_status.return_value = _status(auth_required=True)

        done = s.refresh_from_manager()

        assert done is False
        assert s.is_complete is False
        assert s.wait_banner_holder.visible is True
        banner = s.wait_banner_holder.content
        from src.ui.components import StatusBanner
        assert isinstance(banner, StatusBanner)
        assert "sign-in expired" in banner.message
        assert "reconnect" in banner.message.lower()
        assert banner.banner_type == "error"
        # Non-technical: no jargon in what the user sees
        for word in ("401", "403", "token", "cookie", "SAPISID", "header", "json"):
            assert word.lower() not in banner.message.lower()
        assert "reconnect" in s.time_text.value.lower()
        # The paused playlist is the "current" one
        assert "Pop Hits" in s.playlist_text.value

    def test_throttled_shows_waiting_until_banner_and_is_not_complete(self, polling_screen):
        s = polling_screen
        from datetime import datetime
        until = time.time() + 15 * 60
        expected_hhmm = datetime.fromtimestamp(until).strftime('%H:%M')
        throttle = {'throttled': True, 'reason': 'rate', 'until': until,
                    'message': 'Rate limited by YouTube Music'}
        jobs = [
            _job('Rock Classics', 'in_progress', 20, 50, 19, 1),
            _job('Pop Hits', 'queued', 0, 30, 0, 0),
        ]
        s.migration_manager.get_batch_progress.return_value = _batch(jobs, throttle=throttle)
        s.migration_manager.get_migration_status.return_value = _status(throttle=throttle)

        assert s.refresh_from_manager() is False
        assert s.wait_banner_holder.visible is True
        banner = s.wait_banner_holder.content
        assert banner.message.startswith("Waiting")
        assert f"throttled until {expected_hhmm}" in banner.message
        assert banner.banner_type == "warning"

    def test_throttled_without_until_falls_back_to_message(self, screen):
        text = screen._throttle_message({'throttled': True, 'until': None,
                                         'message': 'slowing down for a moment'})
        assert text == "Waiting — slowing down for a moment"
        text = screen._throttle_message({'throttled': True, 'until': None, 'message': ''})
        assert text.startswith("Waiting")

    def test_auth_banner_takes_precedence_over_throttle(self, polling_screen):
        s = polling_screen
        throttle = {'throttled': True, 'reason': 'rate', 'until': time.time() + 60, 'message': 'x'}
        jobs = [_job('A', 'paused_auth', 1, 10, 1, 0)]
        s.migration_manager.get_batch_progress.return_value = _batch(jobs, throttle=throttle)
        s.migration_manager.get_migration_status.return_value = _status(auth_required=True, throttle=throttle)
        s.refresh_from_manager()
        assert s.wait_banner_kind == 'auth'

    def test_banner_clears_on_refresh_when_state_recovers(self, polling_screen):
        s = polling_screen
        jobs = [_job('A', 'paused_auth', 1, 10, 1, 0)]
        s.migration_manager.get_batch_progress.return_value = _batch(jobs)
        s.migration_manager.get_migration_status.return_value = _status(auth_required=True)
        s.refresh_from_manager()
        assert s.wait_banner_holder.visible is True

        # Reconnected: job back in progress on the next poll
        jobs = [_job('A', 'in_progress', 4, 10, 4, 0)]
        s.migration_manager.get_batch_progress.return_value = _batch(jobs)
        s.migration_manager.get_migration_status.return_value = _status()
        s.refresh_from_manager()
        assert s.wait_banner_holder.visible is False
        assert s.wait_banner_holder.content is None
        assert s.time_text.value.startswith("Estimated time")

    def test_banner_is_rebuilt_only_on_change(self, polling_screen):
        s = polling_screen
        jobs = [_job('A', 'paused_auth', 1, 10, 1, 0)]
        s.migration_manager.get_batch_progress.return_value = _batch(jobs)
        s.migration_manager.get_migration_status.return_value = _status(auth_required=True)
        s.refresh_from_manager()
        first = s.wait_banner_holder.content
        s.refresh_from_manager()
        assert s.wait_banner_holder.content is first

    def test_refresh_without_manager_or_jobs_is_a_noop(self, screen):
        assert screen.refresh_from_manager() is False
        screen.migration_manager = Mock()
        assert screen.refresh_from_manager() is False
        screen.migration_manager.get_batch_progress.assert_not_called()
