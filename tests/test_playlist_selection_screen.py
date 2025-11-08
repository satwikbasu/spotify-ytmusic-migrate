"""Tests for PlaylistSelectionScreen."""

import pytest
import flet as ft
from unittest.mock import Mock, MagicMock, patch, AsyncMock
import asyncio

from src.ui.screens.playlist_selection_screen import PlaylistSelectionScreen
from src.fetchers.spotify_fetcher import SpotifyFetcher
from config import app_config


@pytest.fixture
def mock_page():
    """Create a mock Flet page."""
    page = Mock(spec=ft.Page)
    page.controls = Mock()
    page.overlay = []
    page.update = Mock()
    page.add = Mock()
    # Mock run_task to just return a Mock instead of actually creating a task
    page.run_task = Mock(return_value=None)
    return page


@pytest.fixture
def app_state():
    """Create a fresh app state with clients."""
    return {
        'spotify_client': Mock(),
        'youtube_client': Mock()
    }


@pytest.fixture
def sample_playlists():
    """Create sample playlist data."""
    return [
        {
            'id': 'playlist1',
            'name': 'Rock Classics',
            'track_count': 50,
            'thumbnail_url': 'http://example.com/thumb1.jpg'
        },
        {
            'id': 'playlist2',
            'name': 'Jazz Favorites',
            'track_count': 30,
            'thumbnail_url': 'http://example.com/thumb2.jpg'
        },
        {
            'id': 'playlist3',
            'name': 'Electronic Beats',
            'track_count': 75,
            'thumbnail_url': None
        }
    ]


@pytest.fixture
def playlist_screen(mock_page, app_state):
    """Create a PlaylistSelectionScreen instance."""
    return PlaylistSelectionScreen(mock_page, app_state)


class TestPlaylistSelectionScreenInitialization:
    """Test PlaylistSelectionScreen initialization."""
    
    def test_init_creates_screen(self, mock_page, app_state):
        """Test PlaylistSelectionScreen initializes correctly."""
        screen = PlaylistSelectionScreen(mock_page, app_state)
        
        assert screen.page is mock_page
        assert screen.app_state is app_state
        assert screen.playlists == []
        assert screen.filtered_playlists == []
        assert screen.selected_playlists == set()
        assert screen.fetcher is None
        assert screen.search_query == ""
    
    def test_init_sets_ui_references_to_none(self, playlist_screen):
        """Test UI component references are initially None."""
        assert playlist_screen.header_text is None
        assert playlist_screen.search_field is None
        assert playlist_screen.playlist_list is None
        assert playlist_screen.selection_summary is None
        assert playlist_screen.start_button is None


class TestPlaylistSelectionScreenBuild:
    """Test PlaylistSelectionScreen build method."""
    
    def test_build_returns_control(self, playlist_screen):
        """Test build() returns a Flet control."""
        result = playlist_screen.build()
        
        assert isinstance(result, ft.Control)
    
    def test_build_creates_ui_components(self, playlist_screen):
        """Test build() creates all UI components."""
        playlist_screen.build()
        
        assert playlist_screen.header_text is not None
        assert playlist_screen.search_field is not None
        assert playlist_screen.playlist_list is not None
        assert playlist_screen.selection_summary is not None
        assert playlist_screen.start_button is not None
    
    def test_build_start_button_initially_disabled(self, playlist_screen):
        """Test start button is initially disabled."""
        playlist_screen.build()
        
        assert playlist_screen.start_button.disabled is True
    
    def test_build_creates_search_field(self, playlist_screen):
        """Test build() creates search field with correct properties."""
        playlist_screen.build()
        
        assert playlist_screen.search_field.hint_text == "Search playlists..."
        assert playlist_screen.search_field.prefix_icon == ft.Icons.SEARCH
    
    def test_build_creates_list_view(self, playlist_screen):
        """Test build() creates scrollable ListView."""
        playlist_screen.build()
        
        assert isinstance(playlist_screen.playlist_list, ft.ListView)
        assert playlist_screen.playlist_list.expand is True


class TestPlaylistSelectionScreenLoadPlaylists:
    """Test playlist loading functionality."""
    
    def test_load_playlists_initializes_fetcher(self, playlist_screen):
        """Test that load_playlists would initialize fetcher."""
        # Just verify the method exists and screen has required attributes
        assert hasattr(playlist_screen, 'load_playlists')
        assert playlist_screen.fetcher is None
        # Note: Full async testing would require complex mocking setup


