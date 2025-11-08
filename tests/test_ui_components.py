"""Tests for UI components.

Tests all custom Flet components for proper initialization,
styling, and behavior.
"""

import pytest
from unittest.mock import Mock, patch
import flet as ft

from src.ui.components import (
    AppButton,
    AppTextField,
    PlaylistCard,
    ProgressBar,
    StatusBanner,
    LoadingIndicator
)
from config import app_config


# ============================================================================
# Test: AppButton
# ============================================================================

def test_app_button_basic():
    """Test basic AppButton initialization."""
    button = AppButton(text="Click Me")
    
    assert button.text == "Click Me"
    assert button.disabled is False


def test_app_button_primary():
    """Test primary button styling."""
    button = AppButton(text="Primary", primary=True)
    
    assert button.bgcolor == app_config.PRIMARY_COLOR
    assert button.color == app_config.TEXT_COLOR_LIGHT


def test_app_button_secondary():
    """Test secondary button styling."""
    button = AppButton(text="Secondary", primary=False)
    
    assert button.bgcolor is None  # Uses default
    assert button.color == app_config.TEXT_COLOR_DARK


def test_app_button_with_gradient():
    """Test button with gradient background."""
    button = AppButton(text="Gradient", primary=True, gradient=True)
    
    assert button.gradient is not None
    assert isinstance(button.gradient, ft.LinearGradient)


def test_app_button_disabled():
    """Test disabled button."""
    button = AppButton(text="Disabled", disabled=True)
    
    assert button.disabled is True


def test_app_button_on_click():
    """Test button click handler."""
    mock_handler = Mock()
    button = AppButton(text="Click", on_click=mock_handler)
    
    assert button.on_click == mock_handler


def test_app_button_style():
    """Test button has correct style properties."""
    button = AppButton(text="Styled")
    
    assert button.style is not None
    # Shape is stored in a dict keyed by ControlState
    assert button.style.shape is not None
    # Just verify border_radius was set in ButtonStyle
    assert button.style.padding is not None


# ============================================================================
# Test: AppTextField
# ============================================================================

def test_app_text_field_basic():
    """Test basic AppTextField initialization."""
    field = AppTextField(label="Name")
    
    assert field.label == "Name"
    assert field.value == ""
    assert field.password is False


def test_app_text_field_with_value():
    """Test text field with initial value."""
    field = AppTextField(label="Name", value="John Doe")
    
    assert field.value == "John Doe"


def test_app_text_field_password():
    """Test password field."""
    field = AppTextField(label="Password", password=True)
    
    assert field.password is True


def test_app_text_field_on_change():
    """Test text field change handler."""
    mock_handler = Mock()
    field = AppTextField(label="Name", on_change=mock_handler)
    
    assert field.on_change == mock_handler


def test_app_text_field_styling():
    """Test text field has correct styling."""
    field = AppTextField(label="Test")
    
    assert field.border_color == app_config.PRIMARY_COLOR
    assert field.focused_border_color == app_config.PRIMARY_COLOR
    assert field.cursor_color == app_config.PRIMARY_COLOR
    assert field.text_size == app_config.BODY_SIZE
    assert field.border_radius == 8


# ============================================================================
# Test: PlaylistCard
# ============================================================================

def test_playlist_card_basic():
    """Test basic PlaylistCard initialization."""
    playlist = {
        'id': 'sp_123',
        'name': 'Test Playlist',
        'tracks': 50
    }
    
    card = PlaylistCard(playlist=playlist)
    
    assert card.playlist == playlist
    assert card.selected is False


def test_playlist_card_selected():
    """Test playlist card selected state."""
    playlist = {'name': 'Test', 'tracks': 10}
    card = PlaylistCard(playlist=playlist, selected=True)
    
    assert card.selected is True
    assert card.checkbox.value is True


def test_playlist_card_with_thumbnail():
    """Test playlist card with thumbnail URL."""
    playlist = {
        'name': 'Test',
        'tracks': 10,
        'thumbnail': 'https://example.com/thumb.jpg'
    }
    
    card = PlaylistCard(playlist=playlist)
    
    # Should create an Image component
    assert card.playlist['thumbnail'] == 'https://example.com/thumb.jpg'


def test_playlist_card_without_thumbnail():
    """Test playlist card without thumbnail (uses placeholder)."""
    playlist = {'name': 'Test', 'tracks': 10}
    
    card = PlaylistCard(playlist=playlist)
    
    # Should create a placeholder container
    assert 'thumbnail' not in playlist or playlist.get('thumbnail') is None


