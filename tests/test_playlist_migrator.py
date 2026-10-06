"""Unit tests for PlaylistMigrator class.

This module tests the complete migration pipeline including playlist creation,
track matching, caching, batch addition, and report generation.
"""

import pytest
from unittest.mock import Mock, patch, call
from ytmusicapi.exceptions import YTMusicServerError

from src.migrators.playlist_migrator import PlaylistMigrator


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_ytmusic():
    """Mock YTMusic client."""
    client = Mock()
    client.create_playlist.return_value = "PL123456"
    client.add_playlist_items.return_value = None
    return client


@pytest.fixture
def mock_searcher():
    """Mock YouTubeSearcher."""
    return Mock()


@pytest.fixture
def mock_matcher():
    """Mock TrackMatcher."""
    matcher = Mock()
    matcher.match_track.return_value = ("video123", 95.0)
    return matcher


@pytest.fixture
def mock_cache():
    """Mock CacheManager."""
    cache = Mock()
    cache.get_cached_match.return_value = None  # Default: cache miss
    return cache


@pytest.fixture
def mock_limiter():
    """Mock RateLimiter."""
    limiter = Mock()
    limiter.check_limit.return_value = True
    return limiter


@pytest.fixture
def migrator(mock_ytmusic, mock_searcher, mock_matcher, mock_cache, mock_limiter):
    """PlaylistMigrator instance with all mocks."""
    return PlaylistMigrator(
        mock_ytmusic,
        mock_searcher,
        mock_matcher,
        mock_cache,
        mock_limiter
    )


@pytest.fixture
def sample_tracks():
    """Sample Spotify tracks for testing."""
    return [
        {
            'name': 'Blinding Lights',
            'artists': ['The Weeknd'],
            'album': 'After Hours',
            'duration_ms': 200040,
            'id': 'track1',
            'isrc': 'USUG11904206'
        },
        {
            'name': 'Shape of You',
            'artists': ['Ed Sheeran'],
            'album': '÷',
            'duration_ms': 233713,
            'id': 'track2',
            'isrc': 'GBAHS1700024'
        }
    ]


# ============================================================================
# Initialization Tests
# ============================================================================

def test_migrator_initialization(mock_ytmusic, mock_searcher, mock_matcher, mock_cache, mock_limiter):
    """Test PlaylistMigrator initialization."""
    migrator = PlaylistMigrator(
        mock_ytmusic,
        mock_searcher,
        mock_matcher,
        mock_cache,
        mock_limiter
    )
    
    assert migrator.ytmusic_client == mock_ytmusic
    assert migrator.youtube_searcher == mock_searcher
    assert migrator.track_matcher == mock_matcher
    assert migrator.cache_manager == mock_cache
    assert migrator.rate_limiter == mock_limiter


def test_migrator_initialization_none_ytmusic(mock_searcher, mock_matcher, mock_cache, mock_limiter):
    """Test initialization rejects None ytmusic_client."""
    with pytest.raises(ValueError, match="ytmusic_client cannot be None"):
        PlaylistMigrator(None, mock_searcher, mock_matcher, mock_cache, mock_limiter)


def test_migrator_initialization_none_searcher(mock_ytmusic, mock_matcher, mock_cache, mock_limiter):
    """Test initialization rejects None youtube_searcher."""
    with pytest.raises(ValueError, match="youtube_searcher cannot be None"):
        PlaylistMigrator(mock_ytmusic, None, mock_matcher, mock_cache, mock_limiter)


def test_migrator_initialization_none_matcher(mock_ytmusic, mock_searcher, mock_cache, mock_limiter):
    """Test initialization rejects None track_matcher."""
    with pytest.raises(ValueError, match="track_matcher cannot be None"):
        PlaylistMigrator(mock_ytmusic, mock_searcher, None, mock_cache, mock_limiter)


def test_migrator_initialization_none_cache(mock_ytmusic, mock_searcher, mock_matcher, mock_limiter):
    """Test initialization rejects None cache_manager."""
    with pytest.raises(ValueError, match="cache_manager cannot be None"):
        PlaylistMigrator(mock_ytmusic, mock_searcher, mock_matcher, None, mock_limiter)


def test_migrator_initialization_none_limiter(mock_ytmusic, mock_searcher, mock_matcher, mock_cache):
    """Test initialization rejects None rate_limiter."""
    with pytest.raises(ValueError, match="rate_limiter cannot be None"):
        PlaylistMigrator(mock_ytmusic, mock_searcher, mock_matcher, mock_cache, None)


# ============================================================================
# migrate_playlist() Tests - Basic Functionality
# ============================================================================