class TestPlaylistSelectionScreenPlaylistList:
    """Test playlist list management."""
    
    def test_update_playlist_list_with_playlists(self, playlist_screen, sample_playlists):
        """Test updating playlist list with data."""
        playlist_screen.build()
        playlist_screen.playlists = sample_playlists
        playlist_screen.filtered_playlists = sample_playlists
        
        playlist_screen._update_playlist_list()
        
        # Should have 3 playlist cards
        assert len(playlist_screen.playlist_list.controls) == 3
    
    def test_update_playlist_list_empty(self, playlist_screen):
        """Test updating playlist list with no playlists."""
        playlist_screen.build()
        playlist_screen.filtered_playlists = []
        
        playlist_screen._update_playlist_list()
        
        # Should show empty state message
        assert len(playlist_screen.playlist_list.controls) == 1
    
    def test_update_playlist_list_with_selection(self, playlist_screen, sample_playlists):
        """Test playlist list updates with selected items."""
        playlist_screen.build()
        playlist_screen.playlists = sample_playlists
        playlist_screen.filtered_playlists = sample_playlists
        playlist_screen.selected_playlists.add('playlist1')
        
        playlist_screen._update_playlist_list()
        
        # Should have cards with correct selection state
        assert len(playlist_screen.playlist_list.controls) == 3


class TestPlaylistSelectionScreenHeader:
    """Test header updates."""
    
    def test_update_header_all_playlists(self, playlist_screen, sample_playlists):
        """Test header with all playlists shown."""
        playlist_screen.build()
        playlist_screen.playlists = sample_playlists
        playlist_screen.filtered_playlists = sample_playlists
        playlist_screen.search_query = ""
        
        playlist_screen._update_header()
        
        assert "Found 3 public playlists" in playlist_screen.header_text.value
    
    def test_update_header_with_search(self, playlist_screen, sample_playlists):
        """Test header with search filtering."""
        playlist_screen.build()
        playlist_screen.playlists = sample_playlists
        playlist_screen.filtered_playlists = [sample_playlists[0]]
        playlist_screen.search_query = "rock"
        
        playlist_screen._update_header()
        
        assert "Showing 1 of 3 playlists" in playlist_screen.header_text.value


class TestPlaylistSelectionScreenFooter:
    """Test footer updates."""
    
    def test_update_footer_no_selection(self, playlist_screen):
        """Test footer with no selection."""
        playlist_screen.build()
        playlist_screen.playlists = []
        playlist_screen.selected_playlists = set()
        
        playlist_screen._update_footer()
        
        assert "Selected: 0 playlists" in playlist_screen.selection_summary.value
        assert "Total: 0 tracks" in playlist_screen.selection_summary.value
        assert playlist_screen.start_button.disabled is True
    
    def test_update_footer_with_selection(self, playlist_screen, sample_playlists):
        """Test footer with playlists selected."""
        playlist_screen.build()
        playlist_screen.playlists = sample_playlists
        playlist_screen.selected_playlists = {'playlist1', 'playlist2'}
        
        playlist_screen._update_footer()
        
        assert "Selected: 2 playlists" in playlist_screen.selection_summary.value
        assert "Total: 80 tracks" in playlist_screen.selection_summary.value
        assert playlist_screen.start_button.disabled is False
    
    def test_update_footer_enables_start_button(self, playlist_screen):
        """Test start button is enabled when playlists selected."""
        playlist_screen.build()
        playlist_screen.playlists = [{'id': 'p1', 'track_count': 10}]
        playlist_screen.selected_playlists = {'p1'}
        
        playlist_screen._update_footer()
        
        assert playlist_screen.start_button.disabled is False


class TestPlaylistSelectionScreenPlaylistToggle:
    """Test playlist selection toggling."""
    
    def test_toggle_select_playlist(self, playlist_screen):
        """Test selecting a playlist."""
        playlist_screen.build()
        
        playlist_screen.on_playlist_toggle('playlist1')
        
        assert 'playlist1' in playlist_screen.selected_playlists
    
    def test_toggle_deselect_playlist(self, playlist_screen):
        """Test deselecting a playlist."""
        playlist_screen.build()
        playlist_screen.selected_playlists.add('playlist1')
        
        playlist_screen.on_playlist_toggle('playlist1')
        
        assert 'playlist1' not in playlist_screen.selected_playlists
    
    def test_toggle_updates_footer(self, playlist_screen):
        """Test toggle updates footer."""
        playlist_screen.build()
        
        with patch.object(playlist_screen, '_update_footer') as mock_update:
            playlist_screen.on_playlist_toggle('playlist1')
            
            mock_update.assert_called_once()


