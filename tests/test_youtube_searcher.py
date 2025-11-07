"""Unit tests for YouTubeSearcher class.

This module tests YouTube Music search functionality including rate limiting,
error handling, ISRC matching, and retry logic.
"""

import pytest
from unittest.mock import Mock, patch, call
from ytmusicapi.exceptions import YTMusicServerError

from src.searchers.youtube_searcher import YouTubeSearcher
from src.utils.rate_limiter import RateLimiter


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_ytmusic():
    """Mock YTMusic client."""
    return Mock()


@pytest.fixture
def mock_rate_limiter():
    """Mock RateLimiter."""
    limiter = Mock(spec=RateLimiter)
    limiter.check_limit.return_value = True
    return limiter


@pytest.fixture
def searcher(mock_ytmusic, mock_rate_limiter):
    """YouTubeSearcher instance with mocks."""
    return YouTubeSearcher(mock_ytmusic, mock_rate_limiter)


# ============================================================================
# Initialization Tests
# ============================================================================

def test_searcher_initialization(mock_ytmusic, mock_rate_limiter):
    """Test YouTubeSearcher initialization."""
    searcher = YouTubeSearcher(mock_ytmusic, mock_rate_limiter)
    
    assert searcher.ytmusic_client == mock_ytmusic
    assert searcher.rate_limiter == mock_rate_limiter


def test_searcher_initialization_none_ytmusic(mock_rate_limiter):
    """Test initialization rejects None ytmusic_client."""
    with pytest.raises(ValueError, match="ytmusic_client cannot be None"):
        YouTubeSearcher(None, mock_rate_limiter)


def test_searcher_initialization_none_rate_limiter(mock_ytmusic):
    """Test initialization rejects None rate_limiter."""
    with pytest.raises(ValueError, match="rate_limiter cannot be None"):
        YouTubeSearcher(mock_ytmusic, None)


# ============================================================================
# search_track() Tests - Basic Functionality
# ============================================================================

@patch('src.searchers.youtube_searcher.time.sleep')
def test_search_track_basic(mock_sleep, searcher, mock_ytmusic, mock_rate_limiter):
    """Test basic track search."""
    # Mock search results
    mock_ytmusic.search.return_value = [
        {
            'videoId': 'abc123',
            'title': 'Blinding Lights',
            'artists': [{'name': 'The Weeknd'}],
            'duration': '3:20'
        }
    ]
    
    results = searcher.search_track("Blinding Lights", ["The Weeknd"])
    
    # Verify rate limiter was checked
    mock_rate_limiter.check_limit.assert_called_once()
    
    # Verify search was called with correct parameters
    mock_ytmusic.search.assert_called_once()
    call_kwargs = mock_ytmusic.search.call_args[1]
    assert call_kwargs['filter'] == 'songs'
    assert call_kwargs['limit'] == 5
    assert 'the weeknd' in call_kwargs['query'].lower()
    assert 'blinding lights' in call_kwargs['query'].lower()
    
    # Verify rate limiter recorded request
    mock_rate_limiter.record_request.assert_called_once()
    
    # Verify conservative delay
    mock_sleep.assert_called_once_with(1.0)
    
    # Verify results
    assert len(results) == 1
    assert results[0]['videoId'] == 'abc123'
    assert results[0]['duration_seconds'] == 200  # 3:20 = 200 seconds


@patch('src.searchers.youtube_searcher.time.sleep')
def test_search_track_multiple_results(mock_sleep, searcher, mock_ytmusic):
    """Test search returns multiple results."""
    mock_ytmusic.search.return_value = [
        {'videoId': 'id1', 'title': 'Song 1', 'artists': [{'name': 'Artist'}]},
        {'videoId': 'id2', 'title': 'Song 2', 'artists': [{'name': 'Artist'}]},
        {'videoId': 'id3', 'title': 'Song 3', 'artists': [{'name': 'Artist'}]},
    ]
    
    results = searcher.search_track("Test Song", ["Artist"])
    
    assert len(results) == 3
    assert results[0]['videoId'] == 'id1'
    assert results[1]['videoId'] == 'id2'
    assert results[2]['videoId'] == 'id3'


@patch('src.searchers.youtube_searcher.time.sleep')
def test_search_track_empty_results(mock_sleep, searcher, mock_ytmusic):
    """Test search with no results."""
    mock_ytmusic.search.return_value = []
    
    results = searcher.search_track("Obscure Song", ["Unknown Artist"])
    
    assert results == []


