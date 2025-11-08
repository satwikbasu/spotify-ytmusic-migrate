"""Tests for main.py application entry point."""

import pytest
from unittest.mock import Mock, patch, MagicMock
import logging
from pathlib import Path

import flet as ft


class TestLoggingSetup:
    """Test logging configuration."""
    
    def test_setup_logging_creates_log_directory(self):
        """Test that logging setup creates log directory."""
        from main import setup_logging
        
        with patch('main.logging.basicConfig'):
            with patch('main.app_config.ensure_app_directories'):
                setup_logging()
        
        log_dir = Path.home() / ".playlist_migrator"
        assert log_dir.exists()
    
    def test_setup_logging_configures_handlers(self):
        """Test that logging is configured with file and console handlers."""
        from main import setup_logging
        
        with patch('main.logging.basicConfig') as mock_config:
            with patch('main.app_config.ensure_app_directories'):
                setup_logging()
                
                mock_config.assert_called_once()
                call_kwargs = mock_config.call_args[1]
                assert 'handlers' in call_kwargs
                assert len(call_kwargs['handlers']) == 2


class TestAppStateManagement:
    """Test application state initialization and cleanup."""
    
    def test_initialize_app_state_creates_dict(self):
        """Test that app state is initialized with required keys."""
        from main import initialize_app_state
        
        with patch('main.CacheManager'):
            app_state = initialize_app_state()
            
            assert isinstance(app_state, dict)
            assert 'spotify_client' in app_state
            assert 'youtube_client' in app_state
            assert 'cache_manager' in app_state
            assert 'selected_playlists' in app_state
            assert 'migration_results' in app_state
    
    def test_initialize_app_state_creates_cache_manager(self):
        """Test that cache manager is initialized."""
        from main import initialize_app_state
        
        mock_cache = Mock()
        with patch('main.CacheManager', return_value=mock_cache):
            app_state = initialize_app_state()
            
            assert app_state['cache_manager'] == mock_cache
    
    def test_initialize_app_state_handles_cache_error(self):
        """Test graceful handling of cache manager initialization error."""
        from main import initialize_app_state
        
        with patch('main.CacheManager', side_effect=Exception("DB error")):
            app_state = initialize_app_state()
            
            # Should not crash, cache_manager should be None
            assert app_state['cache_manager'] is None
    
    def test_cleanup_app_state_stops_migration_manager(self):
        """Test that cleanup stops migration manager."""
        from main import cleanup_app_state
        
        mock_manager = Mock()
        mock_manager.stop = Mock()
        
        app_state = {
            'migration_manager': mock_manager,
            'cache_manager': None
        }
        
        cleanup_app_state(app_state)
        
        mock_manager.stop.assert_called_once()
    
    def test_cleanup_app_state_closes_cache_manager(self):
        """Test that cleanup closes cache manager."""
        from main import cleanup_app_state
        
        mock_cache = Mock()
        mock_cache.close = Mock()
        
        app_state = {
            'migration_manager': None,
            'cache_manager': mock_cache
        }
        
        cleanup_app_state(app_state)
        
        mock_cache.close.assert_called_once()
    
    def test_cleanup_app_state_handles_errors(self):
        """Test that cleanup handles errors gracefully."""
        from main import cleanup_app_state
        
        mock_manager = Mock()
        mock_manager.stop = Mock(side_effect=Exception("Stop error"))
        
        app_state = {
            'migration_manager': mock_manager,
            'cache_manager': None
        }
        
        # Should not raise exception
        cleanup_app_state(app_state)


class TestWindowEventHandling:
    """Test window event handling."""
    
    def test_handle_window_event_close(self):
        """Test handling window close event."""
        from main import handle_window_event
        
        mock_event = Mock()
        mock_event.data = "close"
        
        app_state = {
            'migration_manager': None,
            'cache_manager': None
        }
        
        # Should not raise exception
        handle_window_event(mock_event, app_state)
    
    def test_handle_window_event_calls_cleanup(self):
        """Test that window close calls cleanup."""
        from main import handle_window_event
        
        mock_event = Mock()
        mock_event.data = "close"
        
        mock_manager = Mock()
        mock_manager.stop = Mock()
        
        app_state = {
            'migration_manager': mock_manager,
            'cache_manager': None
        }
        
        handle_window_event(mock_event, app_state)
        
        mock_manager.stop.assert_called_once()


