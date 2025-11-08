# BaseScreen Abstract Class

The `BaseScreen` abstract class provides a consistent foundation for all application screens in the Spotify to YouTube Music Migrator. It handles common functionality like navigation, loading states, dialogs, and animations.

## Overview

All screens in the application inherit from `BaseScreen` and implement the abstract `build()` method to define their unique UI. The base class handles:

- **Screen Display**: Page clearing, content rendering, fade-in animations
- **Navigation**: Screen transitions with shared state
- **Back Button**: Optional back navigation with icon button
- **Progress Indicators**: Step counters (e.g., "Step 2 of 5")
- **Error Dialogs**: Modal error messages
- **Success Dialogs**: Modal success messages
- **Confirmation Dialogs**: Two-button confirmation prompts
- **Loading Overlays**: Semi-transparent loading indicators
- **Transitions**: Smooth fade-in animations (300ms)

## Basic Usage

### Creating a Screen

```python
import flet as ft
from src.ui.base_screen import BaseScreen

class WelcomeScreen(BaseScreen):
    """Welcome screen for the application."""
    
    def build(self) -> ft.Control:
        """Build the welcome screen UI."""
        return ft.Container(
            content=ft.Column([
                ft.Text(
                    "Welcome to Playlist Migrator",
                    size=32,
                    weight=ft.FontWeight.BOLD
                ),
                ft.Container(height=20),
                ft.ElevatedButton(
                    "Get Started",
                    on_click=self.handle_start
                )
            ]),
            alignment=ft.alignment.center,
            expand=True
        )
    
    def handle_start(self, e):
        """Navigate to login screen."""
        from src.ui.login_screen import LoginScreen
        self.navigate_to(LoginScreen, progress_text="Step 1 of 5")
```

### Displaying a Screen

```python
# Initialize screen with page and shared state
app_state = {
    'spotify_token': None,
    'youtube_token': None,
    'user_info': {}
}

screen = WelcomeScreen(page, app_state)

# Show screen (basic)
screen.show()

# Show screen with back button
screen.show(show_back=True)

# Show screen with progress indicator
screen.show(progress_text="Step 2 of 5")

# Show screen with both
screen.show(show_back=True, progress_text="Step 3 of 5")
```

## Features

### Navigation

Navigate between screens while preserving app state:

```python
def handle_next(self, e):
    """Navigate to playlist selection."""
    from src.ui.playlist_screen import PlaylistSelectionScreen
    
    # Simple navigation
    self.navigate_to(PlaylistSelectionScreen)
    
    # Navigation with options
    self.navigate_to(
        PlaylistSelectionScreen,
        show_back=True,
        progress_text="Step 3 of 5"
    )
```

### Back Button Handling

Override `_handle_back()` to implement custom back navigation:

```python
class MyScreen(BaseScreen):
    def build(self) -> ft.Control:
        return ft.Text("My Screen")
    
    def _handle_back(self, e):
        """Go back to previous screen."""
        from src.ui.previous_screen import PreviousScreen
        self.navigate_to(PreviousScreen)
```

### Error Dialogs

Display error messages to users:

```python
def handle_login_error(self):
    """Show login error."""
    # Simple error
    self.show_error("Failed to authenticate with Spotify")
    
    # Custom title
    self.show_error(
        "Invalid credentials provided. Please check your API keys.",
        title="Authentication Failed"
    )
```

### Success Dialogs

Display success messages:

```python
def handle_migration_complete(self):
    """Show success message."""
    self.show_success(
        "Successfully migrated 10 playlists!",
        title="Migration Complete"
    )
```

### Confirmation Dialogs

Request user confirmation before actions:

```python
def handle_delete_request(self):
    """Ask user to confirm deletion."""
    def do_delete():
        # Perform deletion
        self.delete_playlist()
    
    self.show_confirmation(
        "Are you sure you want to delete this playlist? This cannot be undone.",
        title="Delete Playlist",
        on_confirm=do_delete,
        confirm_text="Delete",
        cancel_text="Cancel"
    )
```

### Loading Overlays

Show loading states during async operations:

```python
async def fetch_playlists(self):
    """Fetch playlists from Spotify."""
    # Show loading
    self.show_loading(True, "Fetching playlists...")
    
    try:
        playlists = await spotify_client.get_playlists()
        # Process playlists...
    except Exception as e:
        self.show_error(f"Failed to fetch playlists: {e}")
    finally:
        # Hide loading
        self.show_loading(False)
```

## App State

The `app_state` dictionary is shared across all screens, enabling data passing:

```python
# Login screen - store tokens
class LoginScreen(BaseScreen):
    def handle_login_success(self, spotify_token, youtube_token):
        # Store tokens in shared state
        self.app_state['spotify_token'] = spotify_token
        self.app_state['youtube_token'] = youtube_token
        self.app_state['user_info'] = {'name': 'John Doe'}
        
        # Navigate to next screen
        self.navigate_to(PlaylistSelectionScreen)

# Playlist screen - access tokens
class PlaylistSelectionScreen(BaseScreen):
    def build(self) -> ft.Control:
        # Access tokens from state
        spotify_token = self.app_state.get('spotify_token')
        user_name = self.app_state.get('user_info', {}).get('name', 'User')
        
        return ft.Text(f"Welcome, {user_name}!")
```

## Animations

All screens automatically fade in when displayed:

- **Duration**: 300ms (configurable via `BaseScreen.FADE_IN_DURATION`)
- **Effect**: Opacity transition from 0 to 1
- **Timing**: Triggered after page is updated

## Layout Structure

The `show()` method creates a consistent layout:

