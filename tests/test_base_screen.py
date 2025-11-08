"""Tests for BaseScreen abstract class."""

import pytest
import flet as ft
from unittest.mock import Mock, MagicMock, patch
import time

from src.ui.base_screen import BaseScreen
from config import app_config


class TestScreen(BaseScreen):
    """Concrete implementation of BaseScreen for testing."""
    
    def build(self) -> ft.Control:
        """Return a simple test control."""
        return ft.Container(
            content=ft.Text("Test Screen"),
            expand=True
        )


class TestBaseScreenInitialization:
    """Test BaseScreen initialization."""
    
    def test_init_with_page_and_state(self):
        """Test BaseScreen initializes with page and app_state."""
        page = Mock(spec=ft.Page)
        app_state = {'key': 'value'}
        
        screen = TestScreen(page, app_state)
        
        assert screen.page is page
        assert screen.app_state == {'key': 'value'}
        assert screen._loading_overlay is None
    
    def test_init_with_empty_state(self):
        """Test BaseScreen initializes with empty app_state."""
        page = Mock(spec=ft.Page)
        app_state = {}
        
        screen = TestScreen(page, app_state)
        
        assert screen.app_state == {}
    
    def test_init_with_complex_state(self):
        """Test BaseScreen initializes with complex app_state."""
        page = Mock(spec=ft.Page)
        app_state = {
            'spotify_token': 'abc123',
            'youtube_token': 'xyz789',
            'user': {'name': 'John', 'id': '123'},
            'settings': {'theme': 'dark'}
        }
        
        screen = TestScreen(page, app_state)
        
        assert screen.app_state['spotify_token'] == 'abc123'
        assert screen.app_state['user']['name'] == 'John'


class TestBaseScreenAbstractMethod:
    """Test BaseScreen abstract method enforcement."""
    
    def test_cannot_instantiate_base_screen_directly(self):
        """Test BaseScreen cannot be instantiated directly."""
        page = Mock(spec=ft.Page)
        app_state = {}
        
        with pytest.raises(TypeError, match="Can't instantiate abstract class"):
            BaseScreen(page, app_state)
    
    def test_build_must_be_implemented(self):
        """Test subclass must implement build()."""
        class IncompleteScreen(BaseScreen):
            pass
        
        page = Mock(spec=ft.Page)
        app_state = {}
        
        with pytest.raises(TypeError, match="Can't instantiate abstract class"):
            IncompleteScreen(page, app_state)
    
    def test_build_implementation_returns_control(self):
        """Test build() returns a Flet control."""
        page = Mock(spec=ft.Page)
        app_state = {}
        screen = TestScreen(page, app_state)
        
        result = screen.build()
        
        assert isinstance(result, ft.Control)


