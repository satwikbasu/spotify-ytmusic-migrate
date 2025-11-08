"""Reusable Flet UI components for the Spotify to YouTube Music Migrator.

This module provides custom UI components that follow the Material Design
guidelines and maintain consistent styling across the application.

Components:
- AppButton: Styled elevated button with optional gradient
- AppTextField: Styled text input field
- PlaylistCard: Interactive playlist display card
- ProgressBar: Progress indicator with percentage text
- StatusBanner: Dismissible notification banner
- LoadingIndicator: Centered loading spinner

Example:
    >>> import flet as ft
    >>> from src.ui.components import AppButton, PlaylistCard
    >>> 
    >>> def on_click(e):
    ...     print("Button clicked!")
    >>> 
    >>> button = AppButton(text="Migrate", on_click=on_click, primary=True)
    >>> card = PlaylistCard(playlist={'name': 'Rock', 'tracks': 50})
"""

import flet as ft
from typing import Optional, Callable, Dict, Any
from config import app_config


class AppButton(ft.ElevatedButton):
    """Custom styled elevated button.
    
    Provides consistent button styling across the application with
    support for primary/secondary variants and optional gradient backgrounds.
    
    Attributes:
        text (str): Button label text.
        on_click (Optional[Callable]): Click event handler.
        primary (bool): Whether this is a primary action button.
        gradient (bool): Whether to apply gradient background.
        disabled (bool): Whether the button is disabled.
    
    Example:
        >>> # Primary button with gradient
        >>> btn = AppButton(
        ...     text="Migrate Playlists",
        ...     on_click=lambda e: print("Migrating..."),
        ...     primary=True,
        ...     gradient=True
        ... )
        >>> 
        >>> # Secondary button
        >>> cancel_btn = AppButton(
        ...     text="Cancel",
        ...     on_click=lambda e: print("Cancelled"),
        ...     primary=False
        ... )
    """
    
    def __init__(
        self,
        text: str,
        on_click: Optional[Callable] = None,
        primary: bool = False,
        gradient: bool = False,
        disabled: bool = False,
        **kwargs
    ):
        """Initialize the styled button.
        
        Args:
            text (str): Button label text.
            on_click (Optional[Callable]): Click event handler.
            primary (bool): If True, uses primary color styling. Defaults to False.
            gradient (bool): If True, applies gradient background. Defaults to False.
            disabled (bool): If True, button is disabled. Defaults to False.
            **kwargs: Additional Flet button properties.
        """
        # Determine color scheme based on primary flag
        if primary:
            bg_color = app_config.PRIMARY_COLOR
            text_color = app_config.TEXT_COLOR_LIGHT
        else:
            bg_color = None  # Use default
            text_color = app_config.TEXT_COLOR_DARK
        
        # Apply gradient if requested
        if gradient and primary:
            # Create gradient from primary color to slightly darker shade
            gradient_bg = ft.LinearGradient(
                begin=ft.alignment.center_left,
                end=ft.alignment.center_right,
                colors=[app_config.PRIMARY_COLOR, "#1976D2"]  # Darker blue
            )
        else:
            gradient_bg = None
        
        super().__init__(
            text=text,
            on_click=on_click,
            disabled=disabled,
            bgcolor=bg_color if not gradient else None,
            color=text_color,
            style=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=8),
                padding=ft.padding.symmetric(horizontal=24, vertical=12),
                text_style=ft.TextStyle(
                    size=app_config.BODY_SIZE,
                    weight=ft.FontWeight.W_500
                )
            ),
            **kwargs
        )
        
        # Apply gradient if specified
        if gradient_bg:
            self.gradient = gradient_bg


class AppTextField(ft.TextField):
    """Custom styled text field.
    
    Provides consistent text input styling across the application with
    support for password fields and change handlers.
    
    Attributes:
        label (str): Field label text.
        value (str): Current field value.
        password (bool): Whether this is a password field (masked input).
        on_change (Optional[Callable]): Value change event handler.
    
    Example:
        >>> # Regular text field
        >>> name_field = AppTextField(
        ...     label="Playlist Name",
        ...     value="My Favorites",
        ...     on_change=lambda e: print(f"Name: {e.control.value}")
        ... )
        >>> 
        >>> # Password field
        >>> pwd_field = AppTextField(
        ...     label="API Secret",
        ...     password=True
        ... )
    """
    
    def __init__(
        self,
        label: str,
        value: str = "",
        password: bool = False,
        on_change: Optional[Callable] = None,
        **kwargs
    ):
        """Initialize the styled text field.
        
        Args:
            label (str): Field label text.
            value (str): Initial field value. Defaults to empty string.
            password (bool): If True, masks input. Defaults to False.
            on_change (Optional[Callable]): Change event handler.
            **kwargs: Additional Flet TextField properties.
        """
        super().__init__(
            label=label,
            value=value,
            password=password,
            on_change=on_change,
            border_color=app_config.PRIMARY_COLOR,
            focused_border_color=app_config.PRIMARY_COLOR,
            cursor_color=app_config.PRIMARY_COLOR,
            text_size=app_config.BODY_SIZE,
            label_style=ft.TextStyle(
                size=app_config.CAPTION_SIZE,
                color=app_config.TEXT_COLOR_DARK
            ),
            border_radius=8,
            content_padding=ft.padding.symmetric(horizontal=16, vertical=12),
            **kwargs
        )