@patch('src.migrators.playlist_migrator.time.sleep')
def test_migrate_playlist_basic(mock_sleep, migrator, mock_ytmusic, mock_searcher, mock_matcher, mock_cache, sample_tracks):
    """Test basic playlist migration."""
    # Setup mocks
    mock_searcher.search_track.return_value = [
        {'videoId': 'video1', 'title': 'Track 1', 'artists': []}
    ]
    mock_matcher.match_track.return_value = ('video1', 95.0)
    
    # Execute migration
    report = migrator.migrate_playlist("My Playlist", sample_tracks)
    
    # Verify playlist was created
    mock_ytmusic.create_playlist.assert_called_once_with(
        title="My Playlist",
        description="Migrated from Spotify by spotify-yt-migrate"
    )
    
    # Verify tracks were searched
    assert mock_searcher.search_track.call_count == 2
    
    # Verify tracks were added
    mock_ytmusic.add_playlist_items.assert_called_once()
    
    # Verify report
    assert report['playlist_name'] == "My Playlist"
    assert report['total_tracks'] == 2
    assert report['matched_tracks'] == 2
    assert report['success_rate'] == 100.0
    assert len(report['failed_tracks']) == 0
    assert len(report['match_scores']) == 2
    assert 'playlist_url' in report
    assert 'duration_seconds' in report


@patch('src.migrators.playlist_migrator.time.sleep')
def test_migrate_playlist_with_progress_callback(mock_sleep, migrator, mock_searcher, mock_matcher, sample_tracks):
    """Test migration with progress callback."""
    mock_searcher.search_track.return_value = [{'videoId': 'v1', 'title': 'T', 'artists': []}]
    mock_matcher.match_track.return_value = ('v1', 90.0)
    
    progress_calls = []
    
    def progress_callback(current, total, track_name):
        progress_calls.append((current, total, track_name))
    
    report = migrator.migrate_playlist("Test", sample_tracks, progress_callback)
    
    # Verify progress was reported
    assert len(progress_calls) == 2
    assert progress_calls[0] == (1, 2, 'Blinding Lights')
    assert progress_calls[1] == (2, 2, 'Shape of You')


def test_migrate_playlist_empty_name(migrator, sample_tracks):
    """Test migration rejects empty playlist name."""
    with pytest.raises(ValueError, match="playlist_name cannot be empty"):
        migrator.migrate_playlist("", sample_tracks)


def test_migrate_playlist_empty_tracks(migrator):
    """Test migration rejects empty tracks list."""
    with pytest.raises(ValueError, match="tracks list cannot be empty"):
        migrator.migrate_playlist("Test", [])


# ============================================================================
# migrate_playlist() Tests - Cache Handling
# ============================================================================

@patch('src.migrators.playlist_migrator.time.sleep')
def test_migrate_playlist_cache_hit(mock_sleep, migrator, mock_ytmusic, mock_searcher, mock_cache, sample_tracks):
    """Test migration uses cached matches."""
    # Setup cache to return matches
    # CacheManager stores confidence as a 0.0-1.0 decimal, not a percentage
    mock_cache.get_cached_match.return_value = {
        'youtube_video_id': 'cached_video',
        'confidence': 0.98
    }
    
    report = migrator.migrate_playlist("Test", sample_tracks)
    
    # Verify cache was checked
    assert mock_cache.get_cached_match.call_count == 2
    
    # Verify search was NOT called (cache hit)
    mock_searcher.search_track.assert_not_called()
    
    # Verify cached videos were used
    assert report['matched_tracks'] == 2
    assert all(score == 98.0 for score in report['match_scores'])


@patch('src.migrators.playlist_migrator.time.sleep')
def test_migrate_playlist_cache_miss_then_cache(mock_sleep, migrator, mock_cache, mock_searcher, mock_matcher, sample_tracks):
    """Test migration caches new matches."""
    mock_cache.get_cached_match.return_value = None  # Cache miss
    mock_searcher.search_track.return_value = [{'videoId': 'v1', 'title': 'T', 'artists': []}]
    mock_matcher.match_track.return_value = ('v1', 92.0)
    
    migrator.migrate_playlist("Test", sample_tracks)
    
    # Verify matches were cached
    assert mock_cache.cache_match.call_count == 2
    mock_cache.cache_match.assert_any_call(
        spotify_id='track1',
        youtube_id='v1',
        confidence=0.92  # Confidence is converted from percentage to decimal
    )


# ============================================================================
# migrate_playlist() Tests - ISRC Handling
# ============================================================================

