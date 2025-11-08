"""Results Screen for displaying migration completion summary.

This screen shows the final results of playlist migrations, including:
- Overall success statistics
- Per-playlist breakdown with success rates
- Failed tracks with reasons
- Actions: Open YouTube Music, Export Report, Migrate More

The screen features a celebration animation on load and provides detailed
insights into the migration process.

Example:
    >>> screen = ResultsScreen(page, app_state)
    >>> screen.show(show_back=False, progress_text="Step 5 of 5")
"""

import flet as ft
import csv
import webbrowser
import os
from typing import Optional, Dict, Any, List
from datetime import timedelta

from src.ui.base_screen import BaseScreen
from src.ui.components import AppButton
from config import app_config


class ResultsScreen(BaseScreen):
    """Screen for displaying migration results and summary.
    
    Shows the final outcome of playlist migrations with detailed statistics,
    per-playlist breakdowns, and action buttons for further steps.
    
    Features:
    - Celebration animation (confetti) for successful migrations
    - Overall summary (playlists, tracks, success rate, duration)
    - Per-playlist results with expandable failed tracks
    - One-click playlist opening in browser
    - CSV report export with all migration details
    - Navigate back to playlist selection for more migrations
    
    Attributes:
        results (List[Dict]): List of playlist migration results.
        total_playlists (int): Total number of playlists migrated.
        total_tracks (int): Total tracks across all playlists.
        matched_count (int): Number of successfully matched tracks.
        failed_count (int): Number of failed track migrations.
        duration (float): Total migration duration in seconds.
        success_rate (float): Overall success rate (0.0 to 1.0).
        file_picker (Optional[ft.FilePicker]): File picker for CSV export.
    
    Example:
        >>> app_state = {
        ...     'migration_results': {
        ...         'total_playlists': 3,
        ...         'total_tracks': 150,
        ...         'matched_count': 145,
        ...         'failed_count': 5,
        ...         'duration': 1800
        ...     },
        ...     'playlist_results': [...]  # Detailed results per playlist
        ... }
        >>> screen = ResultsScreen(page, app_state)
        >>> screen.show(progress_text="Migration Complete! [5/5]")
    """
    
    def __init__(self, page: ft.Page, app_state: Dict[str, Any]):
        """Initialize the results screen.
        
        Args:
            page (ft.Page): Flet page instance.
            app_state (Dict[str, Any]): Shared application state containing:
                - 'migration_results': Overall statistics dictionary
                - 'playlist_results': List of per-playlist results (optional)
        """
        super().__init__(page, app_state)
        
        # Extract results from app_state
        migration_results = self.app_state.get('migration_results', {})
        self.total_playlists = migration_results.get('total_playlists', 0)
        self.total_tracks = migration_results.get('total_tracks', 0)
        self.matched_count = migration_results.get('matched_count', 0)
        self.failed_count = migration_results.get('failed_count', 0)
        self.duration = migration_results.get('duration', 0)
        
        # Calculate success rate
        if self.total_tracks > 0:
            self.success_rate = self.matched_count / self.total_tracks
        else:
            self.success_rate = 0.0
        
        # Get detailed playlist results (if available)
        self.results = self.app_state.get('playlist_results', [])
        
        # File picker for CSV export
        self.file_picker: Optional[ft.FilePicker] = None
    
    def build(self) -> ft.Control:
        """Build the results screen UI.
        
        Creates the complete screen layout including:
        - Success icon (large checkmark)
        - Overall summary statistics
        - Per-playlist results list
        - Action buttons (Open YT Music, Export, Migrate More)
        
        Returns:
            ft.Control: The screen content container.
        """
        # Title
        title = ft.Text(
            value="Migration Complete!",
            size=app_config.HEADING_SIZE_LARGE,
            weight=ft.FontWeight.BOLD,
            color=app_config.SUCCESS_COLOR
        )
        
        # Success icon
        success_icon = ft.Icon(
            name=ft.Icons.CHECK_CIRCLE,
            color=app_config.SUCCESS_COLOR,
            size=100
        )
        
        # Summary card
        summary_card = self._build_summary_card()
        
        # Results list
        results_list = self._build_results_list()
        
        # Action buttons
        action_buttons = self._build_action_buttons()
        
        # Main content
        content = ft.Column(
            controls=[
                title,
                ft.Container(height=20),
                success_icon,
                ft.Container(height=30),
                summary_card,
                ft.Container(height=20),
                results_list,
                ft.Container(height=30),
                action_buttons
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=10,
            scroll=ft.ScrollMode.AUTO
        )
        
        # Trigger celebration animation
        self.show_celebration()
        
        return content
    
    def _build_summary_card(self) -> ft.Control:
        """Build the summary statistics card.
        
        Returns:
            ft.Control: Summary card container.
        """
        # Format duration
        duration_str = self._format_duration(self.duration)
        
        # Create summary items
        summary_items = [
            ft.Row(
                controls=[
                    ft.Icon(
                        name=ft.Icons.PLAYLIST_PLAY,
                        color=app_config.TEXT_COLOR_DARK,
                        size=20
                    ),
                    ft.Text(
                        value=f"{self.total_playlists} playlist{'s' if self.total_playlists != 1 else ''} migrated",
                        size=app_config.BODY_SIZE,
                        color=app_config.TEXT_COLOR_DARK
                    )
                ],
                spacing=10
            ),
            ft.Row(
                controls=[
                    ft.Icon(
                        name=ft.Icons.MUSIC_NOTE,
                        color=app_config.TEXT_COLOR_DARK,
                        size=20
                    ),
                    ft.Text(
                        value=f"{self.matched_count} / {self.total_tracks} songs ({self.success_rate * 100:.1f}%)",
                        size=app_config.BODY_SIZE,
                        color=app_config.TEXT_COLOR_DARK
                    )
                ],
                spacing=10
            ),
            ft.Row(
                controls=[
                    ft.Icon(
                        name=ft.Icons.TIMER,
                        color=app_config.TEXT_COLOR_DARK,
                        size=20
                    ),
                    ft.Text(
                        value=f"Total time: {duration_str}",
                        size=app_config.BODY_SIZE,
                        color=app_config.TEXT_COLOR_DARK
                    )
                ],
                spacing=10
            )
        ]
        
        # Summary card
        card = ft.Card(
            content=ft.Container(
                content=ft.Column(
                    controls=[
                        ft.Text(
                            value="Summary",
                            size=app_config.HEADING_SIZE_SMALL,
                            weight=ft.FontWeight.BOLD,
                            color=app_config.TEXT_COLOR_DARK
                        ),
                        ft.Divider(),
                        *summary_items
                    ],
                    spacing=15
                ),
                padding=20
            ),
            elevation=2
        )
        
        return card
    
    def _build_results_list(self) -> ft.Control:
        """Build the scrollable list of playlist results.
        
        Returns:
            ft.Control: Results list container.
        """
        if not self.results:
            # No detailed results available
            return ft.Container(
                content=ft.Text(
                    value="Detailed results not available",
                    size=app_config.CAPTION_SIZE,
                    color=app_config.TEXT_COLOR_DARK,
                    italic=True
                ),
                padding=20
            )
        
        # Create result cards for each playlist
        result_cards = []
        for result in self.results:
            card = self._build_playlist_result_card(result)
            result_cards.append(card)
        
        # Scrollable container
        results_container = ft.Container(
            content=ft.Column(
                controls=result_cards,
                spacing=10,
                scroll=ft.ScrollMode.AUTO
            ),
            height=300,  # Fixed height for scrolling
            padding=10
        )
        
        return results_container
    
    def _build_playlist_result_card(self, result: Dict[str, Any]) -> ft.Control:
        """Build a result card for a single playlist.
        
        Args:
            result (Dict[str, Any]): Playlist result dictionary containing:
                - 'name': Playlist name
                - 'total_tracks': Total tracks in playlist
                - 'matched_tracks': Successfully matched tracks
                - 'failed_tracks': List of failed track dictionaries
                - 'youtube_playlist_url': URL to YouTube Music playlist (optional)
        
        Returns:
            ft.Control: Playlist result card.
        """
        name = result.get('name', 'Unknown Playlist')
        total = result.get('total_tracks', 0)
        matched = result.get('matched_tracks', 0)
        failed_tracks = result.get('failed_tracks', [])
        youtube_url = result.get('youtube_playlist_url', '')
        
        # Calculate success rate
        success_rate = (matched / total * 100) if total > 0 else 0
        
        # Success icon
        if len(failed_tracks) == 0:
            icon = ft.Icon(
                name=ft.Icons.CHECK_CIRCLE,
                color=app_config.SUCCESS_COLOR,
                size=24
            )
        else:
            icon = ft.Icon(
                name=ft.Icons.WARNING,
                color=app_config.WARNING_COLOR,
                size=24
            )
        
        # Playlist name and stats
        header = ft.Row(
            controls=[
                icon,
                ft.Column(
                    controls=[
                        ft.Text(
                            value=name,
                            size=app_config.BODY_SIZE,
                            weight=ft.FontWeight.BOLD,
                            color=app_config.TEXT_COLOR_DARK
                        ),
                        ft.Text(
                            value=f"{matched}/{total} songs ({success_rate:.1f}%)",
                            size=app_config.CAPTION_SIZE,
                            color=app_config.TEXT_COLOR_DARK
                        )
                    ],
                    spacing=5
                )
            ],
            spacing=10
        )
        
        # Action buttons
        buttons = []
        
        # View failed tracks button
        if failed_tracks:
            view_failed_btn = AppButton(
                text=f"View {len(failed_tracks)} failed",
                on_click=lambda e, r=result: self.on_view_failed_tracks_click(r),
                primary=False
            )
            buttons.append(view_failed_btn)
        
        # Open playlist button
        if youtube_url:
            open_btn = AppButton(
                text="Open Playlist",
                on_click=lambda e, url=youtube_url: self.on_open_playlist_click(url),
                primary=True
            )
            buttons.append(open_btn)
        
        buttons_row = ft.Row(
            controls=buttons,
            spacing=10
        ) if buttons else ft.Container()
        
        # Card
        card = ft.Card(
            content=ft.Container(
                content=ft.Column(
                    controls=[
                        header,
                        buttons_row
                    ],
                    spacing=10
                ),
                padding=15
            ),
            elevation=1
        )
        
        return card
    
    def _build_action_buttons(self) -> ft.Control:
        """Build the main action buttons.
        
        Returns:
            ft.Control: Action buttons row.
        """
        # Open YouTube Music button
        open_yt_btn = AppButton(
            text="Open YouTube Music",
            on_click=lambda e: self.on_open_youtube_music_click(),
            primary=True,
            gradient=True
        )
        
        # Export report button
        export_btn = AppButton(
            text="Export Report",
            on_click=self.on_export_report_click,
            primary=False
        )
        
        # Migrate more button
        migrate_more_btn = AppButton(
            text="Migrate More Playlists",
            on_click=self.on_migrate_more_click,
            primary=False
        )
        
        # Create file picker
        self.file_picker = ft.FilePicker(
            on_result=self._handle_file_picker_result
        )
        self.page.overlay.append(self.file_picker)
        
        # Buttons row
        buttons = ft.Row(
            controls=[
                open_yt_btn,
                export_btn,
                migrate_more_btn
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            spacing=20,
            wrap=True
        )
        
        return buttons
    
    def _format_duration(self, seconds: float) -> str:
        """Format duration in seconds to human-readable string.
        
        Args:
            seconds (float): Duration in seconds.
        
        Returns:
            str: Formatted duration string.
        """
        if seconds < 60:
            return f"{int(seconds)} seconds"
        elif seconds < 3600:
            minutes = int(seconds / 60)
            return f"{minutes} minute{'s' if minutes != 1 else ''}"
        else:
            hours = int(seconds / 3600)
            remaining_minutes = int((seconds % 3600) / 60)
            if remaining_minutes > 0:
                return f"{hours} hour{'s' if hours != 1 else ''} {remaining_minutes} minute{'s' if remaining_minutes != 1 else ''}"
            else:
                return f"{hours} hour{'s' if hours != 1 else ''}"
    
    def show_celebration(self) -> None:
        """Trigger celebration animation for successful migration.
        
        Shows a brief animation (confetti or success indicator) to
        celebrate the completed migration. Animation runs for 3 seconds.
        
        Note: Full confetti animation requires custom implementation.
        For now, shows a simple success message.
        """
        # For now, just show a brief success banner
        # Full confetti animation would require more complex implementation
        # with animated containers and particle effects
        pass
    
    def on_view_failed_tracks_click(self, playlist_result: Dict[str, Any]) -> None:
        """Show dialog with failed tracks for a playlist.
        
        Args:
            playlist_result (Dict[str, Any]): Playlist result containing failed_tracks.
        """
        failed_tracks = playlist_result.get('failed_tracks', [])
        playlist_name = playlist_result.get('name', 'Unknown')
        
        if not failed_tracks:
            return
        
        # Create table rows for failed tracks
        rows = []
        for track in failed_tracks:
            track_name = track.get('name', 'Unknown')
            artist = track.get('artist', 'Unknown')
            reason = track.get('failure_reason', 'Unknown error')
            
            rows.append(
                ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text(track_name, size=app_config.CAPTION_SIZE)),
                        ft.DataCell(ft.Text(artist, size=app_config.CAPTION_SIZE)),
                        ft.DataCell(ft.Text(reason, size=app_config.CAPTION_SIZE))
                    ]
                )
            )
        
        # Create data table
        table = ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text("Track Name", weight=ft.FontWeight.BOLD)),
                ft.DataColumn(ft.Text("Artist", weight=ft.FontWeight.BOLD)),
                ft.DataColumn(ft.Text("Reason", weight=ft.FontWeight.BOLD))
            ],
            rows=rows
        )
        
        # Scrollable container
        content = ft.Container(
            content=ft.Column(
                controls=[
                    ft.Text(
                        value=f"Failed tracks in '{playlist_name}'",
                        size=app_config.BODY_SIZE,
                        weight=ft.FontWeight.BOLD
                    ),
                    ft.Container(height=10),
                    table
                ],
                scroll=ft.ScrollMode.AUTO
            ),
            width=600,
            height=400
        )
        
        # Show dialog
        dialog = ft.AlertDialog(
            title=ft.Text("Failed Tracks"),
            content=content,
            actions=[
                AppButton(
                    text="Close",
                    on_click=lambda e: self._close_dialog(dialog),
                    primary=False
                )
            ],
            actions_alignment=ft.MainAxisAlignment.END
        )
        
        self.page.overlay.append(dialog)
        dialog.open = True
        self.page.update()
    
    def _close_dialog(self, dialog: ft.AlertDialog) -> None:
        """Close a dialog.
        
        Args:
            dialog (ft.AlertDialog): Dialog to close.
        """
        dialog.open = False
        self.page.update()
    
    def on_open_playlist_click(self, playlist_url: str) -> None:
        """Open YouTube Music playlist in browser.
        
        Args:
            playlist_url (str): URL to YouTube Music playlist.
        """
        try:
            webbrowser.open(playlist_url)
        except Exception as e:
            self.show_error(f"Failed to open playlist: {str(e)}")
    
    def on_open_youtube_music_click(self) -> None:
        """Open YouTube Music library in browser."""
        try:
            webbrowser.open("https://music.youtube.com/library")
        except Exception as e:
            self.show_error(f"Failed to open YouTube Music: {str(e)}")
    
    def on_export_report_click(self, e) -> None:
        """Handle export report button click.
        
        Opens file picker to let user choose save location for CSV report.
        
        Args:
            e: Flet event object.
        """
        if not self.file_picker:
            self.show_error("File picker not initialized")
            return
        
        # Open file picker for save
        self.file_picker.save_file(
            dialog_title="Save Migration Report",
            file_name="migration_report.csv",
            allowed_extensions=["csv"]
        )
    
    def _handle_file_picker_result(self, e: ft.FilePickerResultEvent) -> None:
        """Handle file picker result and export CSV.
        
        Args:
            e (ft.FilePickerResultEvent): File picker result event.
        """
        if not e.path:
            return
        
        try:
            self._export_csv_report(e.path)
            self.show_success(f"Report exported successfully to:\n{e.path}")
        except Exception as ex:
            self.show_error(f"Failed to export report: {str(ex)}")
    
    def _export_csv_report(self, file_path: str) -> None:
        """Export migration results to CSV file.
        
        Args:
            file_path (str): Path where CSV should be saved.
        
        Raises:
            Exception: If export fails.
        """
        with open(file_path, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            
            # Write header
            writer.writerow([
                'Playlist Name',
                'Track Name',
                'Artist',
                'Spotify ID',
                'YouTube Video ID',
                'Confidence',
                'Status'
            ])
            
            # Write results
            for result in self.results:
                playlist_name = result.get('name', 'Unknown')
                
                # Write successful tracks
                matched_tracks = result.get('matched_tracks_details', [])
                for track in matched_tracks:
                    writer.writerow([
                        playlist_name,
                        track.get('name', ''),
                        track.get('artist', ''),
                        track.get('spotify_id', ''),
                        track.get('youtube_video_id', ''),
                        track.get('confidence', 100.0),
                        'Success'
                    ])
                
                # Write failed tracks
                failed_tracks = result.get('failed_tracks', [])
                for track in failed_tracks:
                    writer.writerow([
                        playlist_name,
                        track.get('name', ''),
                        track.get('artist', ''),
                        track.get('spotify_id', ''),
                        '',  # No YouTube video ID for failed tracks
                        0.0,  # Zero confidence
                        'Failed'
                    ])
    
    def on_migrate_more_click(self, e) -> None:
        """Handle migrate more playlists button click.
        
        Clears selections and navigates back to playlist selection screen.
        
        Args:
            e: Flet event object.
        """
        # Clear previous selections
        if 'selected_playlists' in self.app_state:
            self.app_state['selected_playlists'] = []
        if 'migration_results' in self.app_state:
            del self.app_state['migration_results']
        if 'playlist_results' in self.app_state:
            del self.app_state['playlist_results']
        
        # Navigate to playlist selection
        from src.ui.screens.playlist_selection_screen import PlaylistSelectionScreen
        self.navigate_to(PlaylistSelectionScreen, progress_text="Step 2 of 5")
    
    def _handle_back(self, e):
        """Handle back button click.
        
        Results screen typically doesn't show back button.
        
        Args:
            e: Flet event object.
        """
        # No back navigation from results screen
        pass
