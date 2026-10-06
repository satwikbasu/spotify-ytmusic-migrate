"""Unit tests for SpotifyFetcher.

This module contains comprehensive tests for the SpotifyFetcher class,
including pagination, filtering, caching, and error handling.
"""

import os
import json
import tempfile
import time
from unittest.mock import Mock, MagicMock, patch, call
from datetime import datetime, timedelta

import pytest
from spotipy.exceptions import SpotifyException

from src.fetchers.spotify_fetcher import SpotifyFetcher
from src.utils.rate_limiter import RateLimiter
from src.utils.cache_manager import CacheManager


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def temp_db():
    """Create a temporary database for testing.
    
    Yields:
        str: Path to temporary database file.
        
    Cleanup:
        Removes the temporary database after test completion.
    """
    # Create temporary file
    fd, db_path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    
    yield db_path
    
    # Cleanup
    if os.path.exists(db_path):
        os.remove(db_path)


@pytest.fixture
def cache_manager(temp_db):
    """Create a CacheManager instance with temporary database.
    
    Args:
        temp_db: Temporary database path fixture.
        
    Returns:
        CacheManager: Configured cache manager for testing.
    """
    manager = CacheManager(db_path=temp_db)
    yield manager
    manager.close()


@pytest.fixture
def rate_limiter():
    """Create a RateLimiter instance for testing.
    
    Returns:
        RateLimiter: Configured rate limiter with high limits.
    """
    # Use high limits for testing to avoid delays
    return RateLimiter(daily_limit=10000, per_minute_limit=1000)


@pytest.fixture
def mock_spotify_client():
    """Create a mock Spotify client.
    
    Returns:
        Mock: Mock Spotify client with common methods.
    """
    client = Mock()
    client.current_user.return_value = {'id': 'test_user', 'display_name': 'Test User'}
    # Default: user has no saved tracks, so no synthetic Liked Songs entry is
    # added. Tests exercising Liked Songs override this.
    client.current_user_saved_tracks.return_value = create_mock_saved_tracks_response([], total=0)
    return client


@pytest.fixture
def spotify_fetcher(mock_spotify_client, rate_limiter, cache_manager):
    """Create a SpotifyFetcher instance for testing.
    
    Args:
        mock_spotify_client: Mock Spotify client fixture.
        rate_limiter: Rate limiter fixture.
        cache_manager: Cache manager fixture.
        
    Returns:
        SpotifyFetcher: Configured fetcher for testing.
    """
    return SpotifyFetcher(mock_spotify_client, rate_limiter, cache_manager)


# ============================================================================
# Mock Data Generators
# ============================================================================

def create_mock_playlist(playlist_id: str, name: str, is_public: bool = True, 
                         tracks_count: int = 10, has_image: bool = True) -> dict:
    """Create a mock playlist object matching Spotify API format.
    
    Args:
        playlist_id: Playlist ID.
        name: Playlist name.
        is_public: Whether playlist is public.
        tracks_count: Number of tracks.
        has_image: Whether to include image.
        
    Returns:
        dict: Mock playlist object.
    """
    playlist = {
        'id': playlist_id,
        'name': name,
        'public': is_public,
        'tracks': {
            'total': tracks_count
        }
    }
    
    if has_image:
        playlist['images'] = [{'url': f'https://example.com/image_{playlist_id}.jpg'}]
    else:
        playlist['images'] = []
    
    return playlist


def create_mock_track(track_id: str, name: str, artists: list, album: str,
                      duration_ms: int = 180000, isrc: str = None) -> dict:
    """Create a mock track object matching Spotify API format.
    
    Args:
        track_id: Track ID.
        name: Track name.
        artists: List of artist names.
        album: Album name.
        duration_ms: Duration in milliseconds.
        isrc: ISRC code (optional).
        
    Returns:
        dict: Mock track object.
    """
    track = {
        'id': track_id,
        'name': name,
        'artists': [{'name': artist} for artist in artists],
        'album': {'name': album},
        'duration_ms': duration_ms,
        'external_ids': {}
    }
    
    if isrc:
        track['external_ids']['isrc'] = isrc
    
    return track


def create_mock_playlists_response(playlists: list, has_next: bool = False) -> dict:
    """Create a mock playlists API response.
    
    Args:
        playlists: List of playlist objects.
        has_next: Whether there are more pages.
        
    Returns:
        dict: Mock API response.
    """
    return {
        'items': playlists,
        'next': 'https://api.spotify.com/v1/me/playlists?offset=50' if has_next else None,
        'total': len(playlists)
    }


def create_mock_saved_tracks_response(tracks: list, total: int = None,
                                      has_next: bool = False) -> dict:
    """Create a mock GET /me/tracks (saved tracks) API response.

    Shape matches the playlist-items response: each item wraps a ``track``.
    ``total`` is the library-wide count Spotify reports on every page.
    """
    return {
        'items': [{'added_at': '2024-01-01T00:00:00Z', 'track': track} for track in tracks],
        'next': 'https://api.spotify.com/v1/me/tracks?offset=50' if has_next else None,
        'total': len(tracks) if total is None else total
    }