class PlaylistCard(ft.Container):
    """Interactive playlist card component.
    
    Displays playlist information with checkbox, thumbnail (optional),
    name, and track count. Supports selection and hover effects.
    
    Attributes:
        playlist (Dict[str, Any]): Playlist data dictionary with keys:
            - name (str): Playlist name
            - tracks (int): Number of tracks
            - thumbnail (Optional[str]): Thumbnail image URL
            - id (str): Playlist identifier
        selected (bool): Whether the card is selected.
        on_click (Optional[Callable]): Click event handler.
    
    Example:
        >>> playlist_data = {
        ...     'id': 'sp_123',
        ...     'name': 'Rock Classics',
        ...     'tracks': 150,
        ...     'thumbnail': 'https://example.com/thumb.jpg'
        ... }
        >>> 
        >>> card = PlaylistCard(
        ...     playlist=playlist_data,
        ...     selected=True,
        ...     on_click=lambda e: print("Card clicked")
        ... )
    """
    
    def __init__(
        self,
        playlist: Dict[str, Any],
        selected: bool = False,
        on_click: Optional[Callable] = None,
        **kwargs
    ):
        """Initialize the playlist card.
        
        Args:
            playlist (Dict[str, Any]): Playlist data with name, tracks, optional thumbnail.
            selected (bool): If True, shows checkbox as checked. Defaults to False.
            on_click (Optional[Callable]): Click event handler.
            **kwargs: Additional Flet Container properties.
        """
        self.playlist = playlist
        self.selected = selected
        self._on_click = on_click
        
        # Extract playlist info
        name = playlist.get('name', 'Unknown Playlist')
        track_count = playlist.get('tracks', 0)
        thumbnail_url = playlist.get('thumbnail', None)
        
        # Create checkbox
        checkbox = ft.Checkbox(
            value=selected,
            on_change=self._handle_checkbox_change
        )
        
        # Create thumbnail (if available)
        if thumbnail_url:
            thumbnail = ft.Image(
                src=thumbnail_url,
                width=48,
                height=48,
                fit=ft.ImageFit.COVER,
                border_radius=4
            )
        else:
            # Placeholder icon if no thumbnail
            thumbnail = ft.Container(
                width=48,
                height=48,
                bgcolor=app_config.PRIMARY_COLOR,
                border_radius=4,
                content=ft.Icon(
                    name=ft.Icons.MUSIC_NOTE,
                    color=app_config.TEXT_COLOR_LIGHT,
                    size=24
                ),
                alignment=ft.alignment.center
            )
        
        # Create playlist info column
        info_column = ft.Column(
            controls=[
                ft.Text(
                    value=name,
                    size=app_config.BODY_SIZE,
                    weight=ft.FontWeight.W_500,
                    color=app_config.TEXT_COLOR_DARK,
                    overflow=ft.TextOverflow.ELLIPSIS,
                    max_lines=1
                ),
                ft.Text(
                    value=f"{track_count} tracks",
                    size=app_config.CAPTION_SIZE,
                    color=app_config.TEXT_COLOR_DARK,
                    opacity=0.7
                )
            ],
            spacing=4,
            expand=True
        )
        
        # Create card content row
        card_row = ft.Row(
            controls=[
                checkbox,
                thumbnail,
                info_column
            ],
            spacing=12,
            alignment=ft.MainAxisAlignment.START,
            vertical_alignment=ft.CrossAxisAlignment.CENTER
        )
        
        super().__init__(
            content=card_row,
            bgcolor=app_config.BACKGROUND_LIGHT,
            border=ft.border.all(1, color=app_config.PRIMARY_COLOR if selected else "#E0E0E0"),
            border_radius=8,
            padding=12,
            ink=True,
            on_click=self._handle_click,
            on_hover=self._handle_hover,
            **kwargs
        )
        
        self.checkbox = checkbox
    
    def _handle_checkbox_change(self, e):
        """Handle checkbox state change."""
        self.selected = e.control.value
        self.border = ft.border.all(
            1,
            color=app_config.PRIMARY_COLOR if self.selected else "#E0E0E0"
        )
        self.update()
        
        if self._on_click:
            self._on_click(e)
    
    def _handle_click(self, e):
        """Handle card click - toggle selection."""
        self.selected = not self.selected
        self.checkbox.value = self.selected
        self.border = ft.border.all(
            1,
            color=app_config.PRIMARY_COLOR if self.selected else "#E0E0E0"
        )
        self.update()
        
        if self._on_click:
            self._on_click(e)
    
    def _handle_hover(self, e):
        """Handle hover effect."""
        if e.data == "true":
            # Mouse entered
            self.bgcolor = "#F5F5F5"
        else:
            # Mouse left
            self.bgcolor = app_config.BACKGROUND_LIGHT
        self.update()