@patch('src.searchers.youtube_searcher.time.sleep')
def test_search_track_empty_track_name(mock_sleep, searcher, mock_ytmusic):
    """Test search with empty track name."""
    results = searcher.search_track("", ["Artist"])
    
    assert results == []
    mock_ytmusic.search.assert_not_called()


@patch('src.searchers.youtube_searcher.time.sleep')
@patch('src.searchers.youtube_searcher.sanitize_for_search')
def test_search_track_empty_sanitized_query(mock_sanitize, mock_sleep, searcher, mock_ytmusic):
    """Test search when sanitize_for_search returns empty string."""
    mock_sanitize.return_value = ""  # Empty query after sanitization
    
    results = searcher.search_track("Test", ["Artist"])
    
    assert results == []
    mock_ytmusic.search.assert_not_called()


# ============================================================================
# search_by_isrc() Tests
# ============================================================================

@patch('src.searchers.youtube_searcher.time.sleep')
def test_search_by_isrc_success(mock_sleep, searcher, mock_ytmusic):
    """Test successful ISRC search."""
    mock_ytmusic.search.return_value = [
        {
            'videoId': 'isrc123',
            'title': 'Exact Match',
            'artists': [{'name': 'Artist'}],
            'duration': '4:30'
        }
    ]
    
    result = searcher.search_by_isrc("USRC17607839")
    
    # Verify search was called with ISRC query
    mock_ytmusic.search.assert_called_once()
    call_kwargs = mock_ytmusic.search.call_args[1]
    assert call_kwargs['query'] == 'isrc:USRC17607839'
    assert call_kwargs['filter'] == 'songs'
    assert call_kwargs['limit'] == 1
    
    # Verify result
    assert result is not None
    assert result['videoId'] == 'isrc123'
    assert result['duration_seconds'] == 270  # 4:30 = 270 seconds


@patch('src.searchers.youtube_searcher.time.sleep')
def test_search_by_isrc_not_found(mock_sleep, searcher, mock_ytmusic):
    """Test ISRC search with no results."""
    mock_ytmusic.search.return_value = []
    
    result = searcher.search_by_isrc("INVALIDISRC")
    
    assert result is None


@patch('src.searchers.youtube_searcher.time.sleep')
def test_search_by_isrc_empty(mock_sleep, searcher, mock_ytmusic):
    """Test ISRC search with empty ISRC."""
    result = searcher.search_by_isrc("")
    
    assert result is None
    mock_ytmusic.search.assert_not_called()


# ============================================================================
# Rate Limiting Tests
# ============================================================================

@patch('src.searchers.youtube_searcher.time.sleep')
def test_search_rate_limit_check(mock_sleep, searcher, mock_ytmusic, mock_rate_limiter):
    """Test rate limiter is checked before search."""
    mock_rate_limiter.check_limit.return_value = False  # Rate limit exceeded
    mock_ytmusic.search.return_value = []
    
    results = searcher.search_track("Test", ["Artist"])
    
    # Should check twice (initial + retry)
    assert mock_rate_limiter.check_limit.call_count == 2
    # Should not perform search if rate limited
    assert results == []


@patch('src.searchers.youtube_searcher.time.sleep')
def test_search_rate_limit_record(mock_sleep, searcher, mock_ytmusic, mock_rate_limiter):
    """Test rate limiter records successful request."""
    mock_ytmusic.search.return_value = [
        {'videoId': 'test', 'title': 'Test', 'artists': []}
    ]
    
    searcher.search_track("Test", ["Artist"])
    
    mock_rate_limiter.record_request.assert_called_once()


@patch('src.searchers.youtube_searcher.time.sleep')
def test_search_conservative_delay(mock_sleep, searcher, mock_ytmusic):
    """Test 1-second delay is applied after search."""
    mock_ytmusic.search.return_value = []
    
    searcher.search_track("Test", ["Artist"])
    
    # Should sleep for 1.0 second
    mock_sleep.assert_called_with(1.0)


# ============================================================================
# Error Handling Tests - 429 Rate Limit
# ============================================================================

@patch('src.searchers.youtube_searcher.time.sleep')
def test_search_429_error_retry(mock_sleep, searcher, mock_ytmusic, mock_rate_limiter):
    """Test retry on 429 rate limit error."""
    # First call raises 429, second succeeds
    mock_ytmusic.search.side_effect = [
        YTMusicServerError("429 Too Many Requests"),
        [{'videoId': 'success', 'title': 'Test', 'artists': []}]
    ]
    
    results = searcher.search_track("Test", ["Artist"])
    
    # Should have retried
    assert mock_ytmusic.search.call_count == 2
    
    # Should have called handle_429
    mock_rate_limiter.handle_429.assert_called_once()
    
    # Should return results from second attempt
    assert len(results) == 1
    assert results[0]['videoId'] == 'success'


