# UI Components

Reusable Flet UI components for the Spotify to YouTube Music Migrator, following Material Design guidelines.

## Components

### AppButton
Custom styled elevated button with primary/secondary variants and optional gradient backgrounds.

```python
from src.ui.components import AppButton

# Primary button with gradient
migrate_btn = AppButton(
    text="Migrate Playlists",
    on_click=handle_migrate,
    primary=True,
    gradient=True
)

# Secondary button
cancel_btn = AppButton(
    text="Cancel",
    on_click=handle_cancel,
    primary=False
)
```

**Properties:**
- `text` (str): Button label
- `on_click` (Callable): Click handler
- `primary` (bool): Use primary color styling
- `gradient` (bool): Apply gradient background
- `disabled` (bool): Disable the button

---

### AppTextField
Styled text input field with consistent appearance.

```python
from src.ui.components import AppTextField

# Regular text field
name_field = AppTextField(
    label="Playlist Name",
    value="My Favorites",
    on_change=handle_name_change
)

# Password field
api_secret = AppTextField(
    label="API Secret",
    password=True
)
```

**Properties:**
- `label` (str): Field label
- `value` (str): Initial value
- `password` (bool): Mask input
- `on_change` (Callable): Change handler

---

### PlaylistCard
Interactive card displaying playlist information with checkbox and thumbnail.

```python
from src.ui.components import PlaylistCard

playlist_data = {
    'id': 'sp_123',
    'name': 'Rock Classics',
    'tracks': 150,
    'thumbnail': 'https://example.com/thumb.jpg'
}

card = PlaylistCard(
    playlist=playlist_data,
    selected=True,
    on_click=handle_select
)
```

**Properties:**
- `playlist` (dict): Playlist data
  - `name` (str): Playlist name
  - `tracks` (int): Track count
  - `thumbnail` (str, optional): Image URL
  - `id` (str): Playlist ID
- `selected` (bool): Selection state
- `on_click` (Callable): Click handler

**Features:**
- Checkbox for selection
- Thumbnail or placeholder icon
- Hover effect
- Auto-updates border on selection

---

### ProgressBar
Progress indicator with percentage text.

```python
from src.ui.components import ProgressBar

# With percentage
progress = ProgressBar(value=0.75)  # Shows "75%"

# With custom text
progress = ProgressBar(
    value=0.5,
    text="Processing track 5 of 10..."
)

# Update progress
progress.update_progress(0.85, text="Almost done!")
```

**Properties:**
- `value` (float): Progress (0.0 to 1.0)
- `text` (str, optional): Custom text

**Methods:**
- `update_progress(value, text=None)`: Update bar and text

---

### StatusBanner
Dismissible notification banner with type-based styling.

```python
from src.ui.components import StatusBanner

# Success banner
success_banner = StatusBanner(
    message="Migration completed successfully!",
    banner_type="success",
    on_dismiss=handle_dismiss
)

# Error banner
error_banner = StatusBanner(
    message="Failed to connect to Spotify",
    banner_type="error"
)
```

**Properties:**
- `message` (str): Banner text
- `banner_type` (str): Type - `info`, `warning`, `error`, or `success`
- `on_dismiss` (Callable, optional): Dismiss handler

**Types:**
- `info` - Blue (PRIMARY_COLOR)
- `warning` - Orange (WARNING_COLOR)
- `error` - Red (ERROR_COLOR)
- `success` - Green (SUCCESS_COLOR)

---

### LoadingIndicator
Centered spinning indicator with optional text.

```python
from src.ui.components import LoadingIndicator

# Simple spinner
loading = LoadingIndicator()

# With descriptive text
loading = LoadingIndicator(text="Loading playlists...")

# Update text
loading.update_text("Fetching tracks...")
```

**Properties:**
- `text` (str, optional): Text below spinner

**Methods:**
- `update_text(text)`: Update loading text

---

## Design System

All components follow the design system defined in `config/app_config.py`:

### Colors
- **Primary**: `#2196F3` (Material Blue)
- **Spotify Green**: `#1DB954`
- **YouTube Red**: `#FF0000`
- **Success**: `#4CAF50`
- **Warning**: `#FF9800`
- **Error**: `#F44336`

### Typography
- **Heading Large**: 32px
- **Heading Medium**: 24px
- **Heading Small**: 20px
- **Body**: 16px
- **Caption**: 14px

### Spacing
- **Border Radius**: 8px (rounded corners)
- **Padding**: 12-16px
- **Component Spacing**: 12-16px

---

## Testing

Run component tests:
```bash
pytest tests/test_ui_components.py -v
```

All 45 component tests pass with 100% coverage.

---

## Usage Guidelines

### Consistency
Always use these components instead of raw Flet controls to maintain consistent styling:

✅ **Good:**
```python
button = AppButton(text="Submit", primary=True)
```

❌ **Bad:**
```python
button = ft.ElevatedButton(text="Submit", bgcolor="#2196F3")
```

### Accessibility
- Use descriptive labels for all fields
- Provide clear button text (avoid "Click here")
- Use appropriate banner types for messages

### Performance
- Reuse component instances when possible
- Avoid creating components in loops
- Use `update()` sparingly (only when needed)

---

## Examples

### Login Form
```python
from src.ui.components import AppTextField, AppButton, StatusBanner

# Fields
username = AppTextField(label="Username", value="")
password = AppTextField(label="Password", password=True)

# Button
login_btn = AppButton(
    text="Login",
    on_click=handle_login,
    primary=True,
    gradient=True
)

# Error banner
error = StatusBanner(
    message="Invalid credentials",
    banner_type="error",
    on_dismiss=lambda e: error.visible = False
)
```

### Playlist Selection
```python
from src.ui.components import PlaylistCard, LoadingIndicator

# Loading state
loading = LoadingIndicator(text="Loading playlists...")

# Playlist cards
cards = [
    PlaylistCard(
        playlist=pl,
        selected=pl['id'] in selected_ids,
        on_click=lambda e: toggle_selection(pl['id'])
    )
    for pl in playlists
]
```

### Migration Progress
```python
from src.ui.components import ProgressBar, StatusBanner

# Progress bar
progress = ProgressBar(
    value=0.0,
    text="Starting migration..."
)

# Success banner (shown when complete)
success = StatusBanner(
    message="All playlists migrated successfully!",
    banner_type="success"
)
```
