"""
Tests for SettingsScreen.

This module contains comprehensive tests for the settings screen functionality,
including settings loading/saving, UI controls, cache management, and data reset.
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch, call

import pytest
import flet as ft

from src.ui.screens.settings_screen import SettingsScreen
from config import app_config


@pytest.fixture(autouse=True)
def _isolated_user_config(tmp_path, monkeypatch):
    """Reset also clears the saved Client ID; never touch the real home dir."""
    monkeypatch.setattr(app_config, "APP_DATA_DIR", str(tmp_path))


class TestSettingsScreenInitialization:
    """Tests for SettingsScreen initialization."""

    def test_init_creates_screen(self):
        """Test that SettingsScreen initializes correctly."""
        page = Mock(spec=ft.Page)
        app_state = {}
        
        screen = SettingsScreen(page, app_state)
        
        assert screen.page == page
        assert screen.app_state == app_state
        assert isinstance(screen.settings, dict)
        assert screen.match_threshold_slider is None
        assert screen.match_threshold_text is None
        assert screen.notifications_switch is None
        assert screen.theme_radio is None
        assert screen.cache_size_text is None
        assert screen.advanced_section is None
        assert screen.advanced_expanded is False

    def test_init_loads_settings(self):
        """Test that initialization loads settings."""
        page = Mock(spec=ft.Page)
        app_state = {}
        
        with patch.object(SettingsScreen, 'load_settings', return_value={'test': 'value'}):
            screen = SettingsScreen(page, app_state)
            
            assert screen.settings == {'test': 'value'}

    def test_default_settings_structure(self):
        """Test that default settings have correct structure."""
        defaults = SettingsScreen.DEFAULT_SETTINGS
        
        assert 'match_threshold' in defaults
        assert 'notifications_enabled' in defaults
        assert 'theme' in defaults
        assert 'rate_limit_delay' in defaults
        assert 'daily_operation_limit' in defaults
        assert defaults['match_threshold'] == 75
        assert defaults['notifications_enabled'] is True
        assert defaults['theme'] == 'system'


class TestSettingsLoading:
    """Tests for settings file loading."""

    def test_load_settings_file_exists(self):
        """Test loading settings from existing file."""
        page = Mock(spec=ft.Page)
        app_state = {}
        
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
            settings_data = {
                'match_threshold': 85,
                'notifications_enabled': False,
                'theme': 'dark',
            }
            json.dump(settings_data, f)
            temp_path = Path(f.name)
        
        try:
            with patch.object(SettingsScreen, 'SETTINGS_FILE', temp_path):
                screen = SettingsScreen(page, app_state)
                
                assert screen.settings['match_threshold'] == 85
                assert screen.settings['notifications_enabled'] is False
                assert screen.settings['theme'] == 'dark'
                # Should merge with defaults
                assert 'rate_limit_delay' in screen.settings
        finally:
            temp_path.unlink()

    def test_load_settings_file_not_exists(self):
        """Test loading settings when file doesn't exist."""
        page = Mock(spec=ft.Page)
        app_state = {}
        
        non_existent = Path('/nonexistent/settings.json')
        with patch.object(SettingsScreen, 'SETTINGS_FILE', non_existent):
            screen = SettingsScreen(page, app_state)
            
            assert screen.settings == SettingsScreen.DEFAULT_SETTINGS

    def test_load_settings_invalid_json(self):
        """Test loading settings with invalid JSON."""
        page = Mock(spec=ft.Page)
        app_state = {}
        
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
            f.write("invalid json {")
            temp_path = Path(f.name)
        
        try:
            with patch.object(SettingsScreen, 'SETTINGS_FILE', temp_path):
                screen = SettingsScreen(page, app_state)
                
                # Should fall back to defaults
                assert screen.settings == SettingsScreen.DEFAULT_SETTINGS
        finally:
            temp_path.unlink()