class ProgressBar(ft.Container):
    """Progress bar with percentage text.
    
    Displays a progress bar with percentage text above it. Supports
    custom text and optional shimmer animation effect.
    
    Attributes:
        value (float): Progress value from 0.0 to 1.0.
        text (str): Custom text to display (overrides percentage).
    
    Example:
        >>> # Progress bar with percentage
        >>> progress = ProgressBar(value=0.75)  # Shows "75%"
        >>> 
        >>> # Progress bar with custom text
        >>> progress = ProgressBar(
        ...     value=0.5,
        ...     text="Processing track 5 of 10..."
        ... )
    """
    
    def __init__(
        self,
        value: float = 0.0,
        text: Optional[str] = None,
        **kwargs
    ):
        """Initialize the progress bar.
        
        Args:
            value (float): Progress value (0.0 to 1.0). Defaults to 0.0.
            text (Optional[str]): Custom text. If None, shows percentage.
            **kwargs: Additional Flet Container properties.
        """
        self.value = max(0.0, min(1.0, value))  # Clamp to [0, 1]
        
        # Generate display text
        if text:
            display_text = text
        else:
            percentage = int(self.value * 100)
            display_text = f"{percentage}%"
        
        # Create text label
        text_label = ft.Text(
            value=display_text,
            size=app_config.CAPTION_SIZE,
            color=app_config.TEXT_COLOR_DARK,
            text_align=ft.TextAlign.CENTER
        )
        
        # Create progress bar
        progress_bar = ft.ProgressBar(
            value=self.value,
            color=app_config.PRIMARY_COLOR,
            bgcolor="#E0E0E0",
            height=8,
            border_radius=4
        )
        
        # Create container with text and bar
        content = ft.Column(
            controls=[
                text_label,
                progress_bar
            ],
            spacing=8,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH
        )
        
        super().__init__(
            content=content,
            **kwargs
        )
        
        self.text_label = text_label
        self.progress_bar = progress_bar
    
    def update_progress(self, value: float, text: Optional[str] = None):
        """Update progress value and text.
        
        Args:
            value (float): New progress value (0.0 to 1.0).
            text (Optional[str]): New text. If None, shows percentage.
        
        Example:
            >>> progress = ProgressBar(value=0.0)
            >>> progress.update_progress(0.5, "Halfway done!")
            >>> progress.update_progress(1.0)  # Shows "100%"
        """
        self.value = max(0.0, min(1.0, value))
        self.progress_bar.value = self.value
        
        if text:
            self.text_label.value = text
        else:
            percentage = int(self.value * 100)
            self.text_label.value = f"{percentage}%"
        
        self.update()


