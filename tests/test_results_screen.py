"""Tests for ResultsScreen."""

import pytest
from unittest.mock import Mock, patch, MagicMock, mock_open
import tempfile
import os
import csv

from src.ui.screens.results_screen import ResultsScreen
import flet as ft


@pytest.fixture
def mock_page():
    """Create a mock Flet page."""
    page = Mock(spec=ft.Page)
    page.controls = Mock()
    page.overlay = []
    page.update = Mock()
    page.add = Mock()
    return page


@pytest.fixture
def app_state_simple():
    """Create simple app state with minimal results."""
    return {
        'migration_results': {
            'total_playlists': 2,
            'total_tracks': 100,
            'matched_count': 95,
            'failed_count': 5,
            'duration': 600  # 10 minutes
        }
    }


@pytest.fixture
def app_state_detailed():
    """Create app state with detailed playlist results."""
    return {
        'migration_results': {
            'total_playlists': 2,
            'total_tracks': 100,
            'matched_count': 95,
            'failed_count': 5,
            'duration': 2520  # 42 minutes
        },
        'playlist_results': [
            {
                'name': 'Rock Classics',
                'total_tracks': 50,
                'matched_tracks': 48,
                'failed_tracks': [
                    {
                        'name': 'Unknown Track',
                        'artist': 'Unknown Artist',
                        'id': 'abc123',
                        'failure_reason': 'No match found'
                    },
                    {
                        'name': 'Rare Song',
                        'artist': 'Indie Band',
                        'id': 'def456',
                        'failure_reason': 'Low confidence'
                    }
                ],
                'youtube_playlist_url': 'https://music.youtube.com/playlist?list=xyz'
            },
            {
                'name': 'Pop Hits',
                'total_tracks': 50,
                'matched_tracks': 47,
                'failed_tracks': [
                    {
                        'name': 'Foreign Song',
                        'artist': 'Foreign Artist',
                        'id': 'ghi789',
                        'failure_reason': 'Region restricted'
                    }
                ],
                'youtube_playlist_url': 'https://music.youtube.com/playlist?list=abc'
            }
        ]
    }


@pytest.fixture
def screen_simple(mock_page, app_state_simple):
    """Create a ResultsScreen with simple results."""
    return ResultsScreen(mock_page, app_state_simple)


@pytest.fixture
def screen_detailed(mock_page, app_state_detailed):
    """Create a ResultsScreen with detailed results."""
    return ResultsScreen(mock_page, app_state_detailed)


class TestResultsScreenInitialization:
    """Test screen initialization."""
    
    def test_init_creates_screen(self, mock_page, app_state_simple):
        """Test that screen can be instantiated."""
        screen = ResultsScreen(mock_page, app_state_simple)
        assert screen is not None
        assert screen.page == mock_page
        assert screen.app_state == app_state_simple
    
    def test_init_extracts_results(self, screen_simple):
        """Test that initialization extracts results from app_state."""
        assert screen_simple.total_playlists == 2
        assert screen_simple.total_tracks == 100
        assert screen_simple.matched_count == 95
        assert screen_simple.failed_count == 5
        assert screen_simple.duration == 600
    
    def test_init_calculates_success_rate(self, screen_simple):
        """Test that success rate is calculated correctly."""
        assert screen_simple.success_rate == 0.95
    
    def test_init_with_detailed_results(self, screen_detailed):
        """Test initialization with detailed playlist results."""
        assert len(screen_detailed.results) == 2
        assert screen_detailed.results[0]['name'] == 'Rock Classics'
        assert screen_detailed.results[1]['name'] == 'Pop Hits'
    
    def test_init_without_results(self, mock_page):
        """Test initialization with empty app_state."""
        screen = ResultsScreen(mock_page, {})
        assert screen.total_playlists == 0
        assert screen.total_tracks == 0
        assert screen.matched_count == 0
        assert screen.failed_count == 0
        assert screen.success_rate == 0.0


class TestResultsScreenBuild:
    """Test screen build method."""
    
    def test_build_returns_control(self, screen_simple):
        """Test that build returns a Flet control."""
        content = screen_simple.build()
        assert content is not None
        assert isinstance(content, ft.Control)
    
    def test_build_creates_file_picker(self, screen_simple):
        """Test that build creates file picker."""
        screen_simple.build()
        assert screen_simple.file_picker is not None
        assert screen_simple.file_picker in screen_simple.page.overlay
    
    def test_build_with_detailed_results(self, screen_detailed):
        """Test build with detailed playlist results."""
        content = screen_detailed.build()
        assert content is not None