class TestSettingsSaving:
    """Tests for settings file saving."""

    def test_save_settings_creates_file(self):
        """Test that save_settings creates a file."""
        page = Mock(spec=ft.Page)
        page.update = Mock()
        app_state = {}
        
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_path = Path(tmpdir) / 'settings.json'
            
            with patch.object(SettingsScreen, 'SETTINGS_FILE', temp_path):
                screen = SettingsScreen(page, app_state)
                screen.settings['match_threshold'] = 90
                screen.save_settings()
                
                assert temp_path.exists()
                with open(temp_path, 'r') as f:
                    saved = json.load(f)
                    assert saved['match_threshold'] == 90

    def test_save_settings_applies_theme(self):
        """Test that save_settings applies theme immediately."""
        page = Mock(spec=ft.Page)
        page.update = Mock()
        app_state = {}
        
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_path = Path(tmpdir) / 'settings.json'
            
            with patch.object(SettingsScreen, 'SETTINGS_FILE', temp_path):
                screen = SettingsScreen(page, app_state)
                screen.settings['theme'] = 'dark'
                screen.save_settings()
                
                assert page.theme_mode == ft.ThemeMode.DARK
                page.update.assert_called()

    def test_save_settings_shows_success(self):
        """Test that save_settings shows success message."""
        page = Mock(spec=ft.Page)
        page.update = Mock()
        page.overlay = []
        app_state = {}
        
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_path = Path(tmpdir) / 'settings.json'
            
            with patch.object(SettingsScreen, 'SETTINGS_FILE', temp_path):
                screen = SettingsScreen(page, app_state)
                screen.save_settings()
                
                # Check that show_success was called
                assert len(page.overlay) > 0

    def test_save_settings_error_handling(self):
        """Test save_settings handles errors gracefully."""
        page = Mock(spec=ft.Page)
        page.update = Mock()
        page.overlay = []
        app_state = {}
        
        # Use an invalid path to trigger an error
        with patch.object(SettingsScreen, 'SETTINGS_FILE', Path('/invalid/path/settings.json')):
            screen = SettingsScreen(page, app_state)
            screen.save_settings()
            
            # Should show error dialog
            assert len(page.overlay) > 0


class TestThemeApplication:
    """Tests for theme application."""

    def test_apply_theme_light(self):
        """Test applying light theme."""
        page = Mock(spec=ft.Page)
        page.update = Mock()
        app_state = {}
        
        screen = SettingsScreen(page, app_state)
        screen.settings['theme'] = 'light'
        screen._apply_theme()
        
        assert page.theme_mode == ft.ThemeMode.LIGHT
        page.update.assert_called_once()

    def test_apply_theme_dark(self):
        """Test applying dark theme."""
        page = Mock(spec=ft.Page)
        page.update = Mock()
        app_state = {}
        
        screen = SettingsScreen(page, app_state)
        screen.settings['theme'] = 'dark'
        screen._apply_theme()
        
        assert page.theme_mode == ft.ThemeMode.DARK
        page.update.assert_called_once()

    def test_apply_theme_system(self):
        """Test applying system theme."""
        page = Mock(spec=ft.Page)
        page.update = Mock()
        app_state = {}
        
        screen = SettingsScreen(page, app_state)
        screen.settings['theme'] = 'system'
        screen._apply_theme()
        
        assert page.theme_mode == ft.ThemeMode.SYSTEM
        page.update.assert_called_once()