class StatusBanner(ft.Container):
    """Dismissible status banner.
    
    Displays a notification banner at the top of the page with color-coded
    styling based on message type (info, warning, error, success).
    
    Attributes:
        message (str): Banner message text.
        banner_type (str): Type of banner - info, warning, error, or success.
        on_dismiss (Optional[Callable]): Dismiss button click handler.
    
    Example:
        >>> # Success banner
        >>> banner = StatusBanner(
        ...     message="Migration completed successfully!",
        ...     banner_type="success",
        ...     on_dismiss=lambda e: print("Banner dismissed")
        ... )
        >>> 
        >>> # Error banner
        >>> error_banner = StatusBanner(
        ...     message="Failed to connect to Spotify",
        ...     banner_type="error"
        ... )
    """
    
    # Type to color mapping
    TYPE_COLORS = {
        'info': app_config.PRIMARY_COLOR,
        'warning': app_config.WARNING_COLOR,
        'error': app_config.ERROR_COLOR,
        'success': app_config.SUCCESS_COLOR
    }
    
    # Type to icon mapping
    TYPE_ICONS = {
        'info': ft.Icons.INFO_OUTLINED,
        'warning': ft.Icons.WARNING_OUTLINED,
        'error': ft.Icons.ERROR_OUTLINED,
        'success': ft.Icons.CHECK_CIRCLE_OUTLINED
    }
    
    def __init__(
        self,
        message: str,
        banner_type: str = "info",
        on_dismiss: Optional[Callable] = None,
        **kwargs
    ):
        """Initialize the status banner.
        
        Args:
            message (str): Banner message text.
            banner_type (str): Banner type - info, warning, error, or success.
                Defaults to "info".
            on_dismiss (Optional[Callable]): Dismiss button handler.
            **kwargs: Additional Flet Container properties.
        
        Raises:
            ValueError: If banner_type is not valid.
        """
        if banner_type not in self.TYPE_COLORS:
            raise ValueError(
                f"Invalid banner_type: {banner_type}. "
                f"Must be one of: {', '.join(self.TYPE_COLORS.keys())}"
            )
        
        self.message = message
        self.banner_type = banner_type
        self._on_dismiss = on_dismiss
        
        # Get colors and icon for type
        bg_color = self.TYPE_COLORS[banner_type]
        icon_name = self.TYPE_ICONS[banner_type]
        
        # Create icon
        icon = ft.Icon(
            name=icon_name,
            color=app_config.TEXT_COLOR_LIGHT,
            size=20
        )
        
        # Create message text
        message_text = ft.Text(
            value=message,
            size=app_config.BODY_SIZE,
            color=app_config.TEXT_COLOR_LIGHT,
            expand=True
        )
        
        # Create dismiss button (if handler provided)
        if on_dismiss:
            dismiss_button = ft.IconButton(
                icon=ft.Icons.CLOSE,
                icon_color=app_config.TEXT_COLOR_LIGHT,
                icon_size=20,
                on_click=self._handle_dismiss
            )
            controls = [icon, message_text, dismiss_button]
        else:
            controls = [icon, message_text]
        
        # Create banner row
        banner_row = ft.Row(
            controls=controls,
            spacing=12,
            alignment=ft.MainAxisAlignment.START,
            vertical_alignment=ft.CrossAxisAlignment.CENTER
        )
        
        super().__init__(
            content=banner_row,
            bgcolor=bg_color,
            border_radius=8,
            padding=16,
            **kwargs
        )
    
    def _handle_dismiss(self, e):
        """Handle dismiss button click."""
        if self._on_dismiss:
            self._on_dismiss(e)


class LoadingIndicator(ft.Container):
    """Centered loading spinner with optional text.
    
    Displays a centered circular progress indicator with optional
    descriptive text below the spinner.
    
    Attributes:
        text (Optional[str]): Text to display below spinner.
    
    Example:
        >>> # Simple loading spinner
        >>> loading = LoadingIndicator()
        >>> 
        >>> # Loading spinner with text
        >>> loading = LoadingIndicator(text="Loading playlists...")
    """
    
    def __init__(
        self,
        text: Optional[str] = None,
        **kwargs
    ):
        """Initialize the loading indicator.
        
        Args:
            text (Optional[str]): Text to display below spinner.
            **kwargs: Additional Flet Container properties.
        """
        self.text = text
        
        # Create spinner
        spinner = ft.ProgressRing(
            width=48,
            height=48,
            stroke_width=4,
            color=app_config.PRIMARY_COLOR
        )
        
        # Create controls list
        controls = [spinner]
        
        # Add text if provided
        if text:
            text_label = ft.Text(
                value=text,
                size=app_config.BODY_SIZE,
                color=app_config.TEXT_COLOR_DARK,
                text_align=ft.TextAlign.CENTER
            )
            controls.append(text_label)
            self.text_label = text_label
        
        # Create centered column
        content = ft.Column(
            controls=controls,
            spacing=16,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            alignment=ft.MainAxisAlignment.CENTER
        )
        
        super().__init__(
            content=content,
            alignment=ft.alignment.center,
            expand=True,
            **kwargs
        )
        
        self.spinner = spinner
    
    def update_text(self, text: str):
        """Update the loading text.
        
        Args:
            text (str): New text to display.
        
        Example:
            >>> loading = LoadingIndicator(text="Loading...")
            >>> loading.update_text("Almost done...")
        """
        if hasattr(self, 'text_label'):
            self.text_label.value = text
            self.update()