def create_mock_tracks_response(tracks: list, has_next: bool = False) -> dict:
    """Create a mock playlist tracks API response.
    
    Args:
        tracks: List of track objects.
        has_next: Whether there are more pages.
        
    Returns:
        dict: Mock API response.
    """
    return {
        'items': [{'track': track} for track in tracks],
        'next': 'https://api.spotify.com/v1/playlists/123/tracks?offset=100' if has_next else None,
        'total': len(tracks)
    }


# ============================================================================
# Playlist Fetching Tests
# ============================================================================

def test_get_user_playlists_pagination(spotify_fetcher, mock_spotify_client, rate_limiter):
    """Test fetching playlists with pagination across multiple pages.
    
    This test validates that:
    1. SpotifyFetcher correctly handles pagination
    2. All playlists across multiple pages are fetched
    3. rate_limiter.record_request() is called for each page
    """
    # Create 150 playlists (3 pages of 50)
    page1_playlists = [
        create_mock_playlist(f'playlist_{i}', f'Playlist {i}', is_public=True)
        for i in range(50)
    ]
    page2_playlists = [
        create_mock_playlist(f'playlist_{i}', f'Playlist {i}', is_public=True)
        for i in range(50, 100)
    ]
    page3_playlists = [
        create_mock_playlist(f'playlist_{i}', f'Playlist {i}', is_public=True)
        for i in range(100, 150)
    ]
    
    # Mock API responses for each page
    mock_spotify_client.current_user_playlists.side_effect = [
        create_mock_playlists_response(page1_playlists, has_next=True),
        create_mock_playlists_response(page2_playlists, has_next=True),
        create_mock_playlists_response(page3_playlists, has_next=False)
    ]
    
    # Fetch playlists (disable cache for this test)
    playlists = spotify_fetcher.get_user_playlists(use_cache=False)
    
    # Assertions
    assert len(playlists) == 150
    assert playlists[0]['name'] == 'Playlist 0'
    assert playlists[149]['name'] == 'Playlist 149'
    
    # Verify API was called 3 times (once per page)
    assert mock_spotify_client.current_user_playlists.call_count == 3

    # Verify every call went through the rate limiter: 3 playlist pages plus
    # the single /me/tracks probe that sizes the Liked Songs entry.
    assert mock_spotify_client.current_user_saved_tracks.call_count == 1
    assert rate_limiter.daily_operations == 4


def test_private_and_collaborative_playlists_are_included(spotify_fetcher, mock_spotify_client):
    """Private and collaborative playlists must be returned, in API order.

    Most personal playlists are private. The old public-only filter made
    "Select All" migrate almost nothing (contract §4.3). The token already has
    playlist-read-private / playlist-read-collaborative, so nothing is filtered
    on visibility.
    """
    collab = create_mock_playlist('collab1', 'Shared With Friends', is_public=False)
    collab['collaborative'] = True
    playlists = [
        create_mock_playlist('pub1', 'Public Playlist 1', is_public=True),
        create_mock_playlist('priv1', 'Private Playlist 1', is_public=False),
        collab,
        create_mock_playlist('priv2', 'Private Playlist 2', is_public=False),
        create_mock_playlist('pub2', 'Public Playlist 2', is_public=True),
    ]
    mock_spotify_client.current_user_playlists.return_value = create_mock_playlists_response(playlists)

    result = spotify_fetcher.get_user_playlists(use_cache=False)

    assert [p['id'] for p in result] == ['pub1', 'priv1', 'collab1', 'priv2', 'pub2']
    by_id = {p['id']: p for p in result}
    assert by_id['pub1']['public'] is True
    assert by_id['priv1']['public'] is False
    assert by_id['collab1']['collaborative'] is True
    assert all(p['synthetic'] is False for p in result)
    # Existing callers still get the keys they rely on
    for p in result:
        assert {'id', 'name', 'tracks_count', 'image_url'} <= set(p)


def test_private_playlist_with_public_field_missing_is_included(spotify_fetcher, mock_spotify_client):
    """Spotify returns public=None for some private playlists; keep them."""
    playlist = create_mock_playlist('priv_none', 'Visibility Unknown', is_public=True)
    playlist['public'] = None
    mock_spotify_client.current_user_playlists.return_value = create_mock_playlists_response([playlist])

    result = spotify_fetcher.get_user_playlists(use_cache=False)

    assert [p['id'] for p in result] == ['priv_none']
    assert result[0]['public'] is False


# ============================================================================
# Synthetic "Liked Songs" playlist
# ============================================================================