class TestCacheSize:
    """Tests for cache size calculation."""

    def test_get_cache_size_with_cache_manager(self):
        """Test getting cache size when cache manager exists."""
        page = Mock(spec=ft.Page)
        
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b'0' * 1024 * 50)  # 50 KB
            temp_path = Path(f.name)
        
        try:
            cache_manager = Mock()
            cache_manager.db_path = str(temp_path)
            app_state = {'cache_manager': cache_manager}
            
            screen = SettingsScreen(page, app_state)
            size = screen.get_cache_size()
            
            assert 'KB' in size or 'MB' in size
        finally:
            temp_path.unlink()

    def test_get_cache_size_no_cache_manager(self):
        """Test getting cache size when cache manager doesn't exist."""
        page = Mock(spec=ft.Page)
        app_state = {}
        
        screen = SettingsScreen(page, app_state)
        size = screen.get_cache_size()
        
        assert size == "Unknown"

    def test_get_cache_size_file_not_exists(self):
        """Test getting cache size when database file doesn't exist."""
        page = Mock(spec=ft.Page)
        cache_manager = Mock()
        cache_manager.db_path = '/nonexistent/cache.db'
        app_state = {'cache_manager': cache_manager}
        
        screen = SettingsScreen(page, app_state)
        size = screen.get_cache_size()
        
        assert size == "0 KB"

    def test_get_cache_size_formats(self):
        """Test cache size formatting for different sizes."""
        page = Mock(spec=ft.Page)
        
        # Test KB
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b'0' * 2048)  # 2 KB
            temp_path = Path(f.name)
        
        try:
            cache_manager = Mock()
            cache_manager.db_path = str(temp_path)
            app_state = {'cache_manager': cache_manager}
            
            screen = SettingsScreen(page, app_state)
            size = screen.get_cache_size()
            
            assert 'KB' in size
        finally:
            temp_path.unlink()


class TestBuildMethod:
    """Tests for the build method."""

    def test_build_returns_control(self):
        """Test that build returns a control."""
        page = Mock(spec=ft.Page)
        app_state = {}
        
        screen = SettingsScreen(page, app_state)
        control = screen.build()
        
        assert isinstance(control, ft.Control)

    def test_build_creates_match_threshold_slider(self):
        """Test that build creates match threshold slider."""
        page = Mock(spec=ft.Page)
        app_state = {}
        
        screen = SettingsScreen(page, app_state)
        screen.build()
        
        assert screen.match_threshold_slider is not None
        assert isinstance(screen.match_threshold_slider, ft.Slider)
        assert screen.match_threshold_slider.min == 60
        assert screen.match_threshold_slider.max == 95

    def test_build_creates_notifications_switch(self):
        """Test that build creates notifications switch."""
        page = Mock(spec=ft.Page)
        app_state = {}
        
        screen = SettingsScreen(page, app_state)
        screen.build()
        
        assert screen.notifications_switch is not None
        assert isinstance(screen.notifications_switch, ft.Switch)

    def test_build_creates_theme_radio(self):
        """Test that build creates theme radio group."""
        page = Mock(spec=ft.Page)
        app_state = {}
        
        screen = SettingsScreen(page, app_state)
        screen.build()
        
        assert screen.theme_radio is not None
        assert isinstance(screen.theme_radio, ft.RadioGroup)

    def test_build_creates_cache_section(self):
        """Test that build creates cache management section."""
        page = Mock(spec=ft.Page)
        app_state = {}
        
        screen = SettingsScreen(page, app_state)
        screen.build()
        
        assert screen.cache_size_text is not None
        assert isinstance(screen.cache_size_text, ft.Text)

    def test_build_creates_advanced_section(self):
        """Test that build creates advanced settings section."""
        page = Mock(spec=ft.Page)
        app_state = {}
        
        screen = SettingsScreen(page, app_state)
        screen.build()
        
        assert screen.advanced_section is not None
        assert isinstance(screen.advanced_section, ft.Container)


class TestMatchThreshold:
    """Tests for match threshold setting."""

    def test_on_match_threshold_change(self):
        """Test match threshold slider change handler."""
        page = Mock(spec=ft.Page)
        page.update = Mock()
        app_state = {}
        
        screen = SettingsScreen(page, app_state)
        screen.build()
        
        event = Mock()
        event.control.value = 85
        screen.on_match_threshold_change(event)
        
        assert screen.settings['match_threshold'] == 85
        assert screen.match_threshold_text.value == "85%"
        page.update.assert_called()

    def test_match_threshold_initial_value(self):
        """Test match threshold slider uses initial value from settings."""
        page = Mock(spec=ft.Page)
        app_state = {}
        
        screen = SettingsScreen(page, app_state)
        screen.settings['match_threshold'] = 90
        screen.build()
        
        assert screen.match_threshold_slider.value == 90