@patch('src.searchers.youtube_searcher.time.sleep')
def test_search_429_error_max_retries(mock_sleep, searcher, mock_ytmusic, mock_rate_limiter):
    """Test max retries on repeated 429 errors."""
    # All attempts fail with 429
    mock_ytmusic.search.side_effect = YTMusicServerError("429 Too Many Requests")
    
    results = searcher.search_track("Test", ["Artist"])
    
    # Should retry max times (3 attempts total)
    assert mock_ytmusic.search.call_count == 3
    
    # Should return empty list after max retries
    assert results == []


# ============================================================================
# Error Handling Tests - Network Errors
# ============================================================================

@patch('src.searchers.youtube_searcher.time.sleep')
def test_search_connection_error_retry(mock_sleep, searcher, mock_ytmusic):
    """Test retry on connection error with exponential backoff."""
    # First two calls fail, third succeeds
    mock_ytmusic.search.side_effect = [
        ConnectionError("Network unreachable"),
        ConnectionError("Network unreachable"),
        [{'videoId': 'success', 'title': 'Test', 'artists': []}]
    ]
    
    results = searcher.search_track("Test", ["Artist"])
    
    # Should have retried twice
    assert mock_ytmusic.search.call_count == 3
    
    # Should have exponential backoff delays: 1s, 2s, then 1s search delay
    sleep_calls = [call_args[0][0] for call_args in mock_sleep.call_args_list]
    assert 1.0 in sleep_calls  # First retry
    assert 2.0 in sleep_calls  # Second retry
    
    # Should succeed on third attempt
    assert len(results) == 1


@patch('src.searchers.youtube_searcher.time.sleep')
def test_search_connection_error_max_retries(mock_sleep, searcher, mock_ytmusic):
    """Test max retries exceeded for connection errors."""
    # All attempts fail with connection error
    mock_ytmusic.search.side_effect = ConnectionError("Network unreachable")
    
    results = searcher.search_track("Test", ["Artist"])
    
    # Should retry max times (3 attempts)
    assert mock_ytmusic.search.call_count == 3
    
    # Should return empty list
    assert results == []


@patch('src.searchers.youtube_searcher.time.sleep')
def test_search_server_error_retry(mock_sleep, searcher, mock_ytmusic):
    """Test retry on server error."""
    # First call fails, second succeeds
    mock_ytmusic.search.side_effect = [
        YTMusicServerError("500 Internal Server Error"),
        [{'videoId': 'success', 'title': 'Test', 'artists': []}]
    ]
    
    results = searcher.search_track("Test", ["Artist"])
    
    # Should have retried
    assert mock_ytmusic.search.call_count == 2
    assert len(results) == 1


@patch('src.searchers.youtube_searcher.time.sleep')
def test_search_server_error_max_retries(mock_sleep, searcher, mock_ytmusic):
    """Test max retries exceeded for server errors."""
    # All attempts fail with server error
    mock_ytmusic.search.side_effect = YTMusicServerError("500 Internal Server Error")
    
    results = searcher.search_track("Test", ["Artist"])
    
    # Should retry max times
    assert mock_ytmusic.search.call_count == 3
    
    # Should return empty list
    assert results == []


@patch('src.searchers.youtube_searcher.time.sleep')
def test_search_unexpected_error_retry(mock_sleep, searcher, mock_ytmusic):
    """Test retry on unexpected error."""
    # First call raises unexpected error, second succeeds
    mock_ytmusic.search.side_effect = [
        ValueError("Unexpected error"),
        [{'videoId': 'success', 'title': 'Test', 'artists': []}]
    ]
    
    results = searcher.search_track("Test", ["Artist"])
    
    # Should have retried
    assert mock_ytmusic.search.call_count == 2
    assert len(results) == 1


@patch('src.searchers.youtube_searcher.time.sleep')
def test_search_unexpected_error_max_retries(mock_sleep, searcher, mock_ytmusic):
    """Test max retries exceeded for unexpected errors."""
    # All attempts fail with unexpected error
    mock_ytmusic.search.side_effect = ValueError("Unexpected error")
    
    results = searcher.search_track("Test", ["Artist"])
    
    # Should retry max times
    assert mock_ytmusic.search.call_count == 3
    
    # Should return empty list
    assert results == []


# ============================================================================
# Result Validation Tests
# ============================================================================