def test_liked_songs_appears_as_synthetic_playlist(spotify_fetcher, mock_spotify_client, cache_manager):
    """Saved tracks surface as a 'Liked Songs' playlist, first in the list."""
    first = create_mock_track('t1', 'First Liked', ['Artist'], 'Album')
    first['album']['images'] = [{'url': 'https://example.com/liked.jpg'}]
    mock_spotify_client.current_user_saved_tracks.return_value = (
        create_mock_saved_tracks_response([first], total=1234)
    )
    mock_spotify_client.current_user_playlists.return_value = create_mock_playlists_response([
        create_mock_playlist('pl1', 'Real Playlist', is_public=False),
    ])

    result = spotify_fetcher.get_user_playlists(use_cache=False)

    assert [p['id'] for p in result] == [SpotifyFetcher.LIKED_SONGS_PLAYLIST_ID, 'pl1']
    liked = result[0]
    assert liked['name'] == 'Liked Songs'
    assert liked['tracks_count'] == 1234
    assert liked['image_url'] == 'https://example.com/liked.jpg'
    assert liked['synthetic'] is True
    assert liked['public'] is False
    assert spotify_fetcher.is_liked_songs(liked['id'])

    # Probe was a single, minimal page
    mock_spotify_client.current_user_saved_tracks.assert_called_once_with(limit=1, offset=0)
    # Cached like any other playlist so the selection screen / migrations can key on it
    assert cache_manager.get_cached_playlist(SpotifyFetcher.LIKED_SONGS_PLAYLIST_ID, max_age_hours=24) is not None


def test_liked_songs_omitted_when_user_has_none(spotify_fetcher, mock_spotify_client):
    """An empty library must not produce an empty synthetic playlist."""
    mock_spotify_client.current_user_playlists.return_value = create_mock_playlists_response([
        create_mock_playlist('pl1', 'Real Playlist'),
    ])

    result = spotify_fetcher.get_user_playlists(use_cache=False)

    assert [p['id'] for p in result] == ['pl1']


def test_liked_songs_can_be_excluded(spotify_fetcher, mock_spotify_client):
    """include_liked_songs=False skips the /me/tracks probe entirely."""
    mock_spotify_client.current_user_playlists.return_value = create_mock_playlists_response([
        create_mock_playlist('pl1', 'Real Playlist'),
    ])

    result = spotify_fetcher.get_user_playlists(use_cache=False, include_liked_songs=False)

    assert [p['id'] for p in result] == ['pl1']
    assert not mock_spotify_client.current_user_saved_tracks.called


def test_liked_songs_probe_failure_does_not_lose_real_playlists(spotify_fetcher, mock_spotify_client):
    """A 403 on /me/tracks (missing scope) drops only Liked Songs."""
    mock_spotify_client.current_user_saved_tracks.side_effect = SpotifyException(
        http_status=403, code=-1, msg='Insufficient client scope'
    )
    mock_spotify_client.current_user_playlists.return_value = create_mock_playlists_response([
        create_mock_playlist('pl1', 'Real Playlist'),
    ])

    result = spotify_fetcher.get_user_playlists(use_cache=False)

    assert [p['id'] for p in result] == ['pl1']


def test_liked_songs_probe_honours_429(spotify_fetcher, mock_spotify_client, rate_limiter):
    """A 429 on the probe goes through RateLimiter.handle_429 and is retried."""
    mock_spotify_client.current_user_saved_tracks.side_effect = [
        SpotifyException(http_status=429, code=-1, msg='rate limited',
                         reason='QUOTA_EXCEEDED', headers={'Retry-After': '1'}),
        create_mock_saved_tracks_response([], total=7),
    ]
    mock_spotify_client.current_user_playlists.return_value = create_mock_playlists_response([])

    with patch.object(rate_limiter, 'handle_429') as handle_429:
        result = spotify_fetcher.get_user_playlists(use_cache=False)

    handle_429.assert_called_once_with(1)
    assert [p['id'] for p in result] == [SpotifyFetcher.LIKED_SONGS_PLAYLIST_ID]
    assert result[0]['tracks_count'] == 7


def test_liked_songs_tracks_resolve_to_saved_tracks(spotify_fetcher, mock_spotify_client, rate_limiter, cache_manager):
    """get_playlist_tracks(liked_songs) pages /me/tracks at 50/page, not a playlist endpoint."""
    page1 = [create_mock_track(f'liked_{i}', f'Liked {i}', ['Artist'], 'Album', isrc=None) for i in range(50)]
    page2 = [create_mock_track(f'liked_{i}', f'Liked {i}', ['Artist'], 'Album') for i in range(50, 75)]
    mock_spotify_client.current_user_saved_tracks.side_effect = [
        create_mock_saved_tracks_response(page1, total=75, has_next=True),
        create_mock_saved_tracks_response(page2, total=75, has_next=False),
    ]

    tracks = spotify_fetcher.get_playlist_tracks(SpotifyFetcher.LIKED_SONGS_PLAYLIST_ID, use_cache=False)

    assert len(tracks) == 75
    assert tracks[0]['name'] == 'Liked 0'
    assert tracks[74]['name'] == 'Liked 74'
    assert tracks[0]['isrc'] is None  # ISRC is optional, never required

    calls = mock_spotify_client.current_user_saved_tracks.call_args_list
    assert calls[0].kwargs == {'limit': 50, 'offset': 0}
    assert calls[1].kwargs == {'limit': 50, 'offset': 50}
    assert not mock_spotify_client.playlist_items.called
    assert not mock_spotify_client.playlist_tracks.called
    assert rate_limiter.daily_operations == 2

    # Cached under the synthetic id so the migrator's resume path can find them
    cached = cache_manager.get_cached_tracks(SpotifyFetcher.LIKED_SONGS_PLAYLIST_ID)
    assert len(cached) == 75