@patch('src.migrators.playlist_migrator.time.sleep')
def test_migrate_playlist_isrc_search(mock_sleep, migrator, mock_searcher, mock_matcher):
    """A track carrying an ISRC still goes through title search only.

    YouTube Music has no isrc: operator, so the ISRC lookup was removed. See
    test_migration_does_not_issue_isrc_searches for the rationale.
    """
    tracks = [{
        'name': 'Test',
        'artists': ['Artist'],
        'album': 'Album',
        'duration_ms': 200000,
        'id': 'track1',
        'isrc': 'USRC17607839'
    }]
    
    mock_searcher.search_by_isrc.return_value = {
        'videoId': 'isrc_match',
        'title': 'Test',
        'artists': []
    }
    mock_matcher.match_track.return_value = ('isrc_match', 99.0)
    
    report = migrator.migrate_playlist("Test", tracks)
    
    # ISRC search is no longer issued; the title search carries the match
    mock_searcher.search_by_isrc.assert_not_called()
    mock_searcher.search_track.assert_called_once()
    assert report['matched_tracks'] == 1


@patch('src.migrators.playlist_migrator.time.sleep')
def test_migrate_playlist_isrc_fallback_to_fuzzy(mock_sleep, migrator, mock_searcher, mock_matcher):
    """Test migration falls back to fuzzy search if ISRC fails."""
    tracks = [{
        'name': 'Test',
        'artists': ['Artist'],
        'album': 'Album',
        'duration_ms': 200000,
        'id': 'track1',
        'isrc': 'INVALIDISRC'
    }]
    
    mock_searcher.search_by_isrc.return_value = None  # ISRC failed
    mock_searcher.search_track.return_value = [{'videoId': 'fuzzy', 'title': 'T', 'artists': []}]
    mock_matcher.match_track.return_value = ('fuzzy', 85.0)
    
    report = migrator.migrate_playlist("Test", tracks)
    
    # Verify ISRC was tried first
    mock_searcher.search_by_isrc.assert_not_called()
    
    # Verify fuzzy search was used as fallback
    mock_searcher.search_track.assert_called_once()
    
    assert report['matched_tracks'] == 1


# ============================================================================
# migrate_playlist() Tests - Failed Matches
# ============================================================================

@patch('src.migrators.playlist_migrator.time.sleep')
def test_migrate_playlist_no_youtube_results(mock_sleep, migrator, mock_searcher, sample_tracks):
    """Test migration handles tracks with no YouTube results."""
    mock_searcher.search_track.return_value = []  # No results
    
    report = migrator.migrate_playlist("Test", sample_tracks)
    
    # Verify failed tracks
    assert report['matched_tracks'] == 0
    assert len(report['failed_tracks']) == 2
    assert report['failed_tracks'][0]['reason'] == 'No match found above threshold'
    assert report['success_rate'] == 0.0


@patch('src.migrators.playlist_migrator.time.sleep')
def test_migrate_playlist_match_below_threshold(mock_sleep, migrator, mock_searcher, mock_matcher, sample_tracks):
    """Test migration handles matches below threshold."""
    mock_searcher.search_track.return_value = [{'videoId': 'v1', 'title': 'T', 'artists': []}]
    mock_matcher.match_track.return_value = (None, 0.0)  # Below threshold
    
    report = migrator.migrate_playlist("Test", sample_tracks)
    
    assert report['matched_tracks'] == 0
    assert len(report['failed_tracks']) == 2


@patch('src.migrators.playlist_migrator.time.sleep')
def test_migrate_playlist_track_processing_error(mock_sleep, migrator, mock_searcher, sample_tracks):
    """Test migration handles track processing errors gracefully."""
    mock_searcher.search_track.side_effect = Exception("Network error")
    
    report = migrator.migrate_playlist("Test", sample_tracks)
    
    # Should not crash, should report failures
    assert report['matched_tracks'] == 0
    assert len(report['failed_tracks']) == 2
    assert 'Error:' in report['failed_tracks'][0]['reason']


# ============================================================================
# migrate_playlist() Tests - Partial Success
# ============================================================================

@patch('src.migrators.playlist_migrator.time.sleep')
def test_migrate_playlist_partial_success(mock_sleep, migrator, mock_searcher, mock_matcher, sample_tracks):
    """Test migration with some successful and some failed matches."""
    # First track succeeds, second fails
    mock_searcher.search_track.side_effect = [
        [{'videoId': 'v1', 'title': 'T', 'artists': []}],  # Success
        []  # No results
    ]
    mock_matcher.match_track.return_value = ('v1', 88.0)
    
    report = migrator.migrate_playlist("Test", sample_tracks)
    
    assert report['matched_tracks'] == 1
    assert len(report['failed_tracks']) == 1
    assert report['success_rate'] == 50.0