class TestBaseScreenShow:
    """Test BaseScreen show() method."""
    
    def test_show_clears_page_controls(self):
        """Test show() clears page controls."""
        page = Mock(spec=ft.Page)
        page.controls = Mock()
        page.controls.__iter__ = Mock(return_value=iter([ft.Text("Old content")]))
        page.overlay = []
        app_state = {}
        screen = TestScreen(page, app_state)
        
        screen.show()
        
        page.controls.clear.assert_called()
    
    def test_show_builds_screen_content(self):
        """Test show() calls build()."""
        page = Mock(spec=ft.Page)
        page.controls = []
        page.overlay = []
        app_state = {}
        screen = TestScreen(page, app_state)
        
        with patch.object(screen, 'build', return_value=ft.Text("Test")) as mock_build:
            screen.show()
            mock_build.assert_called_once()
    
    def test_show_without_back_button(self):
        """Test show() without back button."""
        page = Mock(spec=ft.Page)
        page.controls = []
        page.overlay = []
        app_state = {}
        screen = TestScreen(page, app_state)
        
        screen.show(show_back=False)
        
        page.add.assert_called_once()
        # First control should be Column with header
        added_control = page.add.call_args[0][0]
        assert isinstance(added_control, ft.Column)
    
    def test_show_with_back_button(self):
        """Test show() with back button."""
        page = Mock(spec=ft.Page)
        page.controls = []
        page.overlay = []
        app_state = {}
        screen = TestScreen(page, app_state)
        
        screen.show(show_back=True)
        
        page.add.assert_called_once()
        added_control = page.add.call_args[0][0]
        # Should have header row with back button
        assert isinstance(added_control, ft.Column)
        header = added_control.controls[0]
        assert isinstance(header, ft.Row)
        # First control should be IconButton
        assert isinstance(header.controls[0], ft.IconButton)
        assert header.controls[0].icon == ft.Icons.ARROW_BACK
    
    def test_show_with_progress_text(self):
        """Test show() with progress indicator."""
        page = Mock(spec=ft.Page)
        page.controls = []
        page.overlay = []
        app_state = {}
        screen = TestScreen(page, app_state)
        
        screen.show(progress_text="Step 2 of 5")
        
        added_control = page.add.call_args[0][0]
        header = added_control.controls[0]
        # Last control should be progress text
        progress_text = header.controls[-1]
        assert isinstance(progress_text, ft.Text)
        assert progress_text.value == "Step 2 of 5"
    
    def test_show_with_back_and_progress(self):
        """Test show() with both back button and progress."""
        page = Mock(spec=ft.Page)
        page.controls = []
        page.overlay = []
        app_state = {}
        screen = TestScreen(page, app_state)
        
        screen.show(show_back=True, progress_text="Step 3 of 5")
        
        added_control = page.add.call_args[0][0]
        header = added_control.controls[0]
        # First should be back button
        assert isinstance(header.controls[0], ft.IconButton)
        # Last should be progress text
        assert isinstance(header.controls[-1], ft.Text)
        assert header.controls[-1].value == "Step 3 of 5"
    
    def test_show_updates_page_twice(self):
        """Test show() updates page for initial display and animation."""
        page = Mock(spec=ft.Page)
        page.controls = []
        page.overlay = []
        app_state = {}
        screen = TestScreen(page, app_state)
        
        screen.show()
        
        # Should update twice: once after add, once for animation
        assert page.update.call_count >= 2
    
    def test_show_sets_fade_in_animation(self):
        """Test show() sets up fade-in animation."""
        page = Mock(spec=ft.Page)
        page.controls = []
        page.overlay = []
        app_state = {}
        screen = TestScreen(page, app_state)
        
        screen.show()
        
        added_control = page.add.call_args[0][0]
        # Content should be wrapped in animated container
        content_container = added_control.controls[2]  # After header and spacing
        assert isinstance(content_container, ft.Container)
        assert content_container.animate_opacity == BaseScreen.FADE_IN_DURATION
        assert content_container.opacity == 1  # Final state


class TestBaseScreenNavigation:
    """Test BaseScreen navigation methods."""
    
    def test_navigate_to_creates_new_screen(self):
        """Test navigate_to() creates instance of target screen."""
        page = Mock(spec=ft.Page)
        page.controls = Mock()
        page.overlay = []
        app_state = {'data': 'test'}
        screen = TestScreen(page, app_state)
        
        class TargetScreen(BaseScreen):
            def build(self) -> ft.Control:
                return ft.Text("Target")
        
        screen.navigate_to(TargetScreen)
        
        # Should have called show on new screen
        page.controls.clear.assert_called()
        page.add.assert_called()
    
    def test_navigate_to_passes_app_state(self):
        """Test navigate_to() passes app_state to new screen."""
        page = Mock(spec=ft.Page)
        page.controls = []
        page.overlay = []
        app_state = {'token': 'abc123'}
        screen = TestScreen(page, app_state)
        
        class TargetScreen(BaseScreen):
            def build(self) -> ft.Control:
                # Access app_state to verify it's passed
                return ft.Text(self.app_state.get('token', ''))
        
        screen.navigate_to(TargetScreen)
        
        # New screen should have been created with same app_state
        page.add.assert_called()
    
    def test_navigate_to_with_kwargs(self):
        """Test navigate_to() passes kwargs to show()."""
        page = Mock(spec=ft.Page)
        page.controls = []
        page.overlay = []
        app_state = {}
        screen = TestScreen(page, app_state)
        
        class TargetScreen(BaseScreen):
            def build(self) -> ft.Control:
                return ft.Text("Target")
        
        screen.navigate_to(TargetScreen, show_back=True, progress_text="Step 2/5")
        
        # Verify show was called with kwargs
        page.add.assert_called()
    
    def test_navigate_to_invalid_class(self):
        """Test navigate_to() raises TypeError for non-BaseScreen class."""
        page = Mock(spec=ft.Page)
        app_state = {}
        screen = TestScreen(page, app_state)
        
        class NotAScreen:
            pass
        
        with pytest.raises(TypeError, match="must be a subclass of BaseScreen"):
            screen.navigate_to(NotAScreen)
    
    def test_handle_back_default_behavior(self):
        """Test _handle_back() default behavior (logs warning)."""
        page = Mock(spec=ft.Page)
        app_state = {}
        screen = TestScreen(page, app_state)
        
        # Should not raise error, just log warning
        screen._handle_back(None)