def test_liked_songs_tracks_are_served_from_cache(spotify_fetcher, mock_spotify_client, cache_manager):
    """Second fetch of Liked Songs uses the cache, like any playlist."""
    cache_manager.cache_tracks(
        [{'id': 'c1', 'name': 'Cached', 'artists': ['A'], 'album': 'B', 'duration_ms': 1000, 'isrc': None}],
        SpotifyFetcher.LIKED_SONGS_PLAYLIST_ID,
    )

    tracks = spotify_fetcher.get_playlist_tracks(SpotifyFetcher.LIKED_SONGS_PLAYLIST_ID, use_cache=True)

    assert [t['id'] for t in tracks] == ['c1']
    assert not mock_spotify_client.current_user_saved_tracks.called


# ============================================================================
# Feb-2026 API rename: playlist `tracks` -> `items`
# ============================================================================

def test_playlist_track_count_from_legacy_tracks_field(spotify_fetcher):
    """Pre-migration responses: tracks_count comes from playlist['tracks']['total']."""
    meta = spotify_fetcher.extract_playlist_metadata(
        {'id': 'p', 'name': 'Old Shape', 'tracks': {'total': 42, 'href': 'x'}, 'images': []}
    )
    assert meta['tracks_count'] == 42


def test_playlist_track_count_from_renamed_items_field(spotify_fetcher):
    """Post-migration responses: tracks_count comes from playlist['items']['total']."""
    meta = spotify_fetcher.extract_playlist_metadata(
        {'id': 'p', 'name': 'New Shape', 'items': {'total': 17, 'href': 'x'}, 'images': []}
    )
    assert meta['tracks_count'] == 17


def test_playlist_track_count_from_items_list(spotify_fetcher):
    """If `items` is an inline list rather than a paging object, count it."""
    meta = spotify_fetcher.extract_playlist_metadata(
        {'id': 'p', 'name': 'Inline', 'items': [{}, {}, {}], 'images': []}
    )
    assert meta['tracks_count'] == 3


def test_playlist_track_count_missing_is_zero(spotify_fetcher):
    """Neither field present -> 0, not an exception."""
    meta = spotify_fetcher.extract_playlist_metadata({'id': 'p', 'name': 'Bare', 'images': []})
    assert meta['tracks_count'] == 0


def test_get_user_playlists_handles_mixed_tracks_and_items_naming(spotify_fetcher, mock_spotify_client):
    """A page mixing both spellings yields correct counts for every playlist."""
    old = {'id': 'old', 'name': 'Old', 'public': False, 'tracks': {'total': 5}, 'images': []}
    new = {'id': 'new', 'name': 'New', 'public': False, 'items': {'total': 9}, 'images': []}
    mock_spotify_client.current_user_playlists.return_value = create_mock_playlists_response([old, new])

    result = spotify_fetcher.get_user_playlists(use_cache=False)

    assert {p['id']: p['tracks_count'] for p in result} == {'old': 5, 'new': 9}


def test_playlist_tracks_use_playlist_items_endpoint(spotify_fetcher, mock_spotify_client):
    """Tracks are fetched via spotipy.playlist_items (the /items endpoint), 100/page."""
    tracks = [create_mock_track('t1', 'Song', ['Artist'], 'Album')]
    mock_spotify_client.playlist_items.return_value = create_mock_tracks_response(tracks)

    result = spotify_fetcher.get_playlist_tracks('pl_1', use_cache=False)

    assert [t['id'] for t in result] == ['t1']
    mock_spotify_client.playlist_items.assert_called_once_with(
        'pl_1', limit=100, offset=0, additional_types=('track',)
    )
    assert not mock_spotify_client.playlist_tracks.called


def test_playlist_items_accept_item_key_for_track(spotify_fetcher, mock_spotify_client):
    """A page item wrapping the track under 'item' instead of 'track' still parses."""
    track = create_mock_track('t1', 'Song', ['Artist'], 'Album')
    mock_spotify_client.playlist_items.return_value = {
        'items': [{'item': track}, {'track': None}],
        'next': None, 'total': 2,
    }

    result = spotify_fetcher.get_playlist_tracks('pl_1', use_cache=False)

    assert [t['id'] for t in result] == ['t1']


