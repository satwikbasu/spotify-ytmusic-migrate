"""
Settings screen for user preferences configuration.

This module provides a comprehensive settings interface for customizing the
playlist migration application's behavior, including match thresholds,
notifications, theme preferences, cache management, and advanced options.
"""

import json
import os
import webbrowser
from pathlib import Path
from typing import Dict, Any, Optional

import flet as ft

from src.ui.base_screen import BaseScreen
from config import app_config


class SettingsScreen(BaseScreen):
    """
    Settings screen for configuring application preferences.

    Provides controls for:
    - Match threshold adjustment
    - Notification preferences
    - Theme selection
    - Cache management
    - Advanced settings (rate limits, daily operation limits)
    - About information and data reset

    Attributes:
        settings (dict): Current settings loaded from file or defaults
        settings_file (Path): Path to settings.json file
        match_threshold_slider (ft.Slider): Slider for match threshold
        match_threshold_text (ft.Text): Text showing current threshold value
        notifications_switch (ft.Switch): Toggle for notifications
        theme_radio (ft.RadioGroup): Radio group for theme selection
        cache_size_text (ft.Text): Text showing current cache size
        advanced_section (ft.Container): Collapsible advanced settings section
    """

    SETTINGS_FILE = Path(app_config.APP_DATA_DIR) / "settings.json"
    DEFAULT_SETTINGS = {
        "match_threshold": 75,
        "notifications_enabled": True,
        "theme": "system",  # light, dark, system
        "rate_limit_delay": 0.5,
        "daily_operation_limit": 10000,
    }

    def __init__(self, page: ft.Page, app_state: Dict[str, Any]):
        """
        Initialize the settings screen.

        Args:
            page: The Flet page instance
            app_state: Shared application state dictionary
        """
        super().__init__(page, app_state)
        self.settings = self.load_settings()
        
        # UI component references
        self.match_threshold_slider: Optional[ft.Slider] = None
        self.match_threshold_text: Optional[ft.Text] = None
        self.notifications_switch: Optional[ft.Switch] = None
        self.theme_radio: Optional[ft.RadioGroup] = None
        self.cache_size_text: Optional[ft.Text] = None
        self.advanced_section: Optional[ft.Container] = None
        self.advanced_expanded: bool = False

    def load_settings(self) -> Dict[str, Any]:
        """
        Load settings from JSON file.

        Returns:
            Dictionary containing settings. Returns default values if file
            doesn't exist or can't be loaded.
        """
        try:
            if self.SETTINGS_FILE.exists():
                with open(self.SETTINGS_FILE, 'r', encoding='utf-8') as f:
                    loaded_settings = json.load(f)
                    # Merge with defaults to ensure all keys exist
                    return {**self.DEFAULT_SETTINGS, **loaded_settings}
            return self.DEFAULT_SETTINGS.copy()
        except Exception as e:
            print(f"Error loading settings: {e}")
            return self.DEFAULT_SETTINGS.copy()

    def save_settings(self) -> None:
        """
        Save current settings to JSON file and apply changes.

        Creates the settings directory if it doesn't exist.
        """
        try:
            # Ensure directory exists
            self.SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
            
            # Save to file
            with open(self.SETTINGS_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.settings, f, indent=2)
            
            # Apply theme change immediately
            self._apply_theme()
            
            # Show success message
            self.show_success("Settings saved successfully!")
            
        except Exception as e:
            self.show_error(f"Failed to save settings: {str(e)}")

    def _apply_theme(self) -> None:
        """Apply the selected theme to the page."""
        theme = self.settings.get("theme", "system")
        if theme == "light":
            self.page.theme_mode = ft.ThemeMode.LIGHT
        elif theme == "dark":
            self.page.theme_mode = ft.ThemeMode.DARK
        else:  # system
            self.page.theme_mode = ft.ThemeMode.SYSTEM
        self.page.update()

    def get_cache_size(self) -> str:
        """
        Calculate and format the cache directory size.

        Returns:
            Formatted string representing cache size (e.g., "2.5 MB")
        """
        try:
            cache_manager = self.app_state.get('cache_manager')
            if not cache_manager or not hasattr(cache_manager, 'db_path'):
                return "Unknown"
            
            db_path = Path(cache_manager.db_path)
            if not db_path.exists():
                return "0 KB"
            
            size_bytes = db_path.stat().st_size
            
            # Convert to appropriate unit
            if size_bytes < 1024:
                return f"{size_bytes} B"
            elif size_bytes < 1024 * 1024:
                return f"{size_bytes / 1024:.1f} KB"
            elif size_bytes < 1024 * 1024 * 1024:
                return f"{size_bytes / (1024 * 1024):.1f} MB"
            else:
                return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"
        except Exception as e:
            print(f"Error calculating cache size: {e}")
            return "Unknown"

    def build(self) -> ft.Control:
        """
        Build the settings screen UI.

        Returns:
            The root control for the settings screen
        """
        # Match Threshold Section
        self.match_threshold_slider = ft.Slider(
            min=60,
            max=95,
            divisions=35,
            value=self.settings["match_threshold"],
            label="{value}%",
            on_change=self.on_match_threshold_change,
            active_color=app_config.PRIMARY_COLOR,
        )
        
        self.match_threshold_text = ft.Text(
            f"{self.settings['match_threshold']}%",
            size=app_config.HEADING_SIZE_LARGE,
            weight=ft.FontWeight.BOLD,
            color=app_config.PRIMARY_COLOR,
        )
        
        match_threshold_section = ft.Container(
            content=ft.Column([
                ft.Text(
                    "Match Threshold",
                    size=app_config.HEADING_SIZE_LARGE,
                    weight=ft.FontWeight.BOLD,
                ),
                ft.Text(
                    "Minimum similarity score required to match tracks",
                    size=app_config.CAPTION_SIZE,
                    color=app_config.TEXT_COLOR_LIGHT,
                ),
                ft.Row([
                    ft.Container(
                        content=self.match_threshold_slider,
                        expand=True,
                    ),
                    self.match_threshold_text,
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            ], spacing=10),
            padding=20,
            bgcolor="#1E1E1E",
            border_radius=10,
        )

        # Notifications Section
        self.notifications_switch = ft.Switch(
            value=self.settings["notifications_enabled"],
            on_change=self.on_notifications_change,
            active_color=app_config.PRIMARY_COLOR,
        )
        
        notifications_section = ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Column([
                        ft.Text(
                            "Desktop Notifications",
                            size=app_config.HEADING_SIZE_LARGE,
                            weight=ft.FontWeight.BOLD,
                        ),
                        ft.Text(
                            "Receive notifications when migrations complete",
                            size=app_config.CAPTION_SIZE,
                            color=app_config.TEXT_COLOR_LIGHT,
                        ),
                    ], expand=True),
                    self.notifications_switch,
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            ], spacing=10),
            padding=20,
            bgcolor="#1E1E1E",
            border_radius=10,
        )

        # Theme Section
        self.theme_radio = ft.RadioGroup(
            content=ft.Column([
                ft.Radio(value="light", label="Light"),
                ft.Radio(value="dark", label="Dark"),
                ft.Radio(value="system", label="System (Auto)"),
            ], spacing=10),
            value=self.settings["theme"],
            on_change=self.on_theme_change,
        )
        
        theme_section = ft.Container(
            content=ft.Column([
                ft.Text(
                    "Theme",
                    size=app_config.HEADING_SIZE_LARGE,
                    weight=ft.FontWeight.BOLD,
                ),
                ft.Text(
                    "Choose your preferred color theme",
                    size=app_config.CAPTION_SIZE,
                    color=app_config.TEXT_COLOR_LIGHT,
                ),
                self.theme_radio,
            ], spacing=10),
            padding=20,
            bgcolor="#1E1E1E",
            border_radius=10,
        )

        # Cache Management Section
        self.cache_size_text = ft.Text(
            f"Cache size: {self.get_cache_size()}",
            size=app_config.BODY_SIZE,
            color=app_config.TEXT_COLOR_LIGHT,
        )
        
        cache_section = ft.Container(
            content=ft.Column([
                ft.Text(
                    "Cache Management",
                    size=app_config.HEADING_SIZE_LARGE,
                    weight=ft.FontWeight.BOLD,
                ),
                ft.Text(
                    "Clear cached data to free up space",
                    size=app_config.CAPTION_SIZE,
                    color=app_config.TEXT_COLOR_LIGHT,
                ),
                self.cache_size_text,
                ft.ElevatedButton(
                    "Clear Cache",
                    icon=ft.Icons.DELETE_OUTLINE,
                    on_click=self.on_clear_cache_click,
                    bgcolor=app_config.ERROR_COLOR,
                    color="white",
                ),
            ], spacing=10),
            padding=20,
            bgcolor="#1E1E1E",
            border_radius=10,
        )

        # Advanced Section (Collapsible)
        advanced_content = ft.Column([
            ft.Text(
                "Rate Limit Delay",
                size=app_config.BODY_SIZE,
                weight=ft.FontWeight.BOLD,
            ),
            ft.Text(
                "Delay between API requests (seconds)",
                size=app_config.CAPTION_SIZE,
                color=app_config.TEXT_COLOR_LIGHT,
            ),
            ft.TextField(
                value=str(self.settings["rate_limit_delay"]),
                keyboard_type=ft.KeyboardType.NUMBER,
                on_change=lambda e: self.on_rate_limit_change(e),
                width=200,
            ),
            ft.Divider(height=20, color=app_config.TEXT_COLOR_LIGHT),
            ft.Text(
                "Daily Operation Limit",
                size=app_config.BODY_SIZE,
                weight=ft.FontWeight.BOLD,
            ),
            ft.Text(
                "Maximum API operations per day",
                size=app_config.CAPTION_SIZE,
                color=app_config.TEXT_COLOR_LIGHT,
            ),
            ft.TextField(
                value=str(self.settings["daily_operation_limit"]),
                keyboard_type=ft.KeyboardType.NUMBER,
                on_change=lambda e: self.on_daily_limit_change(e),
                width=200,
            ),
        ], spacing=10)
        
        self.advanced_section = ft.Container(
            content=ft.Column([
                ft.TextButton(
                    "Advanced Settings",
                    icon=ft.Icons.ARROW_DROP_DOWN if not self.advanced_expanded else ft.Icons.ARROW_DROP_UP,
                    on_click=self.on_toggle_advanced,
                ),
                ft.Container(
                    content=advanced_content,
                    visible=self.advanced_expanded,
                ),
            ], spacing=10),
            padding=20,
            bgcolor="#1E1E1E",
            border_radius=10,
        )

        # About Section
        about_section = ft.Container(
            content=ft.Column([
                ft.Text(
                    "About",
                    size=app_config.HEADING_SIZE_LARGE,
                    weight=ft.FontWeight.BOLD,
                ),
                ft.Text(
                    "Spotify to YouTube Music Migrator",
                    size=app_config.BODY_SIZE,
                ),
                ft.Text(
                    "Version 1.0.0",
                    size=app_config.CAPTION_SIZE,
                    color=app_config.TEXT_COLOR_LIGHT,
                ),
                ft.Row([
                    ft.TextButton(
                        "Documentation",
                        icon=ft.Icons.DESCRIPTION_OUTLINED,
                        on_click=lambda _: webbrowser.open("https://github.com/yourusername/playlist-migrator"),
                    ),
                    ft.TextButton(
                        "GitHub",
                        icon=ft.Icons.CODE,
                        on_click=lambda _: webbrowser.open("https://github.com/yourusername/playlist-migrator"),
                    ),
                ], spacing=10),
                ft.Divider(height=20, color=app_config.TEXT_COLOR_LIGHT),
                ft.ElevatedButton(
                    "Clear All Data & Reset",
                    icon=ft.Icons.WARNING_OUTLINED,
                    on_click=self.on_reset_click,
                    bgcolor=app_config.ERROR_COLOR,
                    color="white",
                ),
            ], spacing=10),
            padding=20,
            bgcolor="#1E1E1E",
            border_radius=10,
        )

        # Save Button
        save_button = ft.Container(
            content=ft.ElevatedButton(
                "Save Settings",
                icon=ft.Icons.SAVE,
                on_click=self.on_save_click,
                bgcolor=app_config.PRIMARY_COLOR,
                color="white",
                width=200,
                height=45,
            ),
            alignment=ft.alignment.center,
            padding=20,
        )

        # Main content
        content = ft.Column(
            [
                ft.Container(
                    content=ft.Text(
                        "Settings",
                        size=32,
                        weight=ft.FontWeight.BOLD,
                    ),
                    padding=ft.padding.only(bottom=20),
                ),
                match_threshold_section,
                notifications_section,
                theme_section,
                cache_section,
                self.advanced_section,
                about_section,
                save_button,
            ],
            spacing=15,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )

        return ft.Container(
            content=content,
            padding=20,
            expand=True,
        )

    def on_match_threshold_change(self, e) -> None:
        """Handle match threshold slider change."""
        value = int(e.control.value)
        self.settings["match_threshold"] = value
        if self.match_threshold_text:
            self.match_threshold_text.value = f"{value}%"
            self.page.update()

    def on_notifications_change(self, e) -> None:
        """Handle notifications switch change."""
        self.settings["notifications_enabled"] = e.control.value

    def on_theme_change(self, e) -> None:
        """Handle theme radio button change."""
        self.settings["theme"] = e.control.value

    def on_rate_limit_change(self, e) -> None:
        """Handle rate limit delay text field change."""
        try:
            value = float(e.control.value)
            if value >= 0:
                self.settings["rate_limit_delay"] = value
        except ValueError:
            pass

    def on_daily_limit_change(self, e) -> None:
        """Handle daily operation limit text field change."""
        try:
            value = int(e.control.value)
            if value > 0:
                self.settings["daily_operation_limit"] = value
        except ValueError:
            pass

    def on_toggle_advanced(self, e) -> None:
        """Toggle the advanced settings section visibility."""
        self.advanced_expanded = not self.advanced_expanded
        
        if self.advanced_section:
            # Update icon
            button = self.advanced_section.content.controls[0]
            button.icon = ft.Icons.ARROW_DROP_UP if self.advanced_expanded else ft.Icons.ARROW_DROP_DOWN
            
            # Toggle visibility
            container = self.advanced_section.content.controls[1]
            container.visible = self.advanced_expanded
            
            self.page.update()

    def on_save_click(self, e) -> None:
        """Handle save button click."""
        self.save_settings()

    def on_clear_cache_click(self, e) -> None:
        """Handle clear cache button click with confirmation."""
        def handle_confirm(confirmed: bool) -> None:
            if confirmed:
                try:
                    cache_manager = self.app_state.get('cache_manager')
                    if cache_manager:
                        # Clear cache
                        if hasattr(cache_manager, 'clear_cache'):
                            cache_manager.clear_cache()
                        
                        # Update cache size display
                        if self.cache_size_text:
                            self.cache_size_text.value = f"Cache size: {self.get_cache_size()}"
                            self.page.update()
                        
                        self.show_success("Cache cleared successfully!")
                    else:
                        self.show_error("Cache manager not available")
                except Exception as ex:
                    self.show_error(f"Failed to clear cache: {str(ex)}")
        
        self.show_confirmation(
            message="Are you sure you want to clear the cache? This will remove all cached playlist and track data.",
            on_confirm=lambda: handle_confirm(True),
            on_cancel=lambda: handle_confirm(False),
            confirm_text="Clear Cache",
            cancel_text="Cancel",
        )

    def on_reset_click(self, e) -> None:
        """Handle reset button click with warning confirmation."""
        def handle_confirm(confirmed: bool) -> None:
            if confirmed:
                try:
                    # Clear cache
                    cache_manager = self.app_state.get('cache_manager')
                    if cache_manager and hasattr(cache_manager, 'clear_cache'):
                        cache_manager.clear_cache()
                    
                    # Clear tokens
                    token_manager = self.app_state.get('token_manager')
                    if token_manager:
                        if hasattr(token_manager, 'clear_spotify_token'):
                            token_manager.clear_spotify_token()
                        if hasattr(token_manager, 'clear_youtube_token'):
                            token_manager.clear_youtube_token()
                    
                    # Reset settings to defaults
                    self.settings = self.DEFAULT_SETTINGS.copy()
                    try:
                        if self.SETTINGS_FILE.exists():
                            self.SETTINGS_FILE.unlink()
                    except Exception:
                        pass
                    
                    # Clear app state
                    self.app_state['spotify_client'] = None
                    self.app_state['youtube_client'] = None
                    self.app_state['token_manager'] = None
                    self.app_state['selected_playlists'] = []
                    self.app_state['migration_results'] = {}
                    self.app_state['playlist_results'] = []
                    
                    # Navigate to welcome screen
                    from src.ui.screens.welcome_screen import WelcomeScreen
                    self.navigate_to(WelcomeScreen)
                    
                    self.show_success("All data cleared. Application reset successfully!")
                    
                except Exception as ex:
                    self.show_error(f"Failed to reset application: {str(ex)}")
        
        self.show_confirmation(
            message="⚠️ WARNING: This will permanently delete all cached data, authentication tokens, and settings. You will need to reconnect your accounts. Are you sure?",
            on_confirm=lambda: handle_confirm(True),
            on_cancel=lambda: handle_confirm(False),
            confirm_text="Reset Everything",
            cancel_text="Cancel",
        )