# ============================================================================
# add_tracks_batch() Tests
# ============================================================================

@patch('src.migrators.playlist_migrator.time.sleep')
def test_add_tracks_batch_single_batch(mock_sleep, migrator, mock_ytmusic):
    """Test adding tracks in single batch (<100 tracks)."""
    video_ids = ['v1', 'v2', 'v3']
    
    migrator.add_tracks_batch('PL123', video_ids)
    
    # Should be added in one batch
    mock_ytmusic.add_playlist_items.assert_called_once_with(
        playlistId='PL123',
        videoIds=['v1', 'v2', 'v3']
    )


@patch('src.migrators.playlist_migrator.time.sleep')
def test_add_tracks_batch_multiple_batches(mock_sleep, migrator, mock_ytmusic):
    """Test adding tracks in multiple batches (>100 tracks)."""
    # Create 250 video IDs
    video_ids = [f'v{i}' for i in range(250)]
    
    migrator.add_tracks_batch('PL123', video_ids)
    
    # Should be split into 3 batches (100, 100, 50)
    assert mock_ytmusic.add_playlist_items.call_count == 3
    
    # Verify batch sizes
    calls = mock_ytmusic.add_playlist_items.call_args_list
    assert len(calls[0][1]['videoIds']) == 100
    assert len(calls[1][1]['videoIds']) == 100
    assert len(calls[2][1]['videoIds']) == 50


@patch('src.migrators.playlist_migrator.time.sleep')
def test_add_tracks_batch_delays_between_batches(mock_sleep, migrator, mock_ytmusic):
    """Test delays between batch additions."""
    video_ids = [f'v{i}' for i in range(250)]
    
    migrator.add_tracks_batch('PL123', video_ids)
    
    # Should have delays between batches (not after last batch)
    sleep_calls = [call_args[0][0] for call_args in mock_sleep.call_args_list]
    assert 0.5 in sleep_calls  # BATCH_DELAY


def test_add_tracks_batch_empty_playlist_id(migrator):
    """Test batch add rejects empty playlist ID."""
    with pytest.raises(ValueError, match="playlist_id cannot be empty"):
        migrator.add_tracks_batch("", ['v1'])


def test_add_tracks_batch_empty_video_ids(migrator):
    """Test batch add rejects empty video IDs list."""
    with pytest.raises(ValueError, match="video_ids list cannot be empty"):
        migrator.add_tracks_batch("PL123", [])


@patch('src.migrators.playlist_migrator.time.sleep')
def test_add_tracks_batch_429_retry(mock_sleep, migrator, mock_ytmusic, mock_limiter):
    """Test batch add retries on 429 error."""
    # First attempt fails with 429, second succeeds
    mock_ytmusic.add_playlist_items.side_effect = [
        YTMusicServerError("429 Too Many Requests"),
        None  # Success
    ]
    
    migrator.add_tracks_batch('PL123', ['v1', 'v2'])
    
    # Should have retried
    assert mock_ytmusic.add_playlist_items.call_count == 2
    
    # Should have called rate limiter
    mock_limiter.handle_429.assert_called_once()


@patch('src.migrators.playlist_migrator.time.sleep')
def test_add_tracks_batch_429_max_retries(mock_sleep, migrator, mock_ytmusic):
    """Test batch add stops after max retries on 429."""
    # All attempts fail with 429
    mock_ytmusic.add_playlist_items.side_effect = YTMusicServerError("429 Too Many Requests")
    
    # Should not raise, just log error
    migrator.add_tracks_batch('PL123', ['v1'])
    
    # Should retry 3 times
    assert mock_ytmusic.add_playlist_items.call_count == 3


@patch('src.migrators.playlist_migrator.time.sleep')
def test_add_tracks_batch_server_error_retry(mock_sleep, migrator, mock_ytmusic):
    """Test batch add retries on server error."""
    # First attempt fails, second succeeds
    mock_ytmusic.add_playlist_items.side_effect = [
        YTMusicServerError("500 Internal Server Error"),
        None
    ]
    
    migrator.add_tracks_batch('PL123', ['v1'])
    
    assert mock_ytmusic.add_playlist_items.call_count == 2