class TestNotifications:
    """Tests for notification settings."""

    def test_on_notifications_change(self):
        """Test notifications switch change handler."""
        page = Mock(spec=ft.Page)
        app_state = {}
        
        screen = SettingsScreen(page, app_state)
        
        event = Mock()
        event.control.value = False
        screen.on_notifications_change(event)
        
        assert screen.settings['notifications_enabled'] is False

    def test_notifications_initial_value(self):
        """Test notifications switch uses initial value from settings."""
        page = Mock(spec=ft.Page)
        app_state = {}
        
        screen = SettingsScreen(page, app_state)
        screen.settings['notifications_enabled'] = False
        screen.build()
        
        assert screen.notifications_switch.value is False


class TestThemeSelection:
    """Tests for theme selection."""

    def test_on_theme_change(self):
        """Test theme radio button change handler."""
        page = Mock(spec=ft.Page)
        app_state = {}
        
        screen = SettingsScreen(page, app_state)
        
        event = Mock()
        event.control.value = 'dark'
        screen.on_theme_change(event)
        
        assert screen.settings['theme'] == 'dark'

    def test_theme_initial_value(self):
        """Test theme radio uses initial value from settings."""
        page = Mock(spec=ft.Page)
        app_state = {}
        
        screen = SettingsScreen(page, app_state)
        screen.settings['theme'] = 'light'
        screen.build()
        
        assert screen.theme_radio.value == 'light'


class TestAdvancedSettings:
    """Tests for advanced settings."""

    def test_on_rate_limit_change_valid(self):
        """Test rate limit change with valid value."""
        page = Mock(spec=ft.Page)
        app_state = {}
        
        screen = SettingsScreen(page, app_state)
        
        event = Mock()
        event.control.value = '1.5'
        screen.on_rate_limit_change(event)
        
        assert screen.settings['rate_limit_delay'] == 1.5

    def test_on_rate_limit_change_invalid(self):
        """Test rate limit change with invalid value."""
        page = Mock(spec=ft.Page)
        app_state = {}
        
        screen = SettingsScreen(page, app_state)
        original_value = screen.settings['rate_limit_delay']
        
        event = Mock()
        event.control.value = 'invalid'
        screen.on_rate_limit_change(event)
        
        # Should not change
        assert screen.settings['rate_limit_delay'] == original_value

    def test_on_daily_limit_change_valid(self):
        """Test daily limit change with valid value."""
        page = Mock(spec=ft.Page)
        app_state = {}
        
        screen = SettingsScreen(page, app_state)
        
        event = Mock()
        event.control.value = '5000'
        screen.on_daily_limit_change(event)
        
        assert screen.settings['daily_operation_limit'] == 5000

    def test_on_daily_limit_change_invalid(self):
        """Test daily limit change with invalid value."""
        page = Mock(spec=ft.Page)
        app_state = {}
        
        screen = SettingsScreen(page, app_state)
        original_value = screen.settings['daily_operation_limit']
        
        event = Mock()
        event.control.value = 'invalid'
        screen.on_daily_limit_change(event)
        
        # Should not change
        assert screen.settings['daily_operation_limit'] == original_value

    def test_on_toggle_advanced(self):
        """Test toggling advanced section visibility."""
        page = Mock(spec=ft.Page)
        page.update = Mock()
        app_state = {}
        
        screen = SettingsScreen(page, app_state)
        screen.build()
        
        assert screen.advanced_expanded is False
        
        screen.on_toggle_advanced(None)
        
        assert screen.advanced_expanded is True
        page.update.assert_called()


