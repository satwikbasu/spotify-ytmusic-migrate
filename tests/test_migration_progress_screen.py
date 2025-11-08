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
        
        screen.on_progress_update(
            playlist_name="Rock Classics",
            current=20,
            total=50,
            track_name="Test Track"
        )
        
        # Should have some matched and failed counts
        assert screen.matched_count > 0
        assert screen.matched_count + screen.failed_count == 19  # current - 1
    
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
        screen.current_track_index = 40
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
        
        with patch.object(screen, 'show_success') as mock_success:
            screen.on_migration_complete()
            
            mock_success.assert_called_once()
            # Check message contains stats
            message = mock_success.call_args[0][0]
            assert "75" in message
            assert "80" in message


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