class TestResultsScreenSummaryCard:
    """Test summary card building."""
    
    def test_build_summary_card_creates_card(self, screen_simple):
        """Test that summary card is created."""
        card = screen_simple._build_summary_card()
        assert card is not None
        assert isinstance(card, ft.Card)
    
    def test_format_duration_seconds(self, screen_simple):
        """Test duration formatting for seconds."""
        result = screen_simple._format_duration(45)
        assert "45 seconds" in result
    
    def test_format_duration_minutes(self, screen_simple):
        """Test duration formatting for minutes."""
        result = screen_simple._format_duration(600)
        assert "10 minutes" in result
    
    def test_format_duration_single_minute(self, screen_simple):
        """Test duration formatting for single minute."""
        result = screen_simple._format_duration(60)
        assert "1 minute" in result
        assert "minutes" not in result
    
    def test_format_duration_hours(self, screen_simple):
        """Test duration formatting for hours."""
        result = screen_simple._format_duration(7200)
        assert "2 hours" in result
    
    def test_format_duration_hours_and_minutes(self, screen_simple):
        """Test duration formatting for hours and minutes."""
        result = screen_simple._format_duration(7320)  # 2 hours 2 minutes
        assert "2 hours" in result
        assert "2 minutes" in result


class TestResultsScreenResultsList:
    """Test results list building."""
    
    def test_build_results_list_without_results(self, screen_simple):
        """Test building results list with no detailed results."""
        results_list = screen_simple._build_results_list()
        assert results_list is not None
    
    def test_build_results_list_with_results(self, screen_detailed):
        """Test building results list with detailed results."""
        results_list = screen_detailed._build_results_list()
        assert results_list is not None
    
    def test_build_playlist_result_card(self, screen_detailed):
        """Test building a single playlist result card."""
        result = screen_detailed.results[0]
        card = screen_detailed._build_playlist_result_card(result)
        assert card is not None
        assert isinstance(card, ft.Card)
    
    def test_build_playlist_result_card_with_failures(self, screen_detailed):
        """Test building card for playlist with failed tracks."""
        result = screen_detailed.results[0]  # Has 2 failed tracks
        card = screen_detailed._build_playlist_result_card(result)
        assert card is not None
    
    def test_build_playlist_result_card_without_url(self, screen_detailed):
        """Test building card for playlist without YouTube URL."""
        result = {
            'name': 'Test Playlist',
            'total_tracks': 10,
            'matched_tracks': 10,
            'failed_tracks': []
        }
        card = screen_detailed._build_playlist_result_card(result)
        assert card is not None


class TestResultsScreenActionButtons:
    """Test action buttons building."""
    
    def test_build_action_buttons_creates_buttons(self, screen_simple):
        """Test that action buttons are created."""
        buttons = screen_simple._build_action_buttons()
        assert buttons is not None


class TestResultsScreenFailedTracks:
    """Test failed tracks modal."""
    
    def test_on_view_failed_tracks_click_shows_dialog(self, screen_detailed):
        """Test that viewing failed tracks shows dialog."""
        result = screen_detailed.results[0]
        
        screen_detailed.on_view_failed_tracks_click(result)
        
        # Should add dialog to overlay
        assert len(screen_detailed.page.overlay) > 0
    
    def test_on_view_failed_tracks_click_with_empty_list(self, screen_detailed):
        """Test viewing failed tracks with empty list."""
        result = {
            'name': 'Test',
            'failed_tracks': []
        }
        
        # Should not raise exception
        screen_detailed.on_view_failed_tracks_click(result)
    
    def test_close_dialog(self, screen_detailed):
        """Test closing a dialog."""
        dialog = ft.AlertDialog()
        dialog.open = True
        
        screen_detailed._close_dialog(dialog)
        
        assert dialog.open is False


class TestResultsScreenBrowserOpening:
    """Test browser opening functionality."""
    
    def test_on_open_playlist_click(self, screen_simple):
        """Test opening playlist in browser."""
        with patch('webbrowser.open') as mock_open:
            screen_simple.on_open_playlist_click('https://music.youtube.com/test')
            
            mock_open.assert_called_once_with('https://music.youtube.com/test')
    
    def test_on_open_playlist_click_error(self, screen_simple):
        """Test error handling when opening playlist fails."""
        with patch('webbrowser.open', side_effect=Exception("Browser error")):
            with patch.object(screen_simple, 'show_error') as mock_error:
                screen_simple.on_open_playlist_click('https://test.com')
                
                mock_error.assert_called_once()
    
    def test_on_open_youtube_music_click(self, screen_simple):
        """Test opening YouTube Music library."""
        with patch('webbrowser.open') as mock_open:
            screen_simple.on_open_youtube_music_click()
            
            mock_open.assert_called_once_with('https://music.youtube.com/library')
    
    def test_on_open_youtube_music_click_error(self, screen_simple):
        """Test error handling when opening YouTube Music fails."""
        with patch('webbrowser.open', side_effect=Exception("Browser error")):
            with patch.object(screen_simple, 'show_error') as mock_error:
                screen_simple.on_open_youtube_music_click()
                
                mock_error.assert_called_once()