class TestBaseScreenDialogs:
    """Test BaseScreen dialog methods."""
    
    def test_show_error_creates_alert_dialog(self):
        """Test show_error() creates and displays alert dialog."""
        page = Mock(spec=ft.Page)
        page.overlay = []
        app_state = {}
        screen = TestScreen(page, app_state)
        
        screen.show_error("Test error message")
        
        assert len(page.overlay) == 1
        dialog = page.overlay[0]
        assert isinstance(dialog, ft.AlertDialog)
        assert dialog.modal is True
        assert dialog.open is True
    
    def test_show_error_custom_title(self):
        """Test show_error() with custom title."""
        page = Mock(spec=ft.Page)
        page.overlay = []
        app_state = {}
        screen = TestScreen(page, app_state)
        
        screen.show_error("Network error", title="Connection Failed")
        
        dialog = page.overlay[0]
        assert "Connection Failed" in dialog.title.value
    
    def test_show_error_updates_page(self):
        """Test show_error() updates page."""
        page = Mock(spec=ft.Page)
        page.overlay = []
        app_state = {}
        screen = TestScreen(page, app_state)
        
        screen.show_error("Error")
        
        page.update.assert_called()
    
    def test_show_success_creates_alert_dialog(self):
        """Test show_success() creates and displays alert dialog."""
        page = Mock(spec=ft.Page)
        page.overlay = []
        app_state = {}
        screen = TestScreen(page, app_state)
        
        screen.show_success("Operation completed")
        
        assert len(page.overlay) == 1
        dialog = page.overlay[0]
        assert isinstance(dialog, ft.AlertDialog)
        assert dialog.open is True
    
    def test_show_success_custom_title(self):
        """Test show_success() with custom title."""
        page = Mock(spec=ft.Page)
        page.overlay = []
        app_state = {}
        screen = TestScreen(page, app_state)
        
        screen.show_success("Migration complete", title="Done!")
        
        dialog = page.overlay[0]
        assert "Done!" in dialog.title.value
    
    def test_show_confirmation_creates_dialog(self):
        """Test show_confirmation() creates dialog with two buttons."""
        page = Mock(spec=ft.Page)
        page.overlay = []
        app_state = {}
        screen = TestScreen(page, app_state)
        
        screen.show_confirmation("Are you sure?")
        
        assert len(page.overlay) == 1
        dialog = page.overlay[0]
        assert isinstance(dialog, ft.AlertDialog)
        assert len(dialog.actions) == 2  # Cancel and Confirm
    
    def test_show_confirmation_calls_on_confirm(self):
        """Test show_confirmation() calls on_confirm callback."""
        page = Mock(spec=ft.Page)
        page.overlay = []
        app_state = {}
        screen = TestScreen(page, app_state)
        
        on_confirm = Mock()
        screen.show_confirmation("Confirm?", on_confirm=on_confirm)
        
        dialog = page.overlay[0]
        # Simulate clicking confirm button
        confirm_button = dialog.actions[1]
        confirm_button.on_click(None)
        
        on_confirm.assert_called_once()
    
    def test_show_confirmation_calls_on_cancel(self):
        """Test show_confirmation() calls on_cancel callback."""
        page = Mock(spec=ft.Page)
        page.overlay = []
        app_state = {}
        screen = TestScreen(page, app_state)
        
        on_cancel = Mock()
        screen.show_confirmation("Confirm?", on_cancel=on_cancel)
        
        dialog = page.overlay[0]
        # Simulate clicking cancel button
        cancel_button = dialog.actions[0]
        cancel_button.on_click(None)
        
        on_cancel.assert_called_once()
    
    def test_show_confirmation_custom_button_text(self):
        """Test show_confirmation() with custom button text."""
        page = Mock(spec=ft.Page)
        page.overlay = []
        app_state = {}
        screen = TestScreen(page, app_state)
        
        screen.show_confirmation(
            "Delete?",
            confirm_text="Delete",
            cancel_text="Keep"
        )
        
        dialog = page.overlay[0]
        assert dialog.actions[0].text == "Keep"
        assert dialog.actions[1].text == "Delete"


