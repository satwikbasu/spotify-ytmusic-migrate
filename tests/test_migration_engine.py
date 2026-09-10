"""Integration tests for the complete migration engine.

This module tests end-to-end scenarios with realistic Spotify and YouTube Music
data to verify the entire migration pipeline works correctly.
"""

import pytest
from unittest.mock import Mock, patch, call

from src.matchers.track_matcher import TrackMatcher
from src.searchers.youtube_searcher import YouTubeSearcher
from src.migrators.playlist_migrator import PlaylistMigrator
from src.utils.cache_manager import CacheManager
from src.utils.rate_limiter import RateLimiter


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_ytmusic():
    """Mock YTMusic client with realistic responses."""
    client = Mock()
    client.create_playlist.return_value = "PLrAXtmErZgOdP_8GztsuKi9kkflr2AuWI"
    client.add_playlist_items.return_value = None
    return client


@pytest.fixture
def real_rate_limiter():
    """Mock RateLimiter that always allows requests."""
    mock = Mock()
    mock.can_make_request = Mock(return_value=True)
    mock.record_request = Mock(return_value=None)
    return mock


@pytest.fixture
def real_cache_manager(tmp_path):
    """Real CacheManager instance with temporary database."""
    db_path = tmp_path / "test_cache.db"
    return CacheManager(str(db_path))


@pytest.fixture
def real_track_matcher():
    """Real TrackMatcher instance."""
    return TrackMatcher(threshold=75)


# ============================================================================
# Test 1: TrackMatcher Exact Match
# ============================================================================

def test_track_matcher_exact_match(real_track_matcher):
    """Test exact match: The Weeknd - Blinding Lights.
    
    Scenario: Perfect match with identical title, artist, album, and duration.
    Expected: Score >= 95% (near-perfect match).
    """
    # Spotify track data
    spotify_track = {
        'name': 'Blinding Lights',
        'artists': ['The Weeknd'],
        'album': 'After Hours',
        'duration_ms': 200040
    }
    
    # YouTube Music result (exact match)
    youtube_track = {
        'videoId': '4NRXx6U8ABQ',
        'title': 'Blinding Lights',
        'artists': [{'name': 'The Weeknd'}],
        'album': {'name': 'After Hours'},
        'duration_seconds': 200  # Exact match (200.04s ≈ 200s)
    }
    
    # Calculate similarity
    score = real_track_matcher.calculate_similarity(spotify_track, youtube_track)
    
    # Verify high confidence score
    assert score >= 95.0, f"Expected score >= 95, got {score}"
    
    # Should be near-perfect match with duration multiplier
    assert score >= 98.0, f"Exact match should score very high, got {score}"


# ============================================================================
# Test 2: TrackMatcher Partial Match
# ============================================================================

def test_track_matcher_partial_match(real_track_matcher):
    """Test partial match with extra text in YouTube title.
    
    Scenario: Eminem - Lose Yourself (Official Music Video)
    Expected: Score >= 75% despite extra text in title.
    """
    # Spotify track data
    spotify_track = {
        'name': 'Lose Yourself',
        'artists': ['Eminem'],
        'album': '8 Mile',
        'duration_ms': 326000
    }
    
    # YouTube Music result (with extra text)
    youtube_track = {
        'videoId': 'xFYQQPAOz7Y',
        'title': 'Eminem - Lose Yourself (Official Music Video)',
        'artists': [{'name': 'Eminem'}],
        'album': {'name': '8 Mile'},
        'duration_seconds': 326
    }
    
    # Calculate similarity
    score = real_track_matcher.calculate_similarity(spotify_track, youtube_track)
    
    # Verify good match despite extra text
    assert score >= 75.0, f"Expected score >= 75, got {score}"
    
    # Should be high confidence (title + artist + album + duration all match)
    assert score >= 85.0, f"Should score high despite noise words, got {score}"


# ============================================================================
# Test 3: TrackMatcher Duration Rejection
# ============================================================================

