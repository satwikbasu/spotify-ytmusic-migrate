"""Base screen abstract class for all application screens.

This module provides the base class that all application screens inherit from,
providing common functionality like navigation, error handling, loading states,
and consistent layout patterns.

Example:
    >>> class LoginScreen(BaseScreen):
    ...     def build(self) -> ft.Control:
    ...         return ft.Text("Login Screen")
    >>> 
    >>> screen = LoginScreen(page, app_state)
    >>> screen.show()
"""

import flet as ft
from abc import ABC, abstractmethod
from typing import Dict, Any, Type, Optional
import logging

from config import app_config


logger = logging.getLogger(__name__)


class BaseScreen(ABC):
    """Abstract base class for all application screens.
    
    Provides common functionality for screen management including:
    - Screen building and display
    - Navigation between screens
    - Error dialogs
    - Loading overlays
    - Back button handling
    - Progress indicators
    - Fade-in animations
    
    All screens should inherit from this class and implement the build() method.
    
    Attributes:
        page (ft.Page): Flet page object for the application.
        app_state (Dict[str, Any]): Shared state dictionary for passing data
            between screens (e.g., tokens, user data, settings).
    
    Example:
        >>> class WelcomeScreen(BaseScreen):
        ...     def build(self) -> ft.Control:
        ...         return ft.Container(
        ...             content=ft.Text("Welcome!"),
        ...             alignment=ft.alignment.center
        ...         )
        >>> 
        >>> app_state = {'user': 'john_doe'}
        >>> screen = WelcomeScreen(page, app_state)
        >>> screen.show()
    """
    
    # Animation duration in milliseconds
    FADE_IN_DURATION = 300
    
    def __init__(self, page: ft.Page, app_state: Dict[str, Any]):
        """Initialize the base screen.
        
        Args:
            page (ft.Page): Flet page object for rendering controls.
            app_state (Dict[str, Any]): Shared application state dictionary.
                Used to pass data between screens (tokens, user info, etc.).
        
        Example:
            >>> page = ft.Page()
            >>> app_state = {
            ...     'spotify_token': 'abc123',
            ...     'youtube_token': 'xyz789',
            ...     'current_step': 2
            ... }
            >>> screen = MyScreen(page, app_state)
        """
        self.page = page
        self.app_state = app_state
        self._loading_overlay: Optional[ft.Container] = None
        
        logger.debug(f"Initialized {self.__class__.__name__}")
    
    @abstractmethod
    def build(self) -> ft.Control:
        """Build and return the screen's UI content.
        
        This method must be implemented by all subclasses. It should return
        a Flet control (typically a Container or Column) containing the
        screen's complete UI layout.
        
        Returns:
            ft.Control: The screen's UI content.
        
        Example:
            >>> def build(self) -> ft.Control:
            ...     return ft.Column([
            ...         ft.Text("My Screen", size=32),
            ...         ft.ElevatedButton("Next", on_click=self.handle_next)
            ...     ])
        
        Raises:
            NotImplementedError: If not implemented by subclass.
        """
        pass
    
    def show(self, show_back: bool = False, progress_text: Optional[str] = None) -> None:
        """Display the screen with optional back button and progress indicator.
        
        Clears the current page content, builds the screen UI, adds optional
        navigation elements, and displays with a fade-in animation.
        
        Args:
            show_back (bool): If True, shows a back button in the top-left.
                Defaults to False.
            progress_text (Optional[str]): Progress text to display in top-right
                (e.g., "Step 2/5"). If None, no progress indicator is shown.
                Defaults to None.
        
        Example:
            >>> # Simple screen
            >>> screen.show()
            >>> 
            >>> # Screen with back button
            >>> screen.show(show_back=True)
            >>> 
            >>> # Screen with back button and progress
            >>> screen.show(show_back=True, progress_text="Step 2 of 5")
        """
        logger.info(f"Showing {self.__class__.__name__}")
        
        # Clear page
        self.page.controls.clear()
        
        # Build screen content
        content = self.build()
        
        # Wrap content in container with fade-in animation
        animated_content = ft.Container(
            content=content,
            animate_opacity=self.FADE_IN_DURATION,
            opacity=0,  # Start invisible
            expand=True  # Allow content to expand and enable scrolling
        )
        
        # Create header row for back button and progress
        header_controls = []
        
        # Add back button if requested
        if show_back:
            back_button = ft.IconButton(
                icon=ft.Icons.ARROW_BACK,
                icon_color=app_config.PRIMARY_COLOR,
                icon_size=24,
                on_click=self._handle_back,
                tooltip="Go back"
            )
            header_controls.append(back_button)
        else:
            # Spacer if no back button
            header_controls.append(ft.Container(width=48))
        
        # Add spacer to push progress to right
        header_controls.append(ft.Container(expand=True))
        
        # Add progress indicator if provided
        if progress_text:
            progress_indicator = ft.Text(
                value=progress_text,
                size=app_config.CAPTION_SIZE,
                color=app_config.TEXT_COLOR_DARK,
                opacity=0.7,
                weight=ft.FontWeight.W_500
            )
            header_controls.append(progress_indicator)
        else:
            # Spacer if no progress
            header_controls.append(ft.Container(width=48))
        
        # Create header row
        header = ft.Row(
            controls=header_controls,
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER
        )
        
        # Create main layout
        main_layout = ft.Column(
            controls=[
                header,
                ft.Container(height=16),  # Spacing
                animated_content
            ],
            expand=True,
            spacing=0
        )
        
        # Add to page
        self.page.add(main_layout)
        self.page.update()
        
        # Trigger fade-in animation
        animated_content.opacity = 1
        self.page.update()
        
        logger.debug(f"{self.__class__.__name__} displayed")
    
    def navigate_to(self, screen_class: Type['BaseScreen'], **kwargs) -> None:
        """Navigate to another screen.
        
        Creates an instance of the specified screen class and displays it,
        passing along the current page and app_state.
        
        Args:
            screen_class (Type[BaseScreen]): The screen class to navigate to.
                Must be a subclass of BaseScreen.
            **kwargs: Additional keyword arguments to pass to screen.show()
                (e.g., show_back=True, progress_text="Step 2/5").
        
        Example:
            >>> # Navigate to next screen
            >>> self.navigate_to(PlaylistSelectionScreen)
            >>> 
            >>> # Navigate with back button and progress
            >>> self.navigate_to(
            ...     MigrationScreen,
            ...     show_back=True,
            ...     progress_text="Step 3 of 5"
            ... )
        
        Raises:
            TypeError: If screen_class is not a BaseScreen subclass.
        """
        if not issubclass(screen_class, BaseScreen):
            raise TypeError(f"{screen_class} must be a subclass of BaseScreen")
        
        logger.info(f"Navigating from {self.__class__.__name__} to {screen_class.__name__}")
        
        # Create and show new screen
        screen = screen_class(self.page, self.app_state)
        screen.show(**kwargs)
    
    def _handle_back(self, e) -> None:
        """Handle back button click.
        
        This is a placeholder that can be overridden by subclasses to
        implement custom back navigation logic. By default, logs a warning.
        
        Args:
            e: Flet event object.
        
        Note:
            Subclasses should override this to implement specific back
            navigation (e.g., navigate_to(PreviousScreen)).
        """
        logger.warning(f"Back button clicked in {self.__class__.__name__} but no handler defined")
    
    def show_error(self, message: str, title: str = "Error") -> None:
        """Display an error dialog.
        
        Shows a modal alert dialog with the error message and an OK button
        to dismiss.
        
        Args:
            message (str): The error message to display.
            title (str): Dialog title. Defaults to "Error".
        
        Example:
            >>> # Simple error
            >>> self.show_error("Failed to connect to Spotify")
            >>> 
            >>> # Custom title
            >>> self.show_error(
            ...     "Invalid credentials provided",
            ...     title="Authentication Failed"
            ... )
        """
        logger.error(f"Showing error dialog: {message}")
        
        def close_dialog(e):
            dialog.open = False
            self.page.update()
        
        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(
                value=title,
                size=app_config.HEADING_SIZE_SMALL,
                weight=ft.FontWeight.BOLD,
                color=app_config.ERROR_COLOR
            ),
            content=ft.Text(
                value=message,
                size=app_config.BODY_SIZE,
                color=ft.Colors.WHITE
            ),
            actions=[
                ft.TextButton(
                    text="OK",
                    on_click=close_dialog
                )
            ],
            actions_alignment=ft.MainAxisAlignment.END
        )
        
        self.page.overlay.append(dialog)
        dialog.open = True
        self.page.update()
    
    def show_success(self, message: str, title: str = "Success") -> None:
        """Display a success dialog.
        
        Shows a modal alert dialog with the success message and an OK button
        to dismiss.
        
        Args:
            message (str): The success message to display.
            title (str): Dialog title. Defaults to "Success".
        
        Example:
            >>> self.show_success("Migration completed successfully!")
            >>> self.show_success("Playlist created", title="Done")
        """
        logger.info(f"Showing success dialog: {message}")
        
        def close_dialog(e):
            dialog.open = False
            self.page.update()
        
        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(
                value=title,
                size=app_config.HEADING_SIZE_SMALL,
                weight=ft.FontWeight.BOLD,
                color=app_config.SUCCESS_COLOR
            ),
            content=ft.Text(
                value=message,
                size=app_config.BODY_SIZE,
                color=ft.Colors.WHITE
            ),
            actions=[
                ft.TextButton(
                    text="OK",
                    on_click=close_dialog
                )
            ],
            actions_alignment=ft.MainAxisAlignment.END
        )
        
        self.page.overlay.append(dialog)
        dialog.open = True
        self.page.update()
    
    def show_loading(self, show: bool = True, message: str = "Loading...") -> None:
        """Show or hide a loading overlay.
        
        Displays a semi-transparent overlay with a centered loading spinner
        and optional message. Useful for blocking the UI during async operations.
        
        Args:
            show (bool): If True, shows the overlay. If False, hides it.
                Defaults to True.
            message (str): Loading message to display below spinner.
                Defaults to "Loading...".
        
        Example:
            >>> # Show loading
            >>> self.show_loading(True, "Fetching playlists...")
            >>> 
            >>> # Perform async operation
            >>> await fetch_playlists()
            >>> 
            >>> # Hide loading
            >>> self.show_loading(False)
        """
        if show:
            logger.debug(f"Showing loading overlay: {message}")
            
            # Create loading overlay if not exists
            if self._loading_overlay is None:
                self._loading_overlay = ft.Container(
                    content=ft.Column(
                        controls=[
                            ft.ProgressRing(
                                width=48,
                                height=48,
                                stroke_width=4,
                                color=app_config.PRIMARY_COLOR
                            ),
                            ft.Container(height=16),
                            ft.Text(
                                value=message,
                                size=app_config.BODY_SIZE,
                                color=app_config.TEXT_COLOR_LIGHT,
                                weight=ft.FontWeight.W_500
                            )
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        alignment=ft.MainAxisAlignment.CENTER
                    ),
                    bgcolor="#000000AA",  # Semi-transparent black
                    expand=True,
                    alignment=ft.alignment.center
                )
            else:
                # Update message if overlay exists
                self._loading_overlay.content.controls[2].value = message
            
            # Add overlay to page
            if self._loading_overlay not in self.page.overlay:
                self.page.overlay.append(self._loading_overlay)
            
            try:
                self.page.update()
            except AssertionError:
                # UI not fully initialized yet, skip update
                logger.debug("UI not ready for update, skipping")
        else:
            logger.debug("Hiding loading overlay")
            
            # Remove overlay from page
            if self._loading_overlay and self._loading_overlay in self.page.overlay:
                self.page.overlay.remove(self._loading_overlay)
                try:
                    self.page.update()
                except AssertionError:
                    # UI not fully initialized yet, skip update
                    logger.debug("UI not ready for update, skipping")
    
    def show_confirmation(
        self,
        message: str,
        title: str = "Confirm",
        on_confirm: Optional[callable] = None,
        on_cancel: Optional[callable] = None,
        confirm_text: str = "Confirm",
        cancel_text: str = "Cancel"
    ) -> None:
        """Display a confirmation dialog.
        
        Shows a modal dialog with the message and two buttons (confirm/cancel).
        Executes callbacks based on user choice.
        
        Args:
            message (str): The confirmation message to display.
            title (str): Dialog title. Defaults to "Confirm".
            on_confirm (Optional[callable]): Callback when user confirms.
            on_cancel (Optional[callable]): Callback when user cancels.
            confirm_text (str): Confirm button text. Defaults to "Confirm".
            cancel_text (str): Cancel button text. Defaults to "Cancel".
        
        Example:
            >>> def handle_delete():
            ...     # Perform deletion
            ...     print("Deleted!")
            >>> 
            >>> self.show_confirmation(
            ...     "Are you sure you want to delete this playlist?",
            ...     title="Delete Playlist",
            ...     on_confirm=handle_delete,
            ...     confirm_text="Delete",
            ...     cancel_text="Cancel"
            ... )
        """
        logger.debug(f"Showing confirmation dialog: {message}")
        
        def close_and_confirm(e):
            dialog.open = False
            self.page.update()
            if on_confirm:
                on_confirm()
        
        def close_and_cancel(e):
            dialog.open = False
            self.page.update()
            if on_cancel:
                on_cancel()
        
        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(
                value=title,
                size=app_config.HEADING_SIZE_SMALL,
                weight=ft.FontWeight.BOLD,
                color=ft.Colors.WHITE
            ),
            content=ft.Text(
                value=message,
                size=app_config.BODY_SIZE,
                color=ft.Colors.WHITE
            ),
            actions=[
                ft.TextButton(
                    text=cancel_text,
                    on_click=close_and_cancel
                ),
                ft.ElevatedButton(
                    text=confirm_text,
                    bgcolor=app_config.PRIMARY_COLOR,
                    color=app_config.TEXT_COLOR_LIGHT,
                    on_click=close_and_confirm
                )
            ],
            actions_alignment=ft.MainAxisAlignment.END
        )
        
        self.page.overlay.append(dialog)
        dialog.open = True
        self.page.update()
    
    def clear_overlays(self) -> None:
        """Clear all overlays from the page.
        
        Removes all dialogs and overlays (including loading overlays)
        from the page.
        
        Example:
            >>> # Clean up before navigation
            >>> self.clear_overlays()
            >>> self.navigate_to(NextScreen)
        """
        logger.debug(f"Clearing overlays in {self.__class__.__name__}")
        self.page.overlay.clear()
        self._loading_overlay = None
        self.page.update()