class TestBaseScreenLoading:
    """Test BaseScreen loading overlay."""
    
    def test_show_loading_creates_overlay(self):
        """Test show_loading() creates loading overlay."""
        page = Mock(spec=ft.Page)
        page.overlay = []
        app_state = {}
        screen = TestScreen(page, app_state)
        
        screen.show_loading(True)
        
        assert len(page.overlay) == 1
        assert screen._loading_overlay is not None
    
    def test_show_loading_custom_message(self):
        """Test show_loading() with custom message."""
        page = Mock(spec=ft.Page)
        page.overlay = []
        app_state = {}
        screen = TestScreen(page, app_state)
        
        screen.show_loading(True, "Fetching playlists...")
        
        overlay = page.overlay[0]
        # Check that message is in overlay
        message_text = overlay.content.controls[2]
        assert isinstance(message_text, ft.Text)
        assert message_text.value == "Fetching playlists..."
    
    def test_show_loading_hides_overlay(self):
        """Test show_loading(False) removes overlay."""
        page = Mock(spec=ft.Page)
        page.overlay = []
        app_state = {}
        screen = TestScreen(page, app_state)
        
        # Show then hide
        screen.show_loading(True)
        assert len(page.overlay) == 1
        
        screen.show_loading(False)
        assert len(page.overlay) == 0
    
    def test_show_loading_updates_message(self):
        """Test show_loading() updates message on subsequent calls."""
        page = Mock(spec=ft.Page)
        page.overlay = []
        app_state = {}
        screen = TestScreen(page, app_state)
        
        screen.show_loading(True, "Loading...")
        first_overlay = page.overlay[0]
        
        screen.show_loading(True, "Processing...")
        
        # Should reuse same overlay
        assert screen._loading_overlay is first_overlay
        # Message should be updated
        message_text = first_overlay.content.controls[2]
        assert message_text.value == "Processing..."
    
    def test_show_loading_default_message(self):
        """Test show_loading() uses default message."""
        page = Mock(spec=ft.Page)
        page.overlay = []
        app_state = {}
        screen = TestScreen(page, app_state)
        
        screen.show_loading(True)
        
        overlay = page.overlay[0]
        message_text = overlay.content.controls[2]
        assert message_text.value == "Loading..."


class TestBaseScreenUtilities:
    """Test BaseScreen utility methods."""
    
    def test_clear_overlays_removes_all_overlays(self):
        """Test clear_overlays() removes all overlays."""
        page = Mock(spec=ft.Page)
        page.overlay = Mock()
        page.overlay.__iter__ = Mock(return_value=iter([ft.Container(), ft.Container(), ft.Container()]))
        app_state = {}
        screen = TestScreen(page, app_state)
        
        screen.clear_overlays()
        
        page.overlay.clear.assert_called_once()
    
    def test_clear_overlays_resets_loading_overlay(self):
        """Test clear_overlays() resets loading overlay reference."""
        page = Mock(spec=ft.Page)
        page.overlay = []
        app_state = {}
        screen = TestScreen(page, app_state)
        
        # Create loading overlay
        screen.show_loading(True)
        assert screen._loading_overlay is not None
        
        # Clear
        screen.clear_overlays()
        assert screen._loading_overlay is None
    
    def test_clear_overlays_updates_page(self):
        """Test clear_overlays() updates page."""
        page = Mock(spec=ft.Page)
        page.overlay = []
        app_state = {}
        screen = TestScreen(page, app_state)
        
        screen.clear_overlays()
        
        page.update.assert_called()