class TestErrorHandling:
    """Test error handling and dialogs."""
    
    def test_show_error_dialog_creates_dialog(self):
        """Test that error dialog is created and shown."""
        from main import show_error_dialog
        
        mock_page = Mock()
        mock_page.overlay = []
        mock_page.update = Mock()
        
        show_error_dialog(mock_page, "Test error message")
        
        assert len(mock_page.overlay) == 1
        assert mock_page.overlay[0].open is True
        mock_page.update.assert_called_once()
    
    def test_close_dialog_closes_dialog(self):
        """Test that dialog is properly closed."""
        from main import close_dialog
        
        mock_dialog = Mock()
        mock_dialog.open = True
        
        mock_page = Mock()
        mock_page.update = Mock()
        
        close_dialog(mock_dialog, mock_page)
        
        assert mock_dialog.open is False
        mock_page.update.assert_called_once()
    
    def test_handle_exception_logs_and_shows_dialog(self):
        """Test that exception is logged and dialog is shown."""
        from main import handle_exception
        
        mock_page = Mock()
        mock_page.overlay = []
        mock_page.update = Mock()
        
        test_exception = ValueError("Test error")
        
        handle_exception(mock_page, test_exception)
        
        # Should show error dialog
        assert len(mock_page.overlay) > 0


class TestMainFunction:
    """Test main application function."""
    
    def test_main_configures_page(self):
        """Test that main function configures page properties."""
        from main import main
        
        mock_page = Mock(spec=ft.Page)
        mock_page.overlay = []
        
        with patch('main.initialize_app_state', return_value={}):
            with patch('main.WelcomeScreen') as mock_screen_class:
                mock_screen = Mock()
                mock_screen_class.return_value = mock_screen
                
                main(mock_page)
                
                assert mock_page.title == "Spotify to YouTube Music Migrator"
                assert mock_page.window_width == 800
                assert mock_page.window_height == 600
                assert mock_page.window_resizable is False
    
    def test_main_initializes_app_state(self):
        """Test that main function initializes app state."""
        from main import main
        
        mock_page = Mock(spec=ft.Page)
        mock_page.overlay = []
        
        with patch('main.initialize_app_state') as mock_init:
            mock_init.return_value = {}
            with patch('main.WelcomeScreen'):
                main(mock_page)
                
                mock_init.assert_called_once()
    
    def test_main_creates_welcome_screen(self):
        """Test that main function creates and shows WelcomeScreen."""
        from main import main
        
        mock_page = Mock(spec=ft.Page)
        mock_page.overlay = []
        
        with patch('main.initialize_app_state', return_value={}):
            with patch('main.WelcomeScreen') as mock_screen_class:
                mock_screen = Mock()
                mock_screen.show = Mock()
                mock_screen_class.return_value = mock_screen
                
                main(mock_page)
                
                mock_screen_class.assert_called_once_with(mock_page, {})
                mock_screen.show.assert_called_once()
    
    def test_main_handles_initialization_error(self):
        """Test that main function handles initialization errors."""
        from main import main
        
        mock_page = Mock(spec=ft.Page)
        mock_page.overlay = []
        mock_page.update = Mock()
        
        with patch('main.initialize_app_state', side_effect=Exception("Init error")):
            main(mock_page)
            
            # Should show error dialog instead of crashing
            assert len(mock_page.overlay) > 0
    
    def test_main_sets_window_event_handler(self):
        """Test that main sets window event handler."""
        from main import main
        
        mock_page = Mock(spec=ft.Page)
        mock_page.overlay = []
        mock_page.on_window_event = None
        
        with patch('main.initialize_app_state', return_value={}):
            with patch('main.WelcomeScreen'):
                main(mock_page)
                
                assert mock_page.on_window_event is not None


class TestIntegration:
    """Test integrated functionality."""
    
    def test_full_initialization_flow(self):
        """Test complete initialization sequence."""
        from main import main, initialize_app_state
        
        mock_page = Mock(spec=ft.Page)
        mock_page.overlay = []
        
        with patch('main.CacheManager'):
            with patch('main.WelcomeScreen') as mock_screen_class:
                mock_screen = Mock()
                mock_screen.show = Mock()
                mock_screen_class.return_value = mock_screen
                
                main(mock_page)
                
                # Verify page configuration
                assert mock_page.title is not None
                assert mock_page.window_width > 0
                assert mock_page.window_height > 0
                
                # Verify screen was shown
                mock_screen.show.assert_called_once()