@patch('src.migrators.playlist_migrator.time.sleep')
def test_add_tracks_batch_unexpected_error_continues(mock_sleep, migrator, mock_ytmusic):
    """Test batch add continues to next batch on unexpected error."""
    # Create 2 batches worth of tracks
    video_ids = [f'v{i}' for i in range(150)]
    
    # First batch fails, second succeeds
    mock_ytmusic.add_playlist_items.side_effect = [
        ValueError("Unexpected error"),
        ValueError("Unexpected error"),
        ValueError("Unexpected error"),  # Max retries for first batch
        None  # Second batch succeeds
    ]
    
    migrator.add_tracks_batch('PL123', video_ids)
    
    # Should have attempted first batch 3 times, then second batch once
    assert mock_ytmusic.add_playlist_items.call_count == 4


# ============================================================================
# chunks() Tests
# ============================================================================

def test_chunks_basic():
    """Test chunks() utility function."""
    result = list(PlaylistMigrator.chunks([1, 2, 3, 4, 5], 2))
    assert result == [[1, 2], [3, 4], [5]]


def test_chunks_exact_division():
    """Test chunks() with exact division."""
    result = list(PlaylistMigrator.chunks([1, 2, 3, 4], 2))
    assert result == [[1, 2], [3, 4]]


def test_chunks_single_chunk():
    """Test chunks() when list smaller than chunk size."""
    result = list(PlaylistMigrator.chunks([1, 2, 3], 10))
    assert result == [[1, 2, 3]]


def test_chunks_empty_list():
    """Test chunks() with empty list."""
    result = list(PlaylistMigrator.chunks([], 5))
    assert result == []


# ============================================================================
# Integration Tests
# ============================================================================

@patch('src.migrators.playlist_migrator.time.sleep')
def test_full_migration_workflow(mock_sleep, migrator, mock_ytmusic, mock_searcher, mock_matcher, mock_cache):
    """Test complete end-to-end migration workflow."""
    tracks = [
        {
            'name': 'Track 1',
            'artists': ['Artist 1'],
            'album': 'Album 1',
            'duration_ms': 200000,
            'id': 'sp1',
            'isrc': 'ISRC1'
        },
        {
            'name': 'Track 2',
            'artists': ['Artist 2'],
            'album': 'Album 2',
            'duration_ms': 180000,
            'id': 'sp2'
            # No ISRC
        }
    ]
    
    # Setup mocks
    mock_ytmusic.create_playlist.return_value = 'PL_NEW'
    mock_cache.get_cached_match.return_value = None
    mock_searcher.search_by_isrc.return_value = {'videoId': 'isrc_v', 'title': 'T', 'artists': []}
    mock_searcher.search_track.return_value = [{'videoId': 'fuzzy_v', 'title': 'T', 'artists': []}]
    mock_matcher.match_track.side_effect = [('isrc_v', 98.0), ('fuzzy_v', 87.0)]
    
    # Execute migration
    report = migrator.migrate_playlist("Full Test", tracks)
    
    # Verify complete workflow
    assert report['playlist_name'] == "Full Test"
    assert report['total_tracks'] == 2
    assert report['matched_tracks'] == 2
    assert report['success_rate'] == 100.0
    assert 'PL_NEW' in report['playlist_url']
    
    # ISRC lookup is no longer issued for either track
    mock_searcher.search_by_isrc.assert_not_called()
    
    # Both tracks resolve through the title search
    assert mock_searcher.search_track.call_count == 2
    
    # Verify tracks were cached
    assert mock_cache.cache_match.call_count == 2
    
    # Verify tracks were added to playlist
    mock_ytmusic.add_playlist_items.assert_called_once()


def test_migration_does_not_issue_isrc_searches(migrator, mock_ytmusic, mock_searcher,
                                                mock_cache, sample_tracks):
    """YouTube Music has no isrc: search operator, so that lookup is dead weight.

    Measured against the live API: the isrc: query returned zero results for all
    12 tracks of a real playlist, while the title search matched 11. Issuing it
    doubled the request count and the wall-clock time per track.
    """
    mock_cache.get_cached_match.return_value = None
    mock_searcher.search_track.return_value = [
        {'videoId': 'v1', 'title': 'Song One', 'artists': [{'name': 'Artist A'}],
         'album': {'name': 'Album'}, 'duration_seconds': 200},
    ]

    migrator.migrate_playlist("No ISRC Please", sample_tracks)

    mock_searcher.search_by_isrc.assert_not_called()


# ============================================================================
# Incremental writes, sharding, resume (contract §4.3)
# ============================================================================

from config.app_config import YOUTUBE_PLAYLIST_MAX_ITEMS, INCREMENTAL_FLUSH_SIZE


def _make_tracks(n, prefix='t'):
    return [
        {'name': f'Song {i}', 'artists': [f'Artist {i}'], 'album': 'A',
         'duration_ms': 200000, 'id': f'{prefix}{i}'}
        for i in range(1, n + 1)
    ]