class TestCacheManagement:
    """Tests for cache management."""

    def test_on_clear_cache_click_shows_confirmation(self):
        """Test that clear cache shows confirmation dialog."""
        page = Mock(spec=ft.Page)
        page.overlay = []
        page.update = Mock()
        app_state = {}
        
        screen = SettingsScreen(page, app_state)
        screen.on_clear_cache_click(None)
        
        # Should show confirmation dialog
        assert len(page.overlay) > 0

    def test_clear_cache_confirmed(self):
        """Test clearing cache when confirmed."""
        page = Mock(spec=ft.Page)
        page.overlay = []
        page.update = Mock()
        
        cache_manager = Mock()
        cache_manager.clear_cache = Mock()
        cache_manager.db_path = '/fake/path.db'
        app_state = {'cache_manager': cache_manager}
        
        screen = SettingsScreen(page, app_state)
        screen.build()
        
        # Simulate confirmation
        with patch.object(screen, 'show_confirmation') as mock_confirm:
            screen.on_clear_cache_click(None)
            
            # Get the on_confirm callback
            on_confirm = mock_confirm.call_args[1]['on_confirm']
            on_confirm()
            
            cache_manager.clear_cache.assert_called_once()

    def test_clear_cache_no_cache_manager(self):
        """Test clearing cache when cache manager doesn't exist."""
        page = Mock(spec=ft.Page)
        page.overlay = []
        page.update = Mock()
        app_state = {}
        
        screen = SettingsScreen(page, app_state)
        
        # Simulate confirmation
        with patch.object(screen, 'show_confirmation') as mock_confirm:
            screen.on_clear_cache_click(None)
            
            # Get the on_confirm callback
            on_confirm = mock_confirm.call_args[1]['on_confirm']
            on_confirm()
            
            # Should show error
            assert len(page.overlay) > 0


class TestDataReset:
    """Tests for complete data reset."""

    def test_on_reset_click_shows_confirmation(self):
        """Test that reset shows confirmation dialog."""
        page = Mock(spec=ft.Page)
        page.overlay = []
        page.update = Mock()
        app_state = {}
        
        screen = SettingsScreen(page, app_state)
        screen.on_reset_click(None)
        
        # Should show confirmation dialog
        assert len(page.overlay) > 0

    def test_reset_confirmed_clears_cache(self):
        """Test that reset clears cache when confirmed."""
        page = Mock(spec=ft.Page)
        page.overlay = []
        page.update = Mock()
        page.controls = []
        
        cache_manager = Mock()
        cache_manager.clear_cache = Mock()
        token_manager = Mock()
        token_manager.clear_spotify_token = Mock()
        token_manager.clear_youtube_token = Mock()
        
        app_state = {
            'cache_manager': cache_manager,
            'token_manager': token_manager,
            'spotify_client': 'fake',
            'youtube_client': 'fake',
            'selected_playlists': ['test'],
        }
        
        screen = SettingsScreen(page, app_state)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_path = Path(tmpdir) / 'settings.json'
            temp_path.write_text('{}')
            
            with patch.object(SettingsScreen, 'SETTINGS_FILE', temp_path):
                # Simulate confirmation
                with patch.object(screen, 'show_confirmation') as mock_confirm:
                    screen.on_reset_click(None)
                    
                    # Get the on_confirm callback
                    on_confirm = mock_confirm.call_args[1]['on_confirm']
                    on_confirm()
                    
                    cache_manager.clear_cache.assert_called_once()
                    token_manager.clear_spotify_token.assert_called_once()
                    token_manager.clear_youtube_token.assert_called_once()

    def test_reset_confirmed_clears_app_state(self):
        """Test that reset clears app state when confirmed."""
        page = Mock(spec=ft.Page)
        page.overlay = []
        page.update = Mock()
        page.controls = []
        
        app_state = {
            'spotify_client': 'fake',
            'youtube_client': 'fake',
            'token_manager': Mock(),
            'selected_playlists': ['test'],
            'migration_results': {'test': 'data'},
            'playlist_results': ['result'],
        }
        
        screen = SettingsScreen(page, app_state)
        
        # Simulate confirmation
        with patch.object(screen, 'show_confirmation') as mock_confirm:
            screen.on_reset_click(None)
            
            # Get the on_confirm callback
            on_confirm = mock_confirm.call_args[1]['on_confirm']
            on_confirm()
            
            assert app_state['spotify_client'] is None
            assert app_state['youtube_client'] is None
            assert app_state['token_manager'] is None
            assert app_state['selected_playlists'] == []
            assert app_state['migration_results'] == {}
            assert app_state['playlist_results'] == []

    def test_reset_confirmed_navigates_to_welcome(self):
        """Test that reset navigates to welcome screen."""
        page = Mock(spec=ft.Page)
        page.overlay = []
        page.update = Mock()
        page.controls = []
        
        app_state = {'cache_manager': Mock(), 'token_manager': Mock()}
        
        screen = SettingsScreen(page, app_state)
        
        # Simulate confirmation
        with patch.object(screen, 'show_confirmation') as mock_confirm:
            with patch.object(screen, 'navigate_to') as mock_navigate:
                screen.on_reset_click(None)
                
                # Get the on_confirm callback
                on_confirm = mock_confirm.call_args[1]['on_confirm']
                on_confirm()
                
                mock_navigate.assert_called_once()