class TestBaseScreenConstants:
    """Test BaseScreen constants."""
    
    def test_fade_in_duration_constant(self):
        """Test FADE_IN_DURATION is set correctly."""
        assert BaseScreen.FADE_IN_DURATION == 300
    
    def test_fade_in_duration_used_in_show(self):
        """Test FADE_IN_DURATION is used in show() animation."""
        page = Mock(spec=ft.Page)
        page.controls = []
        page.overlay = []
        app_state = {}
        screen = TestScreen(page, app_state)
        
        screen.show()
        
        added_control = page.add.call_args[0][0]
        content_container = added_control.controls[2]
        assert content_container.animate_opacity == BaseScreen.FADE_IN_DURATION


class TestBaseScreenIntegration:
    """Integration tests for BaseScreen."""
    
    def test_full_navigation_flow(self):
        """Test complete navigation flow between screens."""
        page = Mock(spec=ft.Page)
        page.controls = Mock()
        page.overlay = []
        app_state = {'step': 1}
        
        # First screen
        screen1 = TestScreen(page, app_state)
        screen1.show()
        
        # Navigate to second screen
        class SecondScreen(BaseScreen):
            def build(self) -> ft.Control:
                return ft.Text(f"Step {self.app_state['step']}")
        
        app_state['step'] = 2
        screen1.navigate_to(SecondScreen, show_back=True, progress_text="Step 2/5")
        
        # Verify navigation happened
        assert page.controls.clear.call_count >= 2
        assert page.add.call_count >= 2
    
    def test_error_dialog_flow(self):
        """Test showing and dismissing error dialog."""
        page = Mock(spec=ft.Page)
        page.overlay = []
        app_state = {}
        screen = TestScreen(page, app_state)
        
        # Show error
        screen.show_error("Test error")
        assert len(page.overlay) == 1
        
        # Simulate dismissal
        dialog = page.overlay[0]
        ok_button = dialog.actions[0]
        ok_button.on_click(None)
        
        assert dialog.open is False
    
    def test_loading_overlay_flow(self):
        """Test showing and hiding loading overlay."""
        page = Mock(spec=ft.Page)
        page.overlay = []
        app_state = {}
        screen = TestScreen(page, app_state)
        
        # Show loading
        screen.show_loading(True, "Processing...")
        assert len(page.overlay) == 1
        
        # Hide loading
        screen.show_loading(False)
        assert len(page.overlay) == 0
    
    def test_multiple_overlays(self):
        """Test multiple overlays can coexist."""
        page = Mock(spec=ft.Page)
        page.overlay = []
        app_state = {}
        screen = TestScreen(page, app_state)
        
        # Show loading
        screen.show_loading(True)
        assert len(page.overlay) == 1
        
        # Show error (should add to overlay, not replace)
        screen.show_error("Error")
        assert len(page.overlay) == 2
        
        # Clear all
        screen.clear_overlays()
        assert len(page.overlay) == 0


class TestBaseScreenConfigIntegration:
    """Test BaseScreen integration with app_config."""
    
    def test_uses_config_colors(self):
        """Test BaseScreen uses colors from app_config."""
        page = Mock(spec=ft.Page)
        page.controls = []
        page.overlay = []
        app_state = {}
        screen = TestScreen(page, app_state)
        
        # Show error dialog
        screen.show_error("Error")
        
        dialog = page.overlay[0]
        # Title should use error color
        assert app_config.ERROR_COLOR in str(dialog.title.color)
    
    def test_uses_config_sizes(self):
        """Test BaseScreen uses sizes from app_config."""
        page = Mock(spec=ft.Page)
        page.controls = []
        page.overlay = []
        app_state = {}
        screen = TestScreen(page, app_state)
        
        screen.show(progress_text="Step 1/5")
        
        added_control = page.add.call_args[0][0]
        header = added_control.controls[0]
        progress_text = header.controls[-1]
        assert progress_text.size == app_config.CAPTION_SIZE
    
    def test_uses_config_primary_color(self):
        """Test BaseScreen uses PRIMARY_COLOR from config."""
        page = Mock(spec=ft.Page)
        page.controls = []
        page.overlay = []
        app_state = {}
        screen = TestScreen(page, app_state)
        
        screen.show(show_back=True)
        
        added_control = page.add.call_args[0][0]
        header = added_control.controls[0]
        back_button = header.controls[0]
        assert back_button.icon_color == app_config.PRIMARY_COLOR