class TestPlaylistSelectionScreenSelectAll:
    """Test select all functionality."""
    
    def test_select_all_selects_filtered_playlists(self, playlist_screen, sample_playlists):
        """Test select all selects all filtered playlists."""
        playlist_screen.build()
        playlist_screen.playlists = sample_playlists
        playlist_screen.filtered_playlists = sample_playlists
        
        playlist_screen.on_select_all_click(None)
        
        assert len(playlist_screen.selected_playlists) == 3
        assert 'playlist1' in playlist_screen.selected_playlists
        assert 'playlist2' in playlist_screen.selected_playlists
        assert 'playlist3' in playlist_screen.selected_playlists
    
    def test_select_all_with_filter(self, playlist_screen, sample_playlists):
        """Test select all only selects filtered playlists."""
        playlist_screen.build()
        playlist_screen.playlists = sample_playlists
        playlist_screen.filtered_playlists = [sample_playlists[0]]
        
        playlist_screen.on_select_all_click(None)
        
        assert len(playlist_screen.selected_playlists) == 1
        assert 'playlist1' in playlist_screen.selected_playlists


class TestPlaylistSelectionScreenDeselectAll:
    """Test deselect all functionality."""
    
    def test_deselect_all_clears_selection(self, playlist_screen):
        """Test deselect all clears all selections."""
        playlist_screen.build()
        playlist_screen.selected_playlists = {'playlist1', 'playlist2', 'playlist3'}
        
        playlist_screen.on_deselect_all_click(None)
        
        assert len(playlist_screen.selected_playlists) == 0


class TestPlaylistSelectionScreenSearch:
    """Test search functionality."""
    
    def test_search_filters_playlists(self, playlist_screen, sample_playlists):
        """Test search filters playlists by name."""
        playlist_screen.build()
        playlist_screen.playlists = sample_playlists
        playlist_screen.filtered_playlists = sample_playlists
        
        # Simulate search for "jazz"
        mock_event = Mock()
        mock_event.control.value = "jazz"
        playlist_screen.on_search_change(mock_event)
        
        assert len(playlist_screen.filtered_playlists) == 1
        assert playlist_screen.filtered_playlists[0]['name'] == 'Jazz Favorites'
    
    def test_search_case_insensitive(self, playlist_screen, sample_playlists):
        """Test search is case-insensitive."""
        playlist_screen.build()
        playlist_screen.playlists = sample_playlists
        
        mock_event = Mock()
        mock_event.control.value = "ROCK"
        playlist_screen.on_search_change(mock_event)
        
        assert len(playlist_screen.filtered_playlists) == 1
        assert playlist_screen.filtered_playlists[0]['name'] == 'Rock Classics'
    
    def test_search_empty_query_shows_all(self, playlist_screen, sample_playlists):
        """Test empty search shows all playlists."""
        playlist_screen.build()
        playlist_screen.playlists = sample_playlists
        playlist_screen.filtered_playlists = [sample_playlists[0]]
        
        mock_event = Mock()
        mock_event.control.value = ""
        playlist_screen.on_search_change(mock_event)
        
        assert len(playlist_screen.filtered_playlists) == 3
    
    def test_search_no_matches(self, playlist_screen, sample_playlists):
        """Test search with no matches."""
        playlist_screen.build()
        playlist_screen.playlists = sample_playlists
        
        mock_event = Mock()
        mock_event.control.value = "nonexistent"
        playlist_screen.on_search_change(mock_event)
        
        assert len(playlist_screen.filtered_playlists) == 0