class TestResultsScreenExport:
    """Test CSV export functionality."""
    
    def test_on_export_report_click(self, screen_simple):
        """Test export report button click."""
        screen_simple.build()  # Initialize file picker
        
        with patch.object(screen_simple.file_picker, 'save_file') as mock_save:
            screen_simple.on_export_report_click(Mock())
            
            mock_save.assert_called_once()
    
    def test_on_export_report_click_without_file_picker(self, screen_simple):
        """Test export when file picker not initialized."""
        screen_simple.file_picker = None
        
        with patch.object(screen_simple, 'show_error') as mock_error:
            screen_simple.on_export_report_click(Mock())
            
            mock_error.assert_called_once()
    
    def test_handle_file_picker_result_with_path(self, screen_detailed):
        """Test handling file picker result with valid path."""
        event = Mock()
        event.path = '/tmp/test_report.csv'
        
        with patch.object(screen_detailed, '_export_csv_report') as mock_export:
            with patch.object(screen_detailed, 'show_success') as mock_success:
                screen_detailed._handle_file_picker_result(event)
                
                mock_export.assert_called_once_with('/tmp/test_report.csv')
                mock_success.assert_called_once()
    
    def test_handle_file_picker_result_without_path(self, screen_simple):
        """Test handling file picker result with no path (cancelled)."""
        event = Mock()
        event.path = None
        
        with patch.object(screen_simple, '_export_csv_report') as mock_export:
            screen_simple._handle_file_picker_result(event)
            
            # Should not call export
            mock_export.assert_not_called()
    
    def test_handle_file_picker_result_error(self, screen_simple):
        """Test handling file picker result with export error."""
        event = Mock()
        event.path = '/tmp/test.csv'
        
        with patch.object(screen_simple, '_export_csv_report', side_effect=Exception("Write error")):
            with patch.object(screen_simple, 'show_error') as mock_error:
                screen_simple._handle_file_picker_result(event)
                
                mock_error.assert_called_once()
    
    def test_export_csv_report(self, screen_detailed):
        """Test CSV export with detailed results."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv') as f:
            temp_path = f.name
        
        try:
            # Add detailed track info to results
            screen_detailed.results[0]['matched_tracks_details'] = [
                {
                    'name': 'Track 1',
                    'artist': 'Artist 1',
                    'id': 'sp1',
                    'youtube_video_id': 'yt1',
                    'confidence': 95.5
                }
            ]
            
            screen_detailed._export_csv_report(temp_path)
            
            # Verify file was created and contains expected data
            assert os.path.exists(temp_path)
            
            with open(temp_path, 'r', encoding='utf-8') as csvfile:
                reader = csv.reader(csvfile)
                rows = list(reader)
                
                # Should have header + data rows
                assert len(rows) > 1
                assert rows[0][0] == 'Playlist Name'
                assert rows[0][6] == 'Status'
        
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
    
    def test_export_csv_report_with_failed_tracks(self, screen_detailed):
        """Test CSV export includes failed tracks."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv') as f:
            temp_path = f.name
        
        try:
            screen_detailed._export_csv_report(temp_path)
            
            with open(temp_path, 'r', encoding='utf-8') as csvfile:
                reader = csv.reader(csvfile)
                rows = list(reader)
                
                # Should have failed track entries
                failed_rows = [r for r in rows if r[6] == 'Failed']
                assert len(failed_rows) == 3  # 2 + 1 from two playlists
        
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)


class TestResultsScreenNavigation:
    """Test navigation functionality."""
    
    def test_on_migrate_more_click_clears_state(self, screen_simple):
        """Test that migrate more clears app_state."""
        screen_simple.app_state['selected_playlists'] = [{'id': '1'}]
        screen_simple.app_state['migration_results'] = {'test': 'data'}
        screen_simple.app_state['playlist_results'] = [{}]
        
        with patch.object(screen_simple, 'navigate_to') as mock_nav:
            screen_simple.on_migrate_more_click(Mock())
            
            assert screen_simple.app_state.get('selected_playlists') == []
            assert 'migration_results' not in screen_simple.app_state
            assert 'playlist_results' not in screen_simple.app_state
    
    def test_on_migrate_more_click_navigates(self, screen_simple):
        """Test that migrate more navigates to playlist selection."""
        with patch.object(screen_simple, 'navigate_to') as mock_nav:
            screen_simple.on_migrate_more_click(Mock())
            
            mock_nav.assert_called_once()
            from src.ui.screens.playlist_selection_screen import PlaylistSelectionScreen
            assert mock_nav.call_args[0][0] == PlaylistSelectionScreen