class TestSaveButton:
    """Tests for the save button."""

    def test_on_save_click_calls_save_settings(self):
        """Test that save button calls save_settings."""
        page = Mock(spec=ft.Page)
        page.update = Mock()
        app_state = {}
        
        screen = SettingsScreen(page, app_state)
        
        with patch.object(screen, 'save_settings') as mock_save:
            screen.on_save_click(None)
            mock_save.assert_called_once()


class TestIntegration:
    """Integration tests for SettingsScreen."""

    def test_full_settings_flow(self):
        """Test complete settings modification and save flow."""
        page = Mock(spec=ft.Page)
        page.update = Mock()
        page.overlay = []
        
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_path = Path(tmpdir) / 'settings.json'
            
            with patch.object(SettingsScreen, 'SETTINGS_FILE', temp_path):
                app_state = {}
                screen = SettingsScreen(page, app_state)
                screen.build()
                
                # Change settings
                event = Mock()
                event.control.value = 80
                screen.on_match_threshold_change(event)
                
                event.control.value = False
                screen.on_notifications_change(event)
                
                event.control.value = 'dark'
                screen.on_theme_change(event)
                
                # Save
                screen.save_settings()
                
                # Verify file was created with correct values
                assert temp_path.exists()
                with open(temp_path, 'r') as f:
                    saved = json.load(f)
                    assert saved['match_threshold'] == 80
                    assert saved['notifications_enabled'] is False
                    assert saved['theme'] == 'dark'

    def test_settings_persistence(self):
        """Test that settings persist across screen instances."""
        page = Mock(spec=ft.Page)
        page.update = Mock()
        page.overlay = []
        
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_path = Path(tmpdir) / 'settings.json'
            
            with patch.object(SettingsScreen, 'SETTINGS_FILE', temp_path):
                # Create first screen and save settings
                screen1 = SettingsScreen(page, {})
                screen1.settings['match_threshold'] = 88
                screen1.save_settings()
                
                # Create second screen and verify settings loaded
                screen2 = SettingsScreen(page, {})
                assert screen2.settings['match_threshold'] == 88


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_negative_rate_limit(self):
        """Test that negative rate limit values are rejected."""
        page = Mock(spec=ft.Page)
        app_state = {}
        
        screen = SettingsScreen(page, app_state)
        original_value = screen.settings['rate_limit_delay']
        
        event = Mock()
        event.control.value = '-1.0'
        screen.on_rate_limit_change(event)
        
        # Should not change to negative
        assert screen.settings['rate_limit_delay'] == original_value

    def test_zero_daily_limit(self):
        """Test that zero daily limit is rejected."""
        page = Mock(spec=ft.Page)
        app_state = {}
        
        screen = SettingsScreen(page, app_state)
        original_value = screen.settings['daily_operation_limit']
        
        event = Mock()
        event.control.value = '0'
        screen.on_daily_limit_change(event)
        
        # Should not change to zero
        assert screen.settings['daily_operation_limit'] == original_value

    def test_cache_size_with_error(self):
        """Test cache size calculation handles errors gracefully."""
        page = Mock(spec=ft.Page)
        cache_manager = Mock()
        cache_manager.db_path = Mock(side_effect=Exception("Test error"))
        app_state = {'cache_manager': cache_manager}
        
        screen = SettingsScreen(page, app_state)
        size = screen.get_cache_size()
        
        assert size == "Unknown"