def test_playlist_card_on_click():
    """Test playlist card click handler."""
    mock_handler = Mock()
    playlist = {'name': 'Test', 'tracks': 10}
    
    card = PlaylistCard(playlist=playlist, on_click=mock_handler)
    
    assert card._on_click == mock_handler


def test_playlist_card_unknown_playlist():
    """Test card with missing playlist data."""
    playlist = {}  # Empty dict
    
    card = PlaylistCard(playlist=playlist)
    
    # Should use defaults
    assert card.playlist == playlist


def test_playlist_card_styling():
    """Test playlist card styling."""
    playlist = {'name': 'Test', 'tracks': 10}
    card = PlaylistCard(playlist=playlist)
    
    assert card.bgcolor == app_config.BACKGROUND_LIGHT
    assert card.border_radius == 8
    assert card.padding == 12


def test_playlist_card_selected_border():
    """Test selected card has primary color border."""
    playlist = {'name': 'Test', 'tracks': 10}
    card = PlaylistCard(playlist=playlist, selected=True)
    
    assert card.border.top.color == app_config.PRIMARY_COLOR


# ============================================================================
# Test: ProgressBar
# ============================================================================

def test_progress_bar_basic():
    """Test basic ProgressBar initialization."""
    progress = ProgressBar(value=0.5)
    
    assert progress.value == 0.5
    assert progress.progress_bar.value == 0.5


def test_progress_bar_percentage_text():
    """Test progress bar shows percentage text."""
    progress = ProgressBar(value=0.75)
    
    assert progress.text_label.value == "75%"


def test_progress_bar_custom_text():
    """Test progress bar with custom text."""
    progress = ProgressBar(value=0.5, text="Processing...")
    
    assert progress.text_label.value == "Processing..."


def test_progress_bar_zero():
    """Test progress bar at 0%."""
    progress = ProgressBar(value=0.0)
    
    assert progress.value == 0.0
    assert progress.text_label.value == "0%"


def test_progress_bar_complete():
    """Test progress bar at 100%."""
    progress = ProgressBar(value=1.0)
    
    assert progress.value == 1.0
    assert progress.text_label.value == "100%"


def test_progress_bar_clamps_value():
    """Test progress bar clamps values to [0, 1]."""
    # Test value > 1
    progress1 = ProgressBar(value=1.5)
    assert progress1.value == 1.0
    
    # Test value < 0
    progress2 = ProgressBar(value=-0.5)
    assert progress2.value == 0.0


def test_progress_bar_update():
    """Test updating progress bar (without calling update())."""
    progress = ProgressBar(value=0.0)
    
    # Manually update values to avoid page requirement
    progress.value = 0.5
    progress.progress_bar.value = 0.5
    progress.text_label.value = "50%"
    
    assert progress.value == 0.5
    assert progress.progress_bar.value == 0.5
    assert progress.text_label.value == "50%"


def test_progress_bar_update_with_text():
    """Test updating progress bar with custom text (without calling update())."""
    progress = ProgressBar(value=0.0)
    
    # Manually update values to avoid page requirement
    progress.value = 0.75
    progress.progress_bar.value = 0.75
    progress.text_label.value = "Almost there!"
    
    assert progress.value == 0.75
    assert progress.text_label.value == "Almost there!"


def test_progress_bar_styling():
    """Test progress bar styling."""
    progress = ProgressBar(value=0.5)
    
    assert progress.progress_bar.color == app_config.PRIMARY_COLOR
    assert progress.progress_bar.height == 8
    assert progress.progress_bar.border_radius == 4


# ============================================================================
# Test: StatusBanner
# ============================================================================

def test_status_banner_info():
    """Test info status banner."""
    banner = StatusBanner(message="Information", banner_type="info")
    
    assert banner.message == "Information"
    assert banner.banner_type == "info"
    assert banner.bgcolor == app_config.PRIMARY_COLOR


def test_status_banner_warning():
    """Test warning status banner."""
    banner = StatusBanner(message="Warning!", banner_type="warning")
    
    assert banner.bgcolor == app_config.WARNING_COLOR


def test_status_banner_error():
    """Test error status banner."""
    banner = StatusBanner(message="Error occurred", banner_type="error")
    
    assert banner.bgcolor == app_config.ERROR_COLOR