def test_track_matcher_duration_rejection(real_track_matcher):
    """Test auto-rejection for large duration difference.
    
    Scenario: Same title/artist but duration differs by 45 seconds (>30s threshold).
    Expected: Score = 0 (automatic rejection).
    """
    # Spotify track data
    spotify_track = {
        'name': 'Bohemian Rhapsody',
        'artists': ['Queen'],
        'album': 'A Night at the Opera',
        'duration_ms': 354000  # 5:54
    }
    
    # YouTube Music result (wrong version - live/extended)
    youtube_track = {
        'videoId': 'fJ9rUzIMcZQ',
        'title': 'Bohemian Rhapsody',
        'artists': [{'name': 'Queen'}],
        'album': {'name': 'A Night at the Opera'},
        'duration_seconds': 399  # 6:39 (45 seconds longer)
    }
    
    # Calculate similarity
    score = real_track_matcher.calculate_similarity(spotify_track, youtube_track)
    
    # Verify automatic rejection
    assert score == 0.0, f"Expected auto-rejection (score=0), got {score}"


# ============================================================================
# Test 4: YouTube Search with Real Data
# ============================================================================

@patch('src.searchers.youtube_searcher.time.sleep')
def test_youtube_search(mock_sleep, mock_ytmusic, real_rate_limiter):
    """Test YouTube Music search with query sanitization and rate limiting.
    
    Scenario: Search for "Shape of You" by Ed Sheeran.
    Expected: Query is sanitized, rate limiter is used, results are validated.
    """
    # Mock search results (realistic YouTube Music response)
    mock_ytmusic.search.return_value = [
        {
            'videoId': 'JGwWNGJdvx8',
            'title': 'Ed Sheeran - Shape of You [Official Video]',
            'artists': [{'name': 'Ed Sheeran'}],
            'album': {'name': '÷ (Divide)'},
            'duration': '3:53'
        },
        {
            'videoId': 'abc123',
            'title': 'Shape of You Cover',
            'artists': [{'name': 'Random Artist'}],
            'duration': '3:45'
        }
    ]
    
    # Create searcher
    searcher = YouTubeSearcher(mock_ytmusic, real_rate_limiter)
    
    # Perform search
    results = searcher.search_track("Shape of You", ["Ed Sheeran"])
    
    # Verify search was called
    assert mock_ytmusic.search.called
    
    # Verify query sanitization (should contain normalized artist + track)
    call_kwargs = mock_ytmusic.search.call_args[1]
    assert 'query' in call_kwargs
    query = call_kwargs['query'].lower()
    assert 'ed sheeran' in query
    assert 'shape of you' in query
    
    # Verify search filter
    assert call_kwargs['filter'] == 'songs'
    assert call_kwargs['limit'] == 5
    
    # Verify results are valid
    assert len(results) == 2
    assert results[0]['videoId'] == 'JGwWNGJdvx8'
    assert results[0]['duration_seconds'] == 233  # 3:53 = 233s
    
    # Verify conservative delay was applied
    mock_sleep.assert_called_with(1.0)


# ============================================================================
# Test 5: Complete Playlist Migration (100% Success)
# ============================================================================