def test_constants_come_from_app_config(migrator):
    """The 5,000 cap and flush size are named constants, not magic numbers."""
    assert PlaylistMigrator.SHARD_SIZE == YOUTUBE_PLAYLIST_MAX_ITEMS == 5000
    assert PlaylistMigrator.FLUSH_SIZE == INCREMENTAL_FLUSH_SIZE
    assert 50 <= PlaylistMigrator.FLUSH_SIZE <= 100


@patch('src.migrators.playlist_migrator.time.sleep')
def test_incremental_flush_writes_before_search_completes(mock_sleep, migrator, mock_ytmusic,
                                                          mock_searcher, mock_matcher):
    """Matched tracks are written to YouTube while the search loop is still
    running - not after every track has been searched."""
    events = []
    
    def search(name, artists):
        events.append(('search', name))
        return [{'videoId': 'v_' + name, 'title': name, 'artists': []}]
    
    def add(playlistId, videoIds):
        events.append(('add', len(videoIds)))
    
    mock_searcher.search_track.side_effect = search
    mock_matcher.match_track.side_effect = lambda t, r: (r[0]['videoId'], 90.0)
    mock_ytmusic.add_playlist_items.side_effect = add
    
    n = PlaylistMigrator.FLUSH_SIZE * 2 + 7
    report = migrator.migrate_playlist("Big", _make_tracks(n))
    
    adds = [i for i, e in enumerate(events) if e[0] == 'add']
    searches = [i for i, e in enumerate(events) if e[0] == 'search']
    # Three writes: two full flushes mid-loop plus the remainder at the end
    assert [events[i][1] for i in adds] == [PlaylistMigrator.FLUSH_SIZE, PlaylistMigrator.FLUSH_SIZE, 7]
    # The first write happens before the last search
    assert adds[0] < searches[-1]
    # Exactly FLUSH_SIZE searches precede the first write
    assert sum(1 for i in searches if i < adds[0]) == PlaylistMigrator.FLUSH_SIZE
    assert report['matched_tracks'] == n
    assert report['shard_count'] == 1


@patch('src.migrators.playlist_migrator.time.sleep')
def test_state_callback_reports_durable_progress_after_each_flush(mock_sleep, migrator, mock_ytmusic,
                                                                 mock_searcher, mock_matcher):
    """After every write the caller learns the playlist id(s), how many items
    are on YouTube, and the index of the last source track that is final."""
    mock_ytmusic.create_playlist.return_value = 'PL_X'
    mock_searcher.search_track.return_value = [{'videoId': 'v', 'title': 'T', 'artists': []}]
    mock_matcher.match_track.return_value = ('v', 90.0)
    states = []
    
    n = PlaylistMigrator.FLUSH_SIZE + 3
    migrator.migrate_playlist("P", _make_tracks(n), state_callback=lambda **s: states.append(s))
    
    # First state: playlist created, nothing added yet (guards against duplicate
    # playlists if we crash right after create).
    assert states[0] == {'youtube_playlist_ids': ['PL_X'], 'added_tracks': 0,
                         'last_added_index': 0, 'matched_tracks': 0, 'failed_tracks': 0}
    # After the first flush
    assert states[1]['added_tracks'] == PlaylistMigrator.FLUSH_SIZE
    assert states[1]['last_added_index'] == PlaylistMigrator.FLUSH_SIZE
    # Final flush
    assert states[-1]['added_tracks'] == n
    assert states[-1]['last_added_index'] == n
    assert states[-1]['matched_tracks'] == n


@patch('src.migrators.playlist_migrator.time.sleep')
def test_unmatched_tracks_still_advance_last_added_index(mock_sleep, migrator, mock_ytmusic,
                                                         mock_searcher, mock_matcher):
    """A track with no match is final too; resume must not re-search it."""
    mock_searcher.search_track.return_value = []
    states = []
    
    report = migrator.migrate_playlist("P", _make_tracks(3), state_callback=lambda **s: states.append(s))
    
    assert report['matched_tracks'] == 0
    assert states[-1]['last_added_index'] == 3
    assert states[-1]['failed_tracks'] == 3
    assert states[-1]['added_tracks'] == 0
    mock_ytmusic.add_playlist_items.assert_not_called()