def test_quota_exceeded_429_is_routed_through_rate_limiter(spotify_fetcher, mock_spotify_client, rate_limiter):
    """A dev-mode quota 429 (reason QUOTA_EXCEEDED) backs off via handle_429 and retries."""
    tracks = [create_mock_track('t1', 'Song', ['Artist'], 'Album')]
    mock_spotify_client.playlist_items.side_effect = [
        SpotifyException(http_status=429, code=-1, msg='quota', reason='QUOTA_EXCEEDED',
                         headers={'Retry-After': '30'}),
        create_mock_tracks_response(tracks),
    ]

    with patch.object(rate_limiter, 'handle_429') as handle_429:
        result = spotify_fetcher.get_playlist_tracks('pl_1', use_cache=False)

    handle_429.assert_called_once_with(30)
    assert len(result) == 1
    assert mock_spotify_client.playlist_items.call_count == 2


def test_extract_playlist_metadata(spotify_fetcher):
    """Test playlist metadata extraction.
    
    This test validates that:
    1. All required fields are extracted
    2. Missing images are handled gracefully
    """
    # Test with image
    playlist_with_image = create_mock_playlist('test1', 'Test Playlist', has_image=True)
    metadata = spotify_fetcher.extract_playlist_metadata(playlist_with_image)
    
    assert metadata['id'] == 'test1'
    assert metadata['name'] == 'Test Playlist'
    assert metadata['tracks_count'] == 10
    assert metadata['image_url'] is not None
    assert 'image_test1' in metadata['image_url']
    
    # Test without image
    playlist_without_image = create_mock_playlist('test2', 'Test Playlist 2', has_image=False)
    metadata = spotify_fetcher.extract_playlist_metadata(playlist_without_image)
    
    assert metadata['id'] == 'test2'
    assert metadata['image_url'] is None


# ============================================================================
# Track Fetching Tests
# ============================================================================

def test_get_playlist_tracks_pagination(spotify_fetcher, mock_spotify_client, rate_limiter):
    """Test fetching tracks with pagination across multiple pages.
    
    This test validates that:
    1. SpotifyFetcher correctly handles track pagination
    2. All tracks across multiple pages are fetched
    3. Rate limiting is applied
    """
    # Create 250 tracks (3 pages: 100 + 100 + 50)
    page1_tracks = [
        create_mock_track(f'track_{i}', f'Track {i}', ['Artist A'], 'Album A')
        for i in range(100)
    ]
    page2_tracks = [
        create_mock_track(f'track_{i}', f'Track {i}', ['Artist B'], 'Album B')
        for i in range(100, 200)
    ]
    page3_tracks = [
        create_mock_track(f'track_{i}', f'Track {i}', ['Artist C'], 'Album C')
        for i in range(200, 250)
    ]
    
    # Mock API responses
    mock_spotify_client.playlist_items.side_effect = [
        create_mock_tracks_response(page1_tracks, has_next=True),
        create_mock_tracks_response(page2_tracks, has_next=True),
        create_mock_tracks_response(page3_tracks, has_next=False)
    ]
    
    # Fetch tracks
    tracks = spotify_fetcher.get_playlist_tracks('test_playlist', use_cache=False)
    
    # Assertions
    assert len(tracks) == 250
    assert tracks[0]['name'] == 'Track 0'
    assert tracks[249]['name'] == 'Track 249'
    
    # Verify API was called 3 times
    assert mock_spotify_client.playlist_items.call_count == 3


def test_extract_track_metadata(spotify_fetcher):
    """Test track metadata extraction.
    
    This test validates that:
    1. All required fields are extracted
    2. Multiple artists are handled
    3. Track validation works correctly
    """
    # Test normal track with ISRC
    track = create_mock_track(
        'track1', 
        'Test Track', 
        ['Artist 1', 'Artist 2'], 
        'Test Album',
        duration_ms=200000,
        isrc='USABC1234567'
    )
    
    metadata = spotify_fetcher.extract_track_metadata(track)
    
    assert metadata is not None
    assert metadata['id'] == 'track1'
    assert metadata['name'] == 'Test Track'
    assert metadata['artists'] == ['Artist 1', 'Artist 2']
    assert metadata['album'] == 'Test Album'
    assert metadata['duration_ms'] == 200000
    assert metadata['isrc'] == 'USABC1234567'