class TestResultsScreenCelebration:
    """Test celebration animation."""
    
    def test_show_celebration(self, screen_simple):
        """Test that celebration can be shown without errors."""
        # Currently a no-op, but should not raise exception
        screen_simple.show_celebration()


class TestResultsScreenIntegration:
    """Test integrated screen functionality."""
    
    def test_full_build_and_display(self, screen_detailed):
        """Test complete build process."""
        content = screen_detailed.build()
        
        assert content is not None
        assert screen_detailed.file_picker is not None
        assert len(screen_detailed.page.overlay) > 0
    
    def test_export_and_open_flow(self, screen_detailed):
        """Test export report and open playlist flow."""
        screen_detailed.build()
        
        # Mock file picker result
        event = Mock()
        event.path = '/tmp/test.csv'
        
        with patch.object(screen_detailed, '_export_csv_report'):
            with patch.object(screen_detailed, 'show_success'):
                with patch('webbrowser.open'):
                    # Export report
                    screen_detailed._handle_file_picker_result(event)
                    
                    # Open playlist
                    screen_detailed.on_open_playlist_click('https://test.com')


class TestResultsScreenEdgeCases:
    """Test edge cases and error handling."""
    
    def test_zero_tracks(self, mock_page):
        """Test screen with zero tracks."""
        app_state = {
            'migration_results': {
                'total_playlists': 0,
                'total_tracks': 0,
                'matched_count': 0,
                'failed_count': 0,
                'duration': 0
            }
        }
        screen = ResultsScreen(mock_page, app_state)
        
        assert screen.success_rate == 0.0
        content = screen.build()
        assert content is not None
    
    def test_all_tracks_failed(self, mock_page):
        """Test screen with all tracks failed."""
        app_state = {
            'migration_results': {
                'total_playlists': 1,
                'total_tracks': 10,
                'matched_count': 0,
                'failed_count': 10,
                'duration': 100
            }
        }
        screen = ResultsScreen(mock_page, app_state)
        
        assert screen.success_rate == 0.0
        content = screen.build()
        assert content is not None
    
    def test_missing_playlist_fields(self, screen_detailed):
        """Test handling playlists with missing fields."""
        incomplete_result = {
            'name': 'Test'
            # Missing other fields
        }
        
        card = screen_detailed._build_playlist_result_card(incomplete_result)
        assert card is not None


class TestAggregateResultsShape:
    """The progress screen hands over count-only per-playlist results (per-track
    detail is not persisted) plus shard / failed-playlist totals. The Results
    screen must render that shape without a failed_tracks list."""

    def _page(self):
        page = Mock(spec=ft.Page)
        page.overlay = []
        page.update = Mock()
        return page

    def test_renders_count_only_failures_and_shards(self):
        app_state = {
            'migration_results': {
                'total_playlists': 2, 'total_tracks': 80, 'matched_count': 78,
                'failed_count': 2, 'playlists_created': 3, 'failed_playlists': 1,
                'duration': 120,
            },
            'playlist_results': [
                {'name': 'Rock', 'status': 'completed', 'total_tracks': 50,
                 'matched_tracks': 48, 'failed_count': 2, 'failed_tracks': [],
                 'youtube_playlist_ids': ['a'], 'shard_count': 1,
                 'youtube_playlist_url': 'https://music.youtube.com/playlist?list=a'},
                {'name': 'Pop', 'status': 'failed', 'total_tracks': 30,
                 'matched_tracks': 30, 'failed_count': 0, 'failed_tracks': [],
                 'youtube_playlist_ids': ['b', 'c'], 'shard_count': 2,
                 'youtube_playlist_url': 'https://music.youtube.com/playlist?list=b'},
            ],
        }
        screen = ResultsScreen(self._page(), app_state)
        content = screen.build()
        assert content is not None
        assert screen.playlists_created == 3
        assert screen.failed_playlists == 1

        card = screen._build_playlist_result_card(app_state['playlist_results'][1])
        texts = []

        def walk(c):
            if hasattr(c, 'value') and isinstance(getattr(c, 'value'), str):
                texts.append(c.value)
            for attr in ('content', 'controls'):
                child = getattr(c, attr, None)
                if child is None:
                    continue
                for item in (child if isinstance(child, list) else [child]):
                    walk(item)
        walk(card)
        joined = " | ".join(texts)
        assert "split into 2 playlists" in joined
        assert "stopped early" in joined
        # No "View N failed" button when there is no per-track list
        assert "View" not in joined