@patch('src.searchers.youtube_searcher.time.sleep')
@patch('src.migrators.playlist_migrator.time.sleep')
def test_playlist_migration_success(
    mock_migrator_sleep,
    mock_searcher_sleep,
    mock_ytmusic,
    real_rate_limiter,
    real_track_matcher,
    real_cache_manager
):
    """Test complete playlist migration with 100% success rate.
    
    Scenario: Migrate 10 tracks, all match successfully.
    Expected: 
    - Report shows 100% success rate
    - All tracks added to playlist in batches
    - Progress callback called for each track
    """
    # Create realistic Spotify tracks
    spotify_tracks = [
        {
            'name': 'Blinding Lights',
            'artists': ['The Weeknd'],
            'album': 'After Hours',
            'duration_ms': 200040,
            'id': 'sp_track_1'
        },
        {
            'name': 'Shape of You',
            'artists': ['Ed Sheeran'],
            'album': '÷',
            'duration_ms': 233713,
            'id': 'sp_track_2'
        },
        {
            'name': 'Someone Like You',
            'artists': ['Adele'],
            'album': '21',
            'duration_ms': 285000,
            'id': 'sp_track_3'
        },
        {
            'name': 'Bohemian Rhapsody',
            'artists': ['Queen'],
            'album': 'A Night at the Opera',
            'duration_ms': 354000,
            'id': 'sp_track_4'
        },
        {
            'name': 'Hotel California',
            'artists': ['Eagles'],
            'album': 'Hotel California',
            'duration_ms': 391000,
            'id': 'sp_track_5'
        },
        {
            'name': 'Imagine',
            'artists': ['John Lennon'],
            'album': 'Imagine',
            'duration_ms': 183000,
            'id': 'sp_track_6'
        },
        {
            'name': 'Smells Like Teen Spirit',
            'artists': ['Nirvana'],
            'album': 'Nevermind',
            'duration_ms': 301000,
            'id': 'sp_track_7'
        },
        {
            'name': 'Billie Jean',
            'artists': ['Michael Jackson'],
            'album': 'Thriller',
            'duration_ms': 294000,
            'id': 'sp_track_8'
        },
        {
            'name': "Sweet Child O' Mine",
            'artists': ["Guns N' Roses"],
            'album': 'Appetite for Destruction',
            'duration_ms': 356000,
            'id': 'sp_track_9'
        },
        {
            'name': 'Stairway to Heaven',
            'artists': ['Led Zeppelin'],
            'album': 'Led Zeppelin IV',
            'duration_ms': 482000,
            'id': 'sp_track_10'
        }
    ]
    
    # Mock YouTube search results (all good matches)
    # Map track names to realistic YouTube results
    youtube_results = {
        'Blinding Lights': {
            'videoId': 'video_1',
            'title': 'Blinding Lights',
            'artists': [{'name': 'The Weeknd'}],
            'album': {'name': 'After Hours'},
            'duration_seconds': 200
        },
        'Shape of You': {
            'videoId': 'video_2',
            'title': 'Shape of You',
            'artists': [{'name': 'Ed Sheeran'}],
            'album': {'name': '÷'},
            'duration_seconds': 234
        },
        'Someone Like You': {
            'videoId': 'video_3',
            'title': 'Someone Like You',
            'artists': [{'name': 'Adele'}],
            'album': {'name': '21'},
            'duration_seconds': 285
        },
        'Bohemian Rhapsody': {
            'videoId': 'video_4',
            'title': 'Bohemian Rhapsody',
            'artists': [{'name': 'Queen'}],
            'album': {'name': 'A Night at the Opera'},
            'duration_seconds': 354
        },
        'Hotel California': {
            'videoId': 'video_5',
            'title': 'Hotel California',
            'artists': [{'name': 'Eagles'}],
            'album': {'name': 'Hotel California'},
            'duration_seconds': 391
        },
        'Imagine': {
            'videoId': 'video_6',
            'title': 'Imagine',
            'artists': [{'name': 'John Lennon'}],
            'album': {'name': 'Imagine'},
            'duration_seconds': 183
        },
        'Smells Like Teen Spirit': {
            'videoId': 'video_7',
            'title': 'Smells Like Teen Spirit',
            'artists': [{'name': 'Nirvana'}],
            'album': {'name': 'Nevermind'},
            'duration_seconds': 301
        },
        'Billie Jean': {
            'videoId': 'video_8',
            'title': 'Billie Jean',
            'artists': [{'name': 'Michael Jackson'}],
            'album': {'name': 'Thriller'},
            'duration_seconds': 294
        },
        "Sweet Child O' Mine": {
            'videoId': 'video_9',
            'title': "Sweet Child O' Mine",
            'artists': [{'name': "Guns N' Roses"}],
            'album': {'name': 'Appetite for Destruction'},
            'duration_seconds': 356
        },
        'Stairway to Heaven': {
            'videoId': 'video_10',
            'title': 'Stairway to Heaven',
            'artists': [{'name': 'Led Zeppelin'}],
            'album': {'name': 'Led Zeppelin IV'},
            'duration_seconds': 482
        }
    }
    
    def mock_search(query, filter, limit):
        # Find matching result based on query content
        query_lower = query.lower()
        for track_name, result in youtube_results.items():
            # Match if key words from track name appear in query
            track_lower = track_name.lower().replace("'", "")  # Normalize apostrophes
            # Extract key words (simplified matching)
            if 'blinding lights' in query_lower or (track_lower in query_lower):
                if 'blinding' in query_lower or 'shape of you' in query_lower or \
                   'someone like you' in query_lower or 'bohemian' in query_lower or \
                   'hotel california' in query_lower or 'imagine' in query_lower or \
                   'smells like' in query_lower or 'billie jean' in query_lower or \
                   'sweet child' in query_lower or 'stairway' in query_lower:
                    # Find the matching result
                    if ('blinding' in query_lower and 'blinding lights' in track_lower) or \
                       ('shape of you' in query_lower and 'shape of you' in track_lower) or \
                       ('someone like you' in query_lower and 'someone like you' in track_lower) or \
                       ('bohemian' in query_lower and 'bohemian' in track_lower) or \
                       ('hotel california' in query_lower and 'hotel california' in track_lower) or \
                       ('imagine' in query_lower and 'imagine' in track_lower and 'john' in query_lower) or \
                       ('smells like' in query_lower and 'smells like' in track_lower) or \
                       ('billie jean' in query_lower and 'billie jean' in track_lower) or \
                       ('sweet child' in query_lower and 'sweet child' in track_lower) or \
                       ('stairway' in query_lower and 'stairway' in track_lower):
                        return [result]
        # Fallback to generic result
        return [{
            'videoId': 'fallback_video',
            'title': query,
            'artists': [{'name': 'Unknown'}],
            'duration_seconds': 200
        }]

    mock_ytmusic.search.side_effect = mock_search
    
    # Create components
    searcher = YouTubeSearcher(mock_ytmusic, real_rate_limiter)
    migrator = PlaylistMigrator(
        mock_ytmusic,
        searcher,
        real_track_matcher,
        real_cache_manager,
        real_rate_limiter
    )
    
    # Track progress callbacks
    progress_calls = []
    
    def progress_callback(current, total, track_name):
        progress_calls.append((current, total, track_name))
    
    # Execute migration
    report = migrator.migrate_playlist(
        "Ultimate Hits",
        spotify_tracks,
        progress_callback
    )
    
    # Verify report structure
    assert 'playlist_name' in report
    assert 'playlist_url' in report
    assert 'total_tracks' in report
    assert 'matched_tracks' in report
    assert 'failed_tracks' in report
    assert 'success_rate' in report
    assert 'match_scores' in report
    assert 'duration_seconds' in report
    
    # Verify successful migration
    assert report['playlist_name'] == "Ultimate Hits"
    assert report['total_tracks'] == 10
    assert report['matched_tracks'] == 10
    assert report['success_rate'] == 100.0
    assert len(report['failed_tracks']) == 0
    assert len(report['match_scores']) == 10
    
    # Verify playlist URL format
    assert 'music.youtube.com/playlist?list=' in report['playlist_url']
    
    # Verify progress callback was called for each track
    assert len(progress_calls) == 10
    assert progress_calls[0] == (1, 10, 'Blinding Lights')
    assert progress_calls[9] == (10, 10, 'Stairway to Heaven')
    
    # Verify playlist was created
    mock_ytmusic.create_playlist.assert_called_once()
    
    # Verify tracks were added (single batch since <100 tracks)
    mock_ytmusic.add_playlist_items.assert_called_once()
    call_args = mock_ytmusic.add_playlist_items.call_args[1]
    assert len(call_args['videoIds']) == 10
    
    # Verify all video IDs are present
    video_ids = call_args['videoIds']
    assert all(vid.startswith('video_') for vid in video_ids)