@patch('src.migrators.playlist_migrator.time.sleep')
def test_resume_skips_added_tracks_and_reuses_playlist(mock_sleep, migrator, mock_ytmusic,
                                                      mock_searcher, mock_matcher):
    """Given the state of an interrupted run, the migrator continues from the
    next track, writes into the existing playlist, and creates nothing new."""
    mock_searcher.search_track.side_effect = lambda name, a: [{'videoId': 'v_' + name, 'title': name, 'artists': []}]
    mock_matcher.match_track.side_effect = lambda t, r: (r[0]['videoId'], 90.0)
    tracks = _make_tracks(5)
    
    report = migrator.migrate_playlist(
        "P", tracks,
        resume_state={'youtube_playlist_ids': ['PL_EXISTING'], 'added_tracks': 3,
                      'last_added_index': 3, 'matched_tracks': 3, 'failed_tracks': 0}
    )
    
    mock_ytmusic.create_playlist.assert_not_called()
    searched = [c.args[0] for c in mock_searcher.search_track.call_args_list]
    assert searched == ['Song 4', 'Song 5']
    mock_ytmusic.add_playlist_items.assert_called_once_with(
        playlistId='PL_EXISTING', videoIds=['v_Song 4', 'v_Song 5'])
    assert report['resumed_from'] == 3
    assert report['matched_tracks'] == 5          # whole job
    assert report['total_tracks'] == 5
    assert report['success_rate'] == 100.0
    assert 'PL_EXISTING' in report['playlist_url']


@patch('src.migrators.playlist_migrator.time.sleep')
def test_resume_with_everything_already_added_does_nothing(mock_sleep, migrator, mock_ytmusic, mock_searcher):
    report = migrator.migrate_playlist(
        "P", _make_tracks(2),
        resume_state={'youtube_playlist_ids': ['PL_DONE'], 'added_tracks': 2,
                      'last_added_index': 2, 'matched_tracks': 2}
    )
    mock_searcher.search_track.assert_not_called()
    mock_ytmusic.create_playlist.assert_not_called()
    mock_ytmusic.add_playlist_items.assert_not_called()
    assert report['matched_tracks'] == 2


@patch('src.migrators.playlist_migrator.time.sleep')
def test_crash_then_resume_round_trip(mock_sleep, migrator, mock_ytmusic, mock_searcher, mock_matcher):
    """End to end: a run dies mid-search after one flush; feeding the last
    reported state into a second run finishes the job with one playlist and
    every matched track written exactly once."""
    class Crash(BaseException):
        """Simulates the process dying (not caught by per-track handlers)."""
    
    mock_ytmusic.create_playlist.return_value = 'PL_ONE'
    mock_matcher.match_track.side_effect = lambda t, r: (r[0]['videoId'], 90.0)
    tracks = _make_tracks(PlaylistMigrator.FLUSH_SIZE + 20)
    crash_at = PlaylistMigrator.FLUSH_SIZE + 10
    calls = {'n': 0}
    
    def search(name, artists):
        calls['n'] += 1
        if calls['n'] == crash_at:
            raise Crash()
        return [{'videoId': 'v_' + name, 'title': name, 'artists': []}]
    mock_searcher.search_track.side_effect = search
    
    states = []
    with pytest.raises(Crash):
        migrator.migrate_playlist("P", tracks, state_callback=lambda **s: states.append(s))
    
    # One flush made it to YouTube before the crash
    assert mock_ytmusic.add_playlist_items.call_count == 1
    last_state = states[-1]
    assert last_state['added_tracks'] == PlaylistMigrator.FLUSH_SIZE
    assert last_state['last_added_index'] == PlaylistMigrator.FLUSH_SIZE
    
    # Restart with the persisted state
    report = migrator.migrate_playlist("P", tracks, resume_state=last_state)
    
    assert mock_ytmusic.create_playlist.call_count == 1       # no duplicate playlist
    written = [vid for c in mock_ytmusic.add_playlist_items.call_args_list for vid in c.kwargs['videoIds']]
    assert len(written) == len(tracks)
    assert len(set(written)) == len(tracks)                   # nothing written twice
    assert report['matched_tracks'] == len(tracks)
    assert report['playlist_ids'] == ['PL_ONE']


