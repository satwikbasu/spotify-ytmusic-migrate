# Spotify to YouTube Music Playlist Migrator - Main Entry Point

import flet as ft


def main(page: ft.Page):
    """Main application entry point."""
    # Configure the application window
    page.title = "Playlist Migrator"
    page.window_width = 800
    page.window_height = 600
    page.window_resizable = False
    
    # Add welcome message
    page.add(
        ft.Text("Welcome to Playlist Migrator")
    )


if __name__ == "__main__":
    ft.app(target=main)