@patch('src.searchers.youtube_searcher.time.sleep')
def test_search_validates_results(mock_sleep, searcher, mock_ytmusic):
    """Test result validation filters invalid results."""
    mock_ytmusic.search.return_value = [
        # Valid result
        {'videoId': 'valid1', 'title': 'Song 1', 'artists': [{'name': 'Artist'}]},
        # Missing videoId
        {'title': 'Song 2', 'artists': [{'name': 'Artist'}]},
        # Missing title
        {'videoId': 'invalid2', 'artists': [{'name': 'Artist'}]},
        # Not a dict
        "invalid string",
        # Valid result
        {'videoId': 'valid2', 'title': 'Song 3', 'artists': []},
    ]
    
    results = searcher.search_track("Test", ["Artist"])
    
    # Should only return 2 valid results
    assert len(results) == 2
    assert results[0]['videoId'] == 'valid1'
    assert results[1]['videoId'] == 'valid2'


@patch('src.searchers.youtube_searcher.time.sleep')
def test_search_adds_duration_seconds(mock_sleep, searcher, mock_ytmusic):
    """Test duration string is parsed to seconds."""
    mock_ytmusic.search.return_value = [
        {'videoId': 'id1', 'title': 'Song', 'artists': [], 'duration': '3:45'},
        {'videoId': 'id2', 'title': 'Song', 'artists': [], 'duration': '1:23:45'},
        {'videoId': 'id3', 'title': 'Song', 'artists': []},  # No duration
    ]
    
    results = searcher.search_track("Test", ["Artist"])
    
    assert results[0]['duration_seconds'] == 225  # 3:45 = 225s
    assert results[1]['duration_seconds'] == 5025  # 1:23:45 = 5025s
    assert 'duration_seconds' not in results[2]  # No duration


@patch('src.searchers.youtube_searcher.time.sleep')
def test_search_handles_missing_artists(mock_sleep, searcher, mock_ytmusic):
    """Test results without artists field get empty list."""
    mock_ytmusic.search.return_value = [
        {'videoId': 'id1', 'title': 'Song'},  # Missing artists
    ]
    
    results = searcher.search_track("Test", ["Artist"])
    
    assert len(results) == 1
    assert results[0]['artists'] == []


# ============================================================================
# Duration Parsing Tests
# ============================================================================

def test_parse_duration_minutes_seconds(searcher):
    """Test parsing MM:SS format."""
    assert searcher._parse_duration("3:45") == 225
    assert searcher._parse_duration("0:30") == 30
    assert searcher._parse_duration("10:00") == 600


def test_parse_duration_hours_minutes_seconds(searcher):
    """Test parsing HH:MM:SS format."""
    assert searcher._parse_duration("1:23:45") == 5025
    assert searcher._parse_duration("0:03:30") == 210
    assert searcher._parse_duration("2:00:00") == 7200


def test_parse_duration_invalid(searcher):
    """Test parsing invalid duration formats."""
    assert searcher._parse_duration("invalid") is None
    assert searcher._parse_duration("1:2:3:4") is None
    assert searcher._parse_duration("") is None


# ============================================================================
# Integration Tests
# ============================================================================

@patch('src.searchers.youtube_searcher.time.sleep')
def test_real_world_search_the_weeknd(mock_sleep, searcher, mock_ytmusic):
    """Test real-world example: The Weeknd - Blinding Lights."""
    mock_ytmusic.search.return_value = [
        {
            'videoId': 'abc123',
            'title': 'The Weeknd - Blinding Lights (Official Video)',
            'artists': [{'name': 'The Weeknd'}],
            'album': {'name': 'After Hours'},
            'duration': '3:20'
        }
    ]
    
    results = searcher.search_track("Blinding Lights", ["The Weeknd"])
    
    assert len(results) == 1
    assert results[0]['videoId'] == 'abc123'
    assert results[0]['duration_seconds'] == 200
    
    # Verify sanitized query
    call_kwargs = mock_ytmusic.search.call_args[1]
    assert 'the weeknd' in call_kwargs['query'].lower()
    assert 'blinding lights' in call_kwargs['query'].lower()


@patch('src.searchers.youtube_searcher.time.sleep')
def test_real_world_isrc_search(mock_sleep, searcher, mock_ytmusic):
    """Test real-world ISRC search."""
    mock_ytmusic.search.return_value = [
        {
            'videoId': 'isrc_match',
            'title': 'Blinding Lights',
            'artists': [{'name': 'The Weeknd'}],
            'duration': '3:20'
        }
    ]
    
    result = searcher.search_by_isrc("USRC17607839")
    
    assert result is not None
    assert result['videoId'] == 'isrc_match'
    
    # Verify ISRC query format
    call_kwargs = mock_ytmusic.search.call_args[1]
    assert call_kwargs['query'] == 'isrc:USRC17607839'