```
Column (main layout)
├── Row (header)
│   ├── IconButton (back, if show_back=True) / Spacer
│   ├── Container (spacer, expand=True)
│   └── Text (progress, if progress_text) / Spacer
├── Container (16px spacing)
└── Container (animated content from build())
    └── Your screen content...
```

## Best Practices

### 1. Implement Abstract Method

Always implement the `build()` method:

```python
def build(self) -> ft.Control:
    """Build and return screen UI."""
    return ft.Container(
        content=your_ui_here,
        expand=True
    )
```

### 2. Clean Up Before Navigation

Clear overlays before navigating to prevent stacking:

```python
def handle_next(self, e):
    self.clear_overlays()
    self.navigate_to(NextScreen)
```

### 3. Use Type Hints

Maintain type hints for better IDE support:

```python
def handle_click(self, e: ft.ControlEvent) -> None:
    """Handle button click."""
    pass
```

### 4. Handle Loading States

Always hide loading overlays in `finally` blocks:

```python
async def async_operation(self):
    self.show_loading(True)
    try:
        await do_work()
    finally:
        self.show_loading(False)
```

### 5. Validate State Data

Check app_state values before using:

```python
def build(self) -> ft.Control:
    token = self.app_state.get('spotify_token')
    if not token:
        self.show_error("Not authenticated")
        return ft.Container()
    
    # Use token...
```

## Configuration Integration

`BaseScreen` uses `app_config` for consistent styling:

```python
from config import app_config

# Colors
app_config.PRIMARY_COLOR      # #2196F3 (Material Blue)
app_config.ERROR_COLOR         # #F44336 (Red)
app_config.SUCCESS_COLOR       # #4CAF50 (Green)
app_config.TEXT_COLOR_LIGHT    # #FFFFFF
app_config.TEXT_COLOR_DARK     # #212121

# Sizes
app_config.HEADING_SIZE_SMALL  # 20px
app_config.BODY_SIZE           # 16px
app_config.CAPTION_SIZE        # 14px
```

## Testing

Test your screens by mocking the page and app_state:

```python
from unittest.mock import Mock
import flet as ft
from src.ui.my_screen import MyScreen

def test_my_screen():
    page = Mock(spec=ft.Page)
    page.controls = Mock()
    page.overlay = []
    app_state = {'token': 'abc123'}
    
    screen = MyScreen(page, app_state)
    screen.show()
    
    # Assertions...
    page.add.assert_called_once()
```

## API Reference

### Constructor

```python
__init__(page: ft.Page, app_state: Dict[str, Any])
```

### Abstract Methods

```python
@abstractmethod
def build() -> ft.Control
    """Build and return screen UI. Must be implemented by subclasses."""
```

### Display Methods

```python
def show(show_back: bool = False, progress_text: Optional[str] = None) -> None
    """Display the screen with optional back button and progress."""

def navigate_to(screen_class: Type[BaseScreen], **kwargs) -> None
    """Navigate to another screen."""
```

### Dialog Methods

```python
def show_error(message: str, title: str = "Error") -> None
    """Display error dialog."""

def show_success(message: str, title: str = "Success") -> None
    """Display success dialog."""

def show_confirmation(
    message: str,
    title: str = "Confirm",
    on_confirm: Optional[callable] = None,
    on_cancel: Optional[callable] = None,
    confirm_text: str = "Confirm",
    cancel_text: str = "Cancel"
) -> None
    """Display confirmation dialog."""
```

### Loading Methods

```python
def show_loading(show: bool = True, message: str = "Loading...") -> None
    """Show or hide loading overlay."""
```

### Utility Methods

```python
def clear_overlays() -> None
    """Clear all overlays from page."""

def _handle_back(e) -> None
    """Handle back button click. Override in subclasses."""
```

### Constants

```python
FADE_IN_DURATION = 300  # Animation duration in milliseconds
```

## Examples

### Login Screen with Error Handling

```python
class LoginScreen(BaseScreen):
    def build(self) -> ft.Control:
        self.username_field = AppTextField(hint_text="Username")
        self.password_field = AppTextField(hint_text="Password", password=True)
        
        return ft.Container(
            content=ft.Column([
                ft.Text("Login", size=32),
                self.username_field,
                self.password_field,
                AppButton("Login", on_click=self.handle_login, primary=True)
            ]),
            padding=40,
            alignment=ft.alignment.center
        )
    
    async def handle_login(self, e):
        username = self.username_field.value
        password = self.password_field.value
        
        if not username or not password:
            self.show_error("Please enter username and password")
            return
        
        self.show_loading(True, "Authenticating...")
        
        try:
            token = await authenticate(username, password)
            self.app_state['token'] = token
            self.show_loading(False)
            self.navigate_to(PlaylistSelectionScreen, progress_text="Step 2 of 5")
        except Exception as e:
            self.show_loading(False)
            self.show_error(f"Authentication failed: {e}", title="Login Error")
```

### Playlist Selection with Confirmation

```python
class PlaylistSelectionScreen(BaseScreen):
    def build(self) -> ft.Control:
        return ft.Container(
            content=ft.Column([
                ft.Text("Select Playlists", size=24),
                # Playlist cards...
                AppButton("Migrate", on_click=self.handle_migrate)
            ])
        )
    
    def handle_migrate(self, e):
        selected = self.get_selected_playlists()
        
        if not selected:
            self.show_error("Please select at least one playlist")
            return
        
        self.show_confirmation(
            f"Migrate {len(selected)} playlists?",
            title="Confirm Migration",
            on_confirm=self.start_migration,
            confirm_text="Migrate",
            cancel_text="Cancel"
        )
    
    def start_migration(self):
        self.app_state['selected_playlists'] = self.get_selected_playlists()
        self.navigate_to(MigrationScreen, progress_text="Step 4 of 5")
```

## License

Part of the Spotify to YouTube Music Migrator project.