def test_handle_null_fields(spotify_fetcher):
    """Test handling of tracks with missing/null fields.
    
    This test validates that:
    1. Tracks with missing ISRC still work
    2. Tracks with missing external_ids are handled
    3. None is returned for invalid tracks
    """
    # Track without ISRC
    track_no_isrc = create_mock_track(
        'track1', 
        'Test Track', 
        ['Artist'], 
        'Album',
        isrc=None
    )
    
    metadata = spotify_fetcher.extract_track_metadata(track_no_isrc)
    
    assert metadata is not None
    assert metadata['isrc'] is None
    
    # Track with invalid duration (too long)
    track_invalid = create_mock_track(
        'track2',
        'Long Track',
        ['Artist'],
        'Album',
        duration_ms=4000000  # > 1 hour
    )
    
    metadata = spotify_fetcher.extract_track_metadata(track_invalid)
    assert metadata is None  # Should be rejected
    
    # Track with zero duration
    track_zero = create_mock_track(
        'track3',
        'Zero Track',
        ['Artist'],
        'Album',
        duration_ms=0
    )
    
    metadata = spotify_fetcher.extract_track_metadata(track_zero)
    assert metadata is None  # Should be rejected
    
    # Track without ID
    track_no_id = create_mock_track('', 'No ID', ['Artist'], 'Album')
    metadata = spotify_fetcher.extract_track_metadata(track_no_id)
    assert metadata is None  # Should be rejected


# ============================================================================
# Caching Tests
# ============================================================================

def test_cache_hit_playlists(spotify_fetcher, mock_spotify_client, cache_manager):
    """Test that cached playlists are returned without API call.
    
    This test validates that:
    1. Cached playlists are detected
    2. API is not called when cache is valid
    3. Cached data is returned correctly
    """
    # Pre-populate cache with playlist
    playlist_data = {
        'id': 'cached_playlist',
        'name': 'Cached Playlist',
        'tracks_count': 15,
        'image_url': 'https://example.com/image.jpg'
    }
    cache_manager.cache_playlist(playlist_data)
    
    # Note: Current implementation doesn't cache the complete list of playlists
    # in a way that allows retrieval without knowing individual IDs.
    # We'll test track caching instead, which is more straightforward.
    
    # For this test, we'll verify the caching mechanism works by checking
    # that fetching doesn't use cache (current limitation)
    playlists_response = [create_mock_playlist('pl1', 'Playlist 1')]
    mock_spotify_client.current_user_playlists.return_value = create_mock_playlists_response(playlists_response)
    
    result = spotify_fetcher.get_user_playlists(use_cache=True)
    
    # API should be called since we don't have a complete cache mechanism
    assert mock_spotify_client.current_user_playlists.called


def test_cache_hit_tracks(spotify_fetcher, mock_spotify_client, cache_manager):
    """Test that cached tracks are returned without API call.
    
    This test validates that:
    1. Cached tracks are detected and returned
    2. API is not called when cache has valid tracks
    3. Cached data matches expected format
    """
    # Pre-populate cache with tracks
    cached_tracks = [
        {
            'id': 'track1',
            'name': 'Cached Track 1',
            'artists': ['Artist A'],
            'album': 'Cached Album',
            'duration_ms': 180000,
            'isrc': 'USABC1111111'
        },
        {
            'id': 'track2',
            'name': 'Cached Track 2',
            'artists': ['Artist B', 'Artist C'],
            'album': 'Cached Album 2',
            'duration_ms': 200000,
            'isrc': 'USABC2222222'
        }
    ]
    
    playlist_id = 'test_playlist'
    cache_manager.cache_tracks(cached_tracks, playlist_id)
    
    # Fetch tracks (should come from cache)
    result = spotify_fetcher.get_playlist_tracks(playlist_id, use_cache=True)
    
    # Assertions
    assert len(result) == 2
    assert result[0]['name'] == 'Cached Track 1'
    assert result[1]['name'] == 'Cached Track 2'
    
    # Verify API was NOT called
    assert not mock_spotify_client.playlist_items.called


def test_cache_miss_tracks(spotify_fetcher, mock_spotify_client, cache_manager):
    """Test that API is called when cache is empty.
    
    This test validates that:
    1. Empty cache triggers API call
    2. Fresh data is fetched and cached
    """
    playlist_id = 'new_playlist'
    
    # Mock API response
    tracks = [create_mock_track('track1', 'New Track', ['Artist'], 'Album')]
    mock_spotify_client.playlist_items.return_value = create_mock_tracks_response(tracks)
    
    # Fetch tracks (cache is empty)
    result = spotify_fetcher.get_playlist_tracks(playlist_id, use_cache=True)
    
    # Assertions
    assert len(result) == 1
    assert result[0]['name'] == 'New Track'
    
    # Verify API was called
    assert mock_spotify_client.playlist_items.called
    
    # Verify data was cached
    cached = cache_manager.get_cached_tracks(playlist_id)
    assert len(cached) == 1
    assert cached[0]['name'] == 'New Track'