# ============================================================================
# Test 6: Playlist Migration with Partial Failure
# ============================================================================

@patch('src.searchers.youtube_searcher.time.sleep')
@patch('src.migrators.playlist_migrator.time.sleep')
def test_playlist_migration_partial_failure(
    mock_migrator_sleep,
    mock_searcher_sleep,
    mock_ytmusic,
    real_rate_limiter,
    real_track_matcher,
    real_cache_manager
):
    """Test playlist migration with some failed matches.
    
    Scenario: Migrate 10 tracks, 2 fail to match (80% success).
    Expected:
    - Report shows 80% success rate
    - failed_tracks list contains 2 items with reasons
    - 8 tracks added to playlist
    """
    # Create 10 tracks
    spotify_tracks = [
        {
            'name': f'Track {i}',
            'artists': [f'Artist {i}'],
            'album': f'Album {i}',
            'duration_ms': 200000,
            'id': f'sp_track_{i}'
        }
        for i in range(1, 11)
    ]
    
    # Mock search results: tracks 3 and 7 fail (no results)
    call_count = [0]
    
    def mock_search(query, filter, limit):
        call_count[0] += 1
        if call_count[0] in [3, 7]:
            # No results for tracks 3 and 7
            return []
        else:
            # Good match for others
            return [{
                'videoId': f'video_{call_count[0]}',
                'title': query,
                'artists': [{'name': 'Artist'}],
                'duration_seconds': 200
            }]
    
    mock_ytmusic.search.side_effect = mock_search
    
    # Create components
    searcher = YouTubeSearcher(mock_ytmusic, real_rate_limiter)
    migrator = PlaylistMigrator(
        mock_ytmusic,
        searcher,
        real_track_matcher,
        real_cache_manager,
        real_rate_limiter
    )
    
    # Execute migration
    report = migrator.migrate_playlist("Test Playlist", spotify_tracks)
    
    # Verify partial success
    assert report['total_tracks'] == 10
    assert report['matched_tracks'] == 8
    assert report['success_rate'] == 80.0
    
    # Verify failed tracks
    assert len(report['failed_tracks']) == 2
    assert report['failed_tracks'][0]['spotify_track']['name'] == 'Track 3'
    assert report['failed_tracks'][1]['spotify_track']['name'] == 'Track 7'
    assert 'reason' in report['failed_tracks'][0]
    
    # Verify only matched tracks were added
    mock_ytmusic.add_playlist_items.assert_called_once()
    call_args = mock_ytmusic.add_playlist_items.call_args[1]
    assert len(call_args['videoIds']) == 8


