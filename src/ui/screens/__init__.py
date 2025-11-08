"""UI Screens Package.

This package contains all application screens that inherit from BaseScreen.

Available screens:
    - WelcomeScreen: Authentication screen for Spotify and YouTube Music
    - MigrationProgressScreen: Real-time migration progress monitoring
    - ResultsScreen: Migration completion summary and results
    - SettingsScreen: Application preferences and configuration
"""

from src.ui.screens.welcome_screen import WelcomeScreen
from src.ui.screens.migration_progress_screen import MigrationProgressScreen
from src.ui.screens.results_screen import ResultsScreen
from src.ui.screens.settings_screen import SettingsScreen

__all__ = ['WelcomeScreen', 'MigrationProgressScreen', 'ResultsScreen', 'SettingsScreen']