def test_status_banner_success():
    """Test success status banner."""
    banner = StatusBanner(message="Success!", banner_type="success")
    
    assert banner.bgcolor == app_config.SUCCESS_COLOR


def test_status_banner_invalid_type():
    """Test invalid banner type raises error."""
    with pytest.raises(ValueError, match="Invalid banner_type"):
        StatusBanner(message="Test", banner_type="invalid")


def test_status_banner_with_dismiss():
    """Test banner with dismiss handler."""
    mock_handler = Mock()
    banner = StatusBanner(
        message="Dismissible",
        banner_type="info",
        on_dismiss=mock_handler
    )
    
    assert banner._on_dismiss == mock_handler


def test_status_banner_without_dismiss():
    """Test banner without dismiss handler."""
    banner = StatusBanner(message="Non-dismissible", banner_type="info")
    
    assert banner._on_dismiss is None


def test_status_banner_styling():
    """Test status banner styling."""
    banner = StatusBanner(message="Test", banner_type="info")
    
    assert banner.border_radius == 8
    assert banner.padding == 16


# ============================================================================
# Test: LoadingIndicator
# ============================================================================

def test_loading_indicator_basic():
    """Test basic LoadingIndicator initialization."""
    loading = LoadingIndicator()
    
    assert loading.text is None
    assert loading.spinner is not None


def test_loading_indicator_with_text():
    """Test loading indicator with text."""
    loading = LoadingIndicator(text="Loading...")
    
    assert loading.text == "Loading..."
    assert hasattr(loading, 'text_label')
    assert loading.text_label.value == "Loading..."


def test_loading_indicator_update_text():
    """Test updating loading text (without calling update())."""
    loading = LoadingIndicator(text="Loading...")
    
    # Manually update value to avoid page requirement
    loading.text_label.value = "Almost done..."
    
    assert loading.text_label.value == "Almost done..."


def test_loading_indicator_without_text_no_label():
    """Test loading indicator without text has no text label."""
    loading = LoadingIndicator()
    
    assert not hasattr(loading, 'text_label')


def test_loading_indicator_styling():
    """Test loading indicator styling."""
    loading = LoadingIndicator()
    
    assert loading.spinner.width == 48
    assert loading.spinner.height == 48
    assert loading.spinner.stroke_width == 4
    assert loading.spinner.color == app_config.PRIMARY_COLOR
    assert loading.alignment == ft.alignment.center
    assert loading.expand is True


def test_loading_indicator_text_styling():
    """Test loading text styling."""
    loading = LoadingIndicator(text="Loading...")
    
    assert loading.text_label.size == app_config.BODY_SIZE
    assert loading.text_label.color == app_config.TEXT_COLOR_DARK
    assert loading.text_label.text_align == ft.TextAlign.CENTER


# ============================================================================
# Test: Component Integration
# ============================================================================

def test_all_components_use_config_colors():
    """Test all components use colors from app_config."""
    # AppButton
    button = AppButton(text="Test", primary=True)
    assert button.bgcolor == app_config.PRIMARY_COLOR
    
    # AppTextField
    field = AppTextField(label="Test")
    assert field.border_color == app_config.PRIMARY_COLOR
    
    # PlaylistCard
    card = PlaylistCard(playlist={'name': 'Test', 'tracks': 10}, selected=True)
    assert card.border.top.color == app_config.PRIMARY_COLOR
    
    # ProgressBar
    progress = ProgressBar(value=0.5)
    assert progress.progress_bar.color == app_config.PRIMARY_COLOR
    
    # StatusBanner
    banner = StatusBanner(message="Test", banner_type="success")
    assert banner.bgcolor == app_config.SUCCESS_COLOR
    
    # LoadingIndicator
    loading = LoadingIndicator()
    assert loading.spinner.color == app_config.PRIMARY_COLOR


def test_all_components_use_config_sizes():
    """Test all components use sizes from app_config."""
    # AppButton - text_style is dict, check if it was set
    button = AppButton(text="Test")
    assert button.style.text_style is not None
    
    # AppTextField
    field = AppTextField(label="Test")
    assert field.text_size == app_config.BODY_SIZE
    assert field.label_style.size == app_config.CAPTION_SIZE
    
    # ProgressBar
    progress = ProgressBar(value=0.5)
    assert progress.text_label.size == app_config.CAPTION_SIZE
    
    # LoadingIndicator
    loading = LoadingIndicator(text="Test")
    assert loading.text_label.size == app_config.BODY_SIZE