# ============================================================================
# Test 7: Cache Usage Optimization
# ============================================================================

@patch('src.searchers.youtube_searcher.time.sleep')
@patch('src.migrators.playlist_migrator.time.sleep')
def test_cache_usage(
    mock_migrator_sleep,
    mock_searcher_sleep,
    mock_ytmusic,
    real_rate_limiter,
    real_track_matcher,
    real_cache_manager
):
    """Test that cache is used to avoid redundant searches.
    
    Scenario: Pre-cache 5 matches, then migrate 10 tracks (5 cached + 5 new).
    Expected:
    - YouTube search called only 5 times (not 10)
    - All 10 tracks successfully migrated
    - Cache hit rate = 50%
    """
    # Create 10 tracks
    spotify_tracks = [
        {
            'name': f'Track {i}',
            'artists': [f'Artist {i}'],
            'album': f'Album {i}',
            'duration_ms': 200000,
            'id': f'sp_track_{i}'
        }
        for i in range(1, 11)
    ]
    
    # Pre-populate cache for tracks 1-5
    for i in range(1, 6):
        real_cache_manager.cache_match(
            spotify_id=f'sp_track_{i}',
            youtube_id=f'cached_video_{i}',
            confidence=0.95
        )
    
    # Mock search results for tracks 6-10 (not cached)
    def mock_search(query, filter, limit):
        return [{
            'videoId': f'new_video_{len(mock_ytmusic.search.mock_calls)}',
            'title': query,
            'artists': [{'name': 'Artist'}],
            'duration_seconds': 200
        }]
    
    mock_ytmusic.search.side_effect = mock_search
    
    # Create components
    searcher = YouTubeSearcher(mock_ytmusic, real_rate_limiter)
    migrator = PlaylistMigrator(
        mock_ytmusic,
        searcher,
        real_track_matcher,
        real_cache_manager,
        real_rate_limiter
    )
    
    # Execute migration
    report = migrator.migrate_playlist("Cached Test", spotify_tracks)
    
    # Verify all tracks matched
    assert report['matched_tracks'] == 10
    assert report['success_rate'] == 100.0
    
    # Verify search was only called 5 times (for non-cached tracks)
    assert mock_ytmusic.search.call_count == 5
    
    # Verify cached videos were used
    call_args = mock_ytmusic.add_playlist_items.call_args[1]
    video_ids = call_args['videoIds']
    
    # First 5 should be cached videos
    assert video_ids[0] == 'cached_video_1'
    assert video_ids[1] == 'cached_video_2'
    assert video_ids[2] == 'cached_video_3'
    assert video_ids[3] == 'cached_video_4'
    assert video_ids[4] == 'cached_video_5'
    
    # Last 5 should be new videos
    assert all(vid.startswith('new_video_') for vid in video_ids[5:])