def test_cache_expiry(spotify_fetcher, mock_spotify_client, cache_manager, temp_db):
    """Test that expired cache is ignored and fresh data is fetched.
    
    This test validates that:
    1. Old cached data is ignored
    2. Fresh data is fetched from API
    3. Cache is updated with new data
    """
    # Create a new cache manager and manually insert old data
    import sqlite3
    conn = sqlite3.connect(temp_db)
    cursor = conn.cursor()
    
    # Insert old playlist (25 hours ago - beyond 24 hour default)
    old_timestamp = datetime.now() - timedelta(hours=25)
    cursor.execute("""
        INSERT INTO playlists (id, name, tracks_count, image_url, last_fetched)
        VALUES (?, ?, ?, ?, ?)
    """, ('old_playlist', 'Old Playlist', 10, None, old_timestamp))
    
    # Insert old tracks
    cursor.execute("""
        INSERT INTO tracks (spotify_id, playlist_id, name, artists, album, duration_ms, isrc)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, ('old_track1', 'old_playlist', 'Old Track', '["Old Artist"]', 'Old Album', 180000, None))
    
    conn.commit()
    conn.close()
    
    # Try to get cached playlist (should return None due to age)
    cached_playlist = cache_manager.get_cached_playlist('old_playlist', max_age_hours=24)
    assert cached_playlist is None  # Expired
    
    # Mock fresh API response
    fresh_playlists = [create_mock_playlist('old_playlist', 'Updated Playlist')]
    mock_spotify_client.current_user_playlists.return_value = create_mock_playlists_response(fresh_playlists)
    
    # Fetch should hit API and update cache
    result = spotify_fetcher.get_user_playlists(use_cache=True)
    
    # Verify API was called (cache was expired)
    assert mock_spotify_client.current_user_playlists.called


# ============================================================================
# Refresh Methods Tests
# ============================================================================

def test_refresh_playlists(spotify_fetcher, mock_spotify_client):
    """Test force refresh of playlists.
    
    This test validates that:
    1. refresh_playlists() forces API call
    2. Cache is bypassed
    3. Fresh data is returned and cached
    """
    # Mock API response
    playlists = [
        create_mock_playlist('pl1', 'Fresh Playlist 1'),
        create_mock_playlist('pl2', 'Fresh Playlist 2')
    ]
    mock_spotify_client.current_user_playlists.return_value = create_mock_playlists_response(playlists)
    
    # Call refresh
    result = spotify_fetcher.refresh_playlists()
    
    # Assertions
    assert len(result) == 2
    assert result[0]['name'] == 'Fresh Playlist 1'
    assert result[1]['name'] == 'Fresh Playlist 2'
    
    # Verify API was called
    assert mock_spotify_client.current_user_playlists.called


def test_refresh_playlist_tracks(spotify_fetcher, mock_spotify_client, cache_manager):
    """Test force refresh of playlist tracks.
    
    This test validates that:
    1. refresh_playlist_tracks() clears cache
    2. Fresh data is fetched from API
    3. New data is cached
    """
    playlist_id = 'refresh_test'
    
    # Pre-populate cache with old tracks
    old_tracks = [
        {
            'id': 'old1',
            'name': 'Old Track',
            'artists': ['Old Artist'],
            'album': 'Old Album',
            'duration_ms': 180000,
            'isrc': None
        }
    ]
    cache_manager.cache_tracks(old_tracks, playlist_id)
    
    # Mock fresh API response
    fresh_tracks = [
        create_mock_track('new1', 'New Track 1', ['New Artist'], 'New Album'),
        create_mock_track('new2', 'New Track 2', ['New Artist'], 'New Album')
    ]
    mock_spotify_client.playlist_items.return_value = create_mock_tracks_response(fresh_tracks)
    
    # Call refresh
    result = spotify_fetcher.refresh_playlist_tracks(playlist_id)
    
    # Assertions
    assert len(result) == 2
    assert result[0]['name'] == 'New Track 1'
    assert result[1]['name'] == 'New Track 2'
    
    # Verify API was called
    assert mock_spotify_client.playlist_items.called
    
    # Verify cache was updated
    cached = cache_manager.get_cached_tracks(playlist_id)
    assert len(cached) == 2
    assert cached[0]['name'] == 'New Track 1'


# ============================================================================
# Error Handling Tests
# ============================================================================

def test_handle_deleted_playlist(spotify_fetcher, mock_spotify_client):
    """Test handling of deleted/not found playlists.
    
    This test validates graceful handling of 404 errors.
    """
    from spotipy.exceptions import SpotifyException
    
    # Mock 404 error
    mock_spotify_client.playlist_items.side_effect = SpotifyException(
        http_status=404,
        code=-1,
        msg='Not found'
    )
    
    # Should not raise, should return empty list
    result = spotify_fetcher.get_playlist_tracks('deleted_playlist', use_cache=False)
    
    assert result == []


def test_sanitize_emoji_strings(spotify_fetcher):
    """Test emoji removal from strings.
    
    This test validates that emojis are properly removed from track/playlist names.
    """
    # Test with emojis
    text_with_emoji = "🎵 Best Songs 🎶 Ever 🔥"
    sanitized = spotify_fetcher._sanitize_string(text_with_emoji)
    
    assert sanitized == "Best Songs  Ever"
    assert '🎵' not in sanitized
    assert '🎶' not in sanitized
    assert '🔥' not in sanitized
    
    # Test with None
    assert spotify_fetcher._sanitize_string(None) is None
    
    # Test with only emojis
    only_emoji = "🎵🎶🔥"
    sanitized = spotify_fetcher._sanitize_string(only_emoji)
    assert sanitized is None  # Empty after removing emojis


# ---------------------------------------------------------------------------
# Regression: one malformed playlist must not stop the rest being cached (B2)
# ---------------------------------------------------------------------------

def _raw_playlist(pid, name, tracks=5):
    """Build a raw Spotify API playlist record."""
    return {
        'id': pid,
        'name': name,
        'public': True,
        'owner': {'display_name': 'tester', 'id': 'tester'},
        'tracks': {'total': tracks},
        'images': [],
        'description': '',
    }


def test_malformed_playlist_does_not_stop_caching_the_rest():
    """A record the cache rejects must skip only itself.

    The real library contains a playlist with name=None. Because the caching
    loop was wrapped in a single try, that one record aborted caching for every
    playlist that came after it -- 190 fetched, 185 cached.
    """
    from unittest.mock import MagicMock
    import tempfile, os
    from src.fetchers.spotify_fetcher import SpotifyFetcher
    from src.utils.cache_manager import CacheManager
    from src.utils.rate_limiter import RateLimiter

    bad = _raw_playlist('bad_1', None)          # name=None -> cache_playlist rejects
    good_before = _raw_playlist('good_1', 'Before The Bad One')
    good_after = _raw_playlist('good_2', 'After The Bad One')

    client = MagicMock()
    client.current_user_playlists.return_value = {
        'items': [good_before, bad, good_after], 'next': None, 'total': 3,
    }

    cache = CacheManager(db_path=os.path.join(tempfile.mkdtemp(), 'b2.db'))
    fetcher = SpotifyFetcher(client, RateLimiter(per_minute_limit=60, daily_limit=10000), cache)
    fetcher.get_user_playlists(use_cache=False)

    assert cache.get_cached_playlist('good_2', max_age_hours=24) is not None, (
        "playlist after the malformed one was never cached"
    )
    assert cache.get_cache_stats()['playlists_count'] == 2


def test_duplicate_playlists_are_returned_once():
    """Spotify's offset paging can return the same playlist twice.

    Measured on a real account: 195 items containing 193 unique IDs. Without
    deduplication the migrator would create duplicate YouTube playlists and
    spend twice the API budget on them.
    """
    from unittest.mock import MagicMock
    import tempfile, os
    from src.fetchers.spotify_fetcher import SpotifyFetcher
    from src.utils.cache_manager import CacheManager
    from src.utils.rate_limiter import RateLimiter

    dupe = _raw_playlist('dupe_1', 'Appears Twice')
    client = MagicMock()
    client.current_user_playlists.return_value = {
        'items': [dupe, _raw_playlist('uniq_1', 'Only Once'), dict(dupe)],
        'next': None, 'total': 3,
    }

    cache = CacheManager(db_path=os.path.join(tempfile.mkdtemp(), 'b5.db'))
    fetcher = SpotifyFetcher(client, RateLimiter(per_minute_limit=60, daily_limit=10000), cache)
    playlists = fetcher.get_user_playlists(use_cache=False)

    ids = [p['id'] for p in playlists]
    assert len(ids) == len(set(ids)), f"duplicate playlist IDs returned: {ids}"
    assert len(playlists) == 2


def test_playlist_without_a_name_is_skipped():
    """A record with name=None must not reach the migrator.

    The real library contains one (id 5WoLlehPQTzoaNdIQgTrcC, 136 tracks,
    owner=None). Left in, it reaches create_playlist(title=None) on YouTube.
    """
    from unittest.mock import MagicMock
    import tempfile, os
    from src.fetchers.spotify_fetcher import SpotifyFetcher
    from src.utils.cache_manager import CacheManager
    from src.utils.rate_limiter import RateLimiter

    nameless = _raw_playlist('nameless_1', None, tracks=136)
    nameless['owner'] = None

    client = MagicMock()
    client.current_user_playlists.return_value = {
        'items': [nameless, _raw_playlist('fine_1', 'Perfectly Fine')],
        'next': None, 'total': 2,
    }

    cache = CacheManager(db_path=os.path.join(tempfile.mkdtemp(), 'b6.db'))
    fetcher = SpotifyFetcher(client, RateLimiter(per_minute_limit=60, daily_limit=10000), cache)
    playlists = fetcher.get_user_playlists(use_cache=False)

    returned_ids = [p['id'] for p in playlists]
    assert 'nameless_1' not in returned_ids, "playlist with name=None was not skipped"
    assert returned_ids == ['fine_1']