@patch('src.migrators.playlist_migrator.time.sleep')
def test_shards_at_youtube_playlist_cap(mock_sleep, migrator, mock_ytmusic, mock_cache):
    """A source playlist with more than 5,000 matched tracks is written to
    several destination playlists, none holding more than 5,000 items."""
    n = YOUTUBE_PLAYLIST_MAX_ITEMS + 1
    # Cache hits keep the test fast and deterministic (no search)
    mock_cache.get_cached_match.side_effect = lambda sid: {'youtube_video_id': 'v_' + sid, 'confidence': 0.9}
    mock_ytmusic.create_playlist.side_effect = ['PL_1', 'PL_2']
    states = []
    
    report = migrator.migrate_playlist("Huge", _make_tracks(n), state_callback=lambda **s: states.append(s))
    
    # Two shards, numbered from the start so names are stable across a resume
    assert mock_ytmusic.create_playlist.call_args_list[0].kwargs['title'] == 'Huge (1)'
    assert mock_ytmusic.create_playlist.call_args_list[1].kwargs['title'] == 'Huge (2)'
    
    per_playlist = {}
    for c in mock_ytmusic.add_playlist_items.call_args_list:
        per_playlist[c.kwargs['playlistId']] = per_playlist.get(c.kwargs['playlistId'], 0) + len(c.kwargs['videoIds'])
    assert per_playlist == {'PL_1': YOUTUBE_PLAYLIST_MAX_ITEMS, 'PL_2': 1}
    
    assert report['shard_count'] == 2
    assert report['playlist_ids'] == ['PL_1', 'PL_2']
    assert len(report['playlist_urls']) == 2
    assert report['matched_tracks'] == n
    # Both shard ids are on the durable state for resume
    assert states[-1]['youtube_playlist_ids'] == ['PL_1', 'PL_2']
    assert states[-1]['added_tracks'] == n


@patch('src.migrators.playlist_migrator.time.sleep')
def test_small_playlist_keeps_its_own_name(mock_sleep, migrator, mock_ytmusic, mock_searcher, mock_matcher):
    mock_searcher.search_track.return_value = [{'videoId': 'v', 'title': 'T', 'artists': []}]
    mock_matcher.match_track.return_value = ('v', 90.0)
    migrator.migrate_playlist("Just Mine", _make_tracks(2))
    assert mock_ytmusic.create_playlist.call_args.kwargs['title'] == 'Just Mine'


@patch('src.migrators.playlist_migrator.time.sleep')
def test_resume_continues_into_second_shard(mock_sleep, migrator, mock_ytmusic, mock_cache):
    """Resuming a sharded job whose first shard is full creates only the
    missing shard and writes the remaining tracks there."""
    n = YOUTUBE_PLAYLIST_MAX_ITEMS + 2
    mock_cache.get_cached_match.side_effect = lambda sid: {'youtube_video_id': 'v_' + sid, 'confidence': 0.9}
    mock_ytmusic.create_playlist.return_value = 'PL_2'
    
    report = migrator.migrate_playlist(
        "Huge", _make_tracks(n),
        resume_state={'youtube_playlist_ids': ['PL_1'], 'added_tracks': YOUTUBE_PLAYLIST_MAX_ITEMS,
                      'last_added_index': YOUTUBE_PLAYLIST_MAX_ITEMS,
                      'matched_tracks': YOUTUBE_PLAYLIST_MAX_ITEMS}
    )
    
    mock_ytmusic.create_playlist.assert_called_once_with(
        title='Huge (2)', description="Migrated from Spotify by spotify-yt-migrate")
    mock_ytmusic.add_playlist_items.assert_called_once_with(
        playlistId='PL_2', videoIds=[f'v_t{n-1}', f'v_t{n}'])
    assert report['playlist_ids'] == ['PL_1', 'PL_2']
    assert report['matched_tracks'] == n


@patch('src.migrators.playlist_migrator.time.sleep')
def test_add_tracks_batch_returns_only_written_ids(mock_sleep, migrator, mock_ytmusic):
    """Callers need to know what actually landed to record durable progress."""
    video_ids = [f'v{i}' for i in range(150)]
    mock_ytmusic.add_playlist_items.side_effect = [
        ValueError("boom"), ValueError("boom"), ValueError("boom"),  # first batch exhausts retries
        None,                                                        # second batch succeeds
    ]
    added = migrator.add_tracks_batch('PL123', video_ids)
    assert added == video_ids[100:]


@patch('src.migrators.playlist_migrator.time.sleep')
def test_failed_write_is_reported_not_counted_as_matched(mock_sleep, migrator, mock_ytmusic,
                                                         mock_searcher, mock_matcher):
    mock_searcher.search_track.return_value = [{'videoId': 'v', 'title': 'T', 'artists': []}]
    mock_matcher.match_track.return_value = ('v', 90.0)
    mock_ytmusic.add_playlist_items.side_effect = ValueError("boom")
    
    report = migrator.migrate_playlist("P", _make_tracks(2))
    
    assert report['matched_tracks'] == 0
    assert len(report['failed_tracks']) == 2
    assert all('add to YouTube' in f['reason'] for f in report['failed_tracks'])