# ============================================================================
# Test 8: Batch Addition with Multiple Batches
# ============================================================================

@patch('src.migrators.playlist_migrator.time.sleep')
def test_batch_addition_multiple_batches(mock_sleep, mock_ytmusic, real_rate_limiter):
    """Test that large playlists are added in batches of 100.
    
    Scenario: Migrate playlist with 250 tracks.
    Expected:
    - Tracks added in 3 batches (100, 100, 50)
    - Delays between batches
    - Rate limiter checked for each batch
    """
    # Create migrator
    migrator = PlaylistMigrator(
        mock_ytmusic,
        Mock(),  # searcher (not used in this test)
        Mock(),  # matcher (not used)
        Mock(),  # cache (not used)
        real_rate_limiter
    )
    
    # Create 250 video IDs
    video_ids = [f'video_{i}' for i in range(250)]
    
    # Add tracks in batches
    migrator.add_tracks_batch('PL123', video_ids)
    
    # Verify 3 batch additions
    assert mock_ytmusic.add_playlist_items.call_count == 3
    
    # Verify batch sizes
    calls = mock_ytmusic.add_playlist_items.call_args_list
    assert len(calls[0][1]['videoIds']) == 100
    assert len(calls[1][1]['videoIds']) == 100
    assert len(calls[2][1]['videoIds']) == 50
    
    # Verify delays between batches (0.5s each, not after last batch)
    sleep_calls = [call_args[0][0] for call_args in mock_sleep.call_args_list]
    assert sleep_calls.count(0.5) >= 2


# ============================================================================
# Test 9: Real-World Track Matching Scenarios
# ============================================================================

def test_track_matcher_featured_artist(real_track_matcher):
    """Test matching tracks with featured artists.
    
    Scenario: Dua Lipa - Levitating (feat. DaBaby)
    Expected: Matches correctly with featured artist extraction.
    """
    spotify_track = {
        'name': 'Levitating (feat. DaBaby)',
        'artists': ['Dua Lipa'],
        'album': 'Future Nostalgia',
        'duration_ms': 203064
    }
    
    youtube_track = {
        'videoId': 'TUVcZfQe-Kw',
        'title': 'Dua Lipa - Levitating feat. DaBaby',
        'artists': [{'name': 'Dua Lipa'}, {'name': 'DaBaby'}],
        'album': {'name': 'Future Nostalgia'},
        'duration_seconds': 203
    }
    
    score = real_track_matcher.calculate_similarity(spotify_track, youtube_track)
    
    # Should match well despite different featuring format
    assert score >= 85.0, f"Expected high match for featured artist, got {score}"


def test_track_matcher_accent_normalization(real_track_matcher):
    """Test matching with accented characters.
    
    Scenario: José González - Heartbeats
    Expected: Matches despite accent differences.
    """
    spotify_track = {
        'name': 'Heartbeats',
        'artists': ['José González'],
        'album': 'Veneer',
        'duration_ms': 177000
    }
    
    youtube_track = {
        'videoId': 's4_4abCWw-w',
        'title': 'Jose Gonzalez - Heartbeats',  # No accents
        'artists': [{'name': 'José González'}],
        'album': {'name': 'Veneer'},
        'duration_seconds': 177
    }
    
    score = real_track_matcher.calculate_similarity(spotify_track, youtube_track)
    
    # Should match well despite accent differences
    assert score >= 90.0, f"Expected high match with accent normalization, got {score}"