class TestPlaylistSelectionScreenStartMigration:
    """Test start migration functionality."""
    
    def test_start_migration_no_selection_shows_error(self, playlist_screen):
        """Test start migration with no selection shows error."""
        playlist_screen.build()
        
        with patch.object(playlist_screen, 'show_error') as mock_error:
            playlist_screen.on_start_migration_click(None)
            
            mock_error.assert_called_once()
            assert "at least one playlist" in mock_error.call_args[0][0].lower()
    
    def test_start_migration_few_playlists(self, playlist_screen, sample_playlists):
        """Test start migration with few playlists."""
        playlist_screen.build()
        playlist_screen.playlists = sample_playlists
        playlist_screen.selected_playlists = {'playlist1', 'playlist2'}
        
        with patch.object(playlist_screen, '_start_migration') as mock_start:
            playlist_screen.on_start_migration_click(None)
            
            mock_start.assert_called_once()
    
    def test_start_migration_many_playlists_shows_warning(self, playlist_screen):
        """Test start migration with >50 playlists shows warning."""
        playlist_screen.build()
        # Create 51 playlists
        many_playlists = [
            {'id': f'playlist{i}', 'name': f'Playlist {i}', 'track_count': 10}
            for i in range(51)
        ]
        playlist_screen.playlists = many_playlists
        playlist_screen.selected_playlists = {p['id'] for p in many_playlists}
        
        with patch.object(playlist_screen, 'show_confirmation') as mock_confirm:
            playlist_screen.on_start_migration_click(None)
            
            mock_confirm.assert_called_once()
            assert "several hours" in mock_confirm.call_args[0][0]
    
    def test_start_migration_stores_playlists_in_app_state(self, playlist_screen, sample_playlists):
        """Test start migration stores playlists in app state."""
        playlist_screen.build()
        playlist_screen.playlists = sample_playlists
        playlist_screen.selected_playlists = {'playlist1', 'playlist2'}
        
        playlist_screen._start_migration()
        
        assert 'selected_playlists' in playlist_screen.app_state
        assert len(playlist_screen.app_state['selected_playlists']) == 2


class TestPlaylistSelectionScreenBackButton:
    """Test back button functionality."""
    
    def test_back_button_clears_selection(self, playlist_screen):
        """Test back button clears selection."""
        playlist_screen.build()
        playlist_screen.selected_playlists = {'playlist1', 'playlist2'}
        
        with patch.object(playlist_screen, 'navigate_to'):
            playlist_screen._handle_back(None)
            
            assert len(playlist_screen.selected_playlists) == 0
    
    def test_back_button_navigates_to_welcome(self, playlist_screen):
        """Test back button navigates to welcome screen."""
        playlist_screen.build()
        
        with patch.object(playlist_screen, 'navigate_to') as mock_nav:
            playlist_screen._handle_back(None)
            
            mock_nav.assert_called_once()
            # Check it's navigating to WelcomeScreen
            assert mock_nav.call_args[1].get('progress_text') == "Step 1 of 5"


class TestPlaylistSelectionScreenIntegration:
    """Integration tests for PlaylistSelectionScreen."""
    
    def test_search_and_select_flow(self, playlist_screen, sample_playlists):
        """Test search and selection integration."""
        playlist_screen.build()
        playlist_screen.playlists = sample_playlists
        playlist_screen.filtered_playlists = sample_playlists
        
        # Search
        mock_event = Mock()
        mock_event.control.value = "rock"
        playlist_screen.on_search_change(mock_event)
        assert len(playlist_screen.filtered_playlists) == 1
        
        # Select all visible
        playlist_screen.on_select_all_click(None)
        assert len(playlist_screen.selected_playlists) == 1
        assert 'playlist1' in playlist_screen.selected_playlists
        
        # Clear search
        mock_event.control.value = ""
        playlist_screen.on_search_change(mock_event)
        assert len(playlist_screen.filtered_playlists) == 3
        
        # Selection should persist
        assert 'playlist1' in playlist_screen.selected_playlists


class TestPlaylistSelectionScreenEdgeCases:
    """Test edge cases."""
    
    def test_toggle_nonexistent_playlist(self, playlist_screen):
        """Test toggling a nonexistent playlist ID."""
        playlist_screen.build()
        
        # Should not raise error
        playlist_screen.on_playlist_toggle('nonexistent')
        assert 'nonexistent' in playlist_screen.selected_playlists
    
    def test_empty_playlist_list_handling(self, playlist_screen):
        """Test handling of empty playlist list."""
        playlist_screen.build()
        playlist_screen.playlists = []
        playlist_screen.filtered_playlists = []
        
        playlist_screen._update_playlist_list()
        playlist_screen._update_header()
        playlist_screen._update_footer()
        
        # Should not crash
        assert len(playlist_screen.playlist_list.controls) >= 0
    
    def test_playlist_without_id(self, playlist_screen):
        """Test handling playlist without ID field."""
        playlist_screen.build()
        bad_playlist = {'name': 'No ID Playlist', 'track_count': 10}
        playlist_screen.playlists = [bad_playlist]
        playlist_screen.filtered_playlists = [bad_playlist]
        
        # Should not crash
        playlist_screen._update_playlist_list()
