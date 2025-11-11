"""Unit tests for TrackMatcher class.

This module tests the fuzzy matching algorithm used to match Spotify tracks
to YouTube Music tracks, including scoring calculations, thresholds, and
normalization.
"""

import pytest

from src.matchers.track_matcher import TrackMatcher


# ============================================================================
# TrackMatcher Initialization Tests
# ============================================================================

def test_matcher_initialization_default():
    """Test TrackMatcher with default threshold."""
    matcher = TrackMatcher()
    assert matcher.threshold == 75


def test_matcher_initialization_custom():
    """Test TrackMatcher with custom threshold."""
    matcher = TrackMatcher(threshold=80)
    assert matcher.threshold == 80


def test_matcher_initialization_invalid_threshold():
    """Test TrackMatcher rejects invalid thresholds."""
    with pytest.raises(ValueError, match="Threshold must be between 0 and 100"):
        TrackMatcher(threshold=150)
    
    with pytest.raises(ValueError, match="Threshold must be between 0 and 100"):
        TrackMatcher(threshold=-10)


# ============================================================================
# normalize_track_data() Tests
# ============================================================================

def test_normalize_spotify_track_basic():
    """Test normalization of basic Spotify track."""
    matcher = TrackMatcher()
    spotify_track = {
        'name': 'Blinding Lights',
        'artists': ['The Weeknd'],
        'album': 'After Hours',
        'duration_ms': 200040
    }
    
    normalized = matcher.normalize_track_data(spotify_track, 'spotify')
    
    assert normalized['title'] == 'blinding lights'
    assert normalized['artists'] == ['the weeknd']
    assert normalized['album'] == 'after hours'
    assert normalized['duration_ms'] == 200040


def test_normalize_spotify_track_with_accents():
    """Test normalization removes accents from Spotify track."""
    matcher = TrackMatcher()
    spotify_track = {
        'name': 'Café Society',
        'artists': ['José González'],
        'album': 'Veneer',
        'duration_ms': 240000
    }
    
    normalized = matcher.normalize_track_data(spotify_track, 'spotify')
    
    assert normalized['title'] == 'cafe society'
    assert normalized['artists'] == ['jose gonzalez']
    assert normalized['album'] == 'veneer'


def test_normalize_spotify_track_with_featured_artists():
    """Test extraction of featured artists from Spotify track name."""
    matcher = TrackMatcher()
    spotify_track = {
        'name': 'Levitating (feat. DaBaby)',
        'artists': ['Dua Lipa'],
        'album': 'Future Nostalgia',
        'duration_ms': 203064
    }
    
    normalized = matcher.normalize_track_data(spotify_track, 'spotify')
    
    assert normalized['title'] == 'levitating'
    assert 'dua lipa' in normalized['artists']
    assert 'dababy' in normalized['artists']


def test_normalize_spotify_track_multiple_artists():
    """Test normalization of Spotify track with multiple artists."""
    matcher = TrackMatcher()
    spotify_track = {
        'name': 'Shallow',
        'artists': ['Lady Gaga', 'Bradley Cooper'],
        'album': 'A Star Is Born',
        'duration_ms': 215733
    }
    
    normalized = matcher.normalize_track_data(spotify_track, 'spotify')
    
    assert normalized['title'] == 'shallow'
    assert 'lady gaga' in normalized['artists']
    assert 'bradley cooper' in normalized['artists']


def test_normalize_youtube_track_basic():
    """Test normalization of basic YouTube Music track."""
    matcher = TrackMatcher()
    youtube_track = {
        'videoId': 'abc123',
        'title': 'The Weeknd - Blinding Lights',
        'artists': [{'name': 'The Weeknd'}],
        'album': {'name': 'After Hours'},
        'duration_seconds': 200
    }
    
    normalized = matcher.normalize_track_data(youtube_track, 'youtube')
    
    assert normalized['title'] == 'the weeknd blinding lights'
    assert normalized['artists'] == ['the weeknd']
    assert normalized['album'] == 'after hours'
    assert normalized['duration_seconds'] == 200
    assert normalized['duration_ms'] == 200000


def test_normalize_youtube_track_no_album():
    """Test normalization of YouTube track without album."""
    matcher = TrackMatcher()
    youtube_track = {
        'videoId': 'xyz789',
        'title': 'Random Song',
        'artists': [{'name': 'Artist Name'}],
        'duration_seconds': 180
    }
    
    normalized = matcher.normalize_track_data(youtube_track, 'youtube')
    
    assert normalized['title'] == 'random song'
    assert normalized['album'] == ''


def test_normalize_youtube_track_multiple_artists():
    """Test normalization of YouTube track with multiple artists."""
    matcher = TrackMatcher()
    youtube_track = {
        'videoId': 'multi123',
        'title': 'Collaboration Song',
        'artists': [
            {'name': 'Artist One'},
            {'name': 'Artist Two'}
        ],
        'duration_seconds': 210
    }
    
    normalized = matcher.normalize_track_data(youtube_track, 'youtube')
    
    assert 'artist one' in normalized['artists']
    assert 'artist two' in normalized['artists']


def test_normalize_invalid_source():
    """Test normalization rejects invalid source."""
    matcher = TrackMatcher()
    track = {'name': 'Test', 'artists': ['Artist']}
    
    with pytest.raises(ValueError, match="Source must be 'spotify' or 'youtube'"):
        matcher.normalize_track_data(track, 'invalid')


# ============================================================================
# calculate_similarity() Tests - Perfect Matches
# ============================================================================

def test_similarity_perfect_match():
    """Test similarity calculation for perfect match."""
    matcher = TrackMatcher()
    
    spotify_track = {
        'name': 'Blinding Lights',
        'artists': ['The Weeknd'],
        'album': 'After Hours',
        'duration_ms': 200000
    }
    
    youtube_track = {
        'videoId': 'abc123',
        'title': 'Blinding Lights',
        'artists': [{'name': 'The Weeknd'}],
        'album': {'name': 'After Hours'},
        'duration_seconds': 200
    }
    
    score = matcher.calculate_similarity(spotify_track, youtube_track)
    
    # Should be very high (near 100 with duration multiplier)
    assert score >= 95


def test_similarity_exact_duration_match():
    """Test duration multiplier for near-perfect duration match."""
    matcher = TrackMatcher()
    
    spotify_track = {
        'name': 'Test Song',
        'artists': ['Artist'],
        'album': 'Album',
        'duration_ms': 200000  # Exactly 200 seconds
    }
    
    youtube_track = {
        'videoId': 'test123',
        'title': 'Test Song',
        'artists': [{'name': 'Artist'}],
        'album': {'name': 'Album'},
        'duration_seconds': 200  # Exactly 200 seconds
    }
    
    score = matcher.calculate_similarity(spotify_track, youtube_track)
    
    # Perfect match with 1.3x multiplier should hit 100 (capped)
    assert score == 100.0


def test_similarity_good_duration_match():
    """Test duration multiplier for good duration match (3s diff)."""
    matcher = TrackMatcher()
    
    spotify_track = {
        'name': 'Test Song',
        'artists': ['Artist'],
        'album': 'Album',
        'duration_ms': 200000
    }
    
    youtube_track = {
        'videoId': 'test123',
        'title': 'Test Song',
        'artists': [{'name': 'Artist'}],
        'album': {'name': 'Album'},
        'duration_seconds': 203  # 3 second difference
    }
    
    score = matcher.calculate_similarity(spotify_track, youtube_track)
    
    # Should apply 1.15x multiplier for <= 5s diff
    assert score >= 90


# ============================================================================
# calculate_similarity() Tests - Duration Validation
# ============================================================================

def test_similarity_duration_auto_reject():
    """Test auto-rejection for large duration difference."""
    matcher = TrackMatcher()
    
    spotify_track = {
        'name': 'Short Song',
        'artists': ['Artist'],
        'album': 'Album',
        'duration_ms': 180000  # 3 minutes
    }
    
    youtube_track = {
        'videoId': 'long123',
        'title': 'Short Song',
        'artists': [{'name': 'Artist'}],
        'album': {'name': 'Album'},
        'duration_seconds': 600  # 10 minutes (7 min diff > 30s threshold)
    }
    
    score = matcher.calculate_similarity(spotify_track, youtube_track)
    
    # Should auto-reject (return 0)
    assert score == 0.0


def test_similarity_acceptable_duration():
    """Test acceptable duration match (8s diff)."""
    matcher = TrackMatcher()
    
    spotify_track = {
        'name': 'Test Song',
        'artists': ['Artist'],
        'album': 'Album',
        'duration_ms': 200000
    }
    
    youtube_track = {
        'videoId': 'test123',
        'title': 'Test Song',
        'artists': [{'name': 'Artist'}],
        'duration_seconds': 208  # 8 second difference
    }
    
    score = matcher.calculate_similarity(spotify_track, youtube_track)
    
    # Should apply 1.05x multiplier for <= 10s diff
    assert 85 <= score <= 100


def test_similarity_no_duration():
    """Test similarity when YouTube track has no duration."""
    matcher = TrackMatcher()
    
    spotify_track = {
        'name': 'Test Song',
        'artists': ['Artist'],
        'album': 'Album',
        'duration_ms': 200000
    }
    
    youtube_track = {
        'videoId': 'test123',
        'title': 'Test Song',
        'artists': [{'name': 'Artist'}],
        'album': {'name': 'Album'}
        # No duration_seconds
    }
    
    score = matcher.calculate_similarity(spotify_track, youtube_track)
    
    # Should still calculate score without duration bonus
    assert score > 0


# ============================================================================
# calculate_similarity() Tests - Fuzzy Matching
# ============================================================================

def test_similarity_word_order_difference():
    """Test token_sort_ratio handles different word order."""
    matcher = TrackMatcher()
    
    spotify_track = {
        'name': 'Someone Like You',
        'artists': ['Adele'],
        'album': '21',
        'duration_ms': 285000
    }
    
    youtube_track = {
        'videoId': 'adele123',
        'title': 'Adele - Like You Someone',  # Different word order
        'artists': [{'name': 'Adele'}],
        'duration_seconds': 285
    }
    
    score = matcher.calculate_similarity(spotify_track, youtube_track)
    
    # Should still match well due to token_sort_ratio
    assert score >= 70


def test_similarity_with_official_video_tag():
    """Test matching with YouTube 'Official Video' tag."""
    matcher = TrackMatcher()
    
    spotify_track = {
        'name': 'Shape of You',
        'artists': ['Ed Sheeran'],
        'album': '÷',
        'duration_ms': 233713
    }
    
    youtube_track = {
        'videoId': 'ed123',
        'title': 'Ed Sheeran - Shape of You (Official Video)',
        'artists': [{'name': 'Ed Sheeran'}],
        'duration_seconds': 234
    }
    
    score = matcher.calculate_similarity(spotify_track, youtube_track)
    
    # Should match well despite extra text (80+ is good match)
    assert score >= 80


def test_similarity_artist_mismatch():
    """Test score calculation when artists don't match."""
    matcher = TrackMatcher()
    
    spotify_track = {
        'name': 'Unique Song Title For Testing',
        'artists': ['Original Artist'],
        'album': 'Album',
        'duration_ms': 200000
    }
    
    youtube_track = {
        'videoId': 'cover123',
        'title': 'Different Title Completely',
        'artists': [{'name': 'Cover Artist'}],
        'duration_seconds': 200
    }
    
    score = matcher.calculate_similarity(spotify_track, youtube_track)
    
    # Both title AND artist mismatch should result in low score
    assert score < 65


def test_similarity_no_album_youtube():
    """Test similarity when YouTube has no album data."""
    matcher = TrackMatcher()
    
    spotify_track = {
        'name': 'Test Song',
        'artists': ['Artist'],
        'album': 'My Album',
        'duration_ms': 200000
    }
    
    youtube_track = {
        'videoId': 'test123',
        'title': 'Test Song',
        'artists': [{'name': 'Artist'}],
        # No album
        'duration_seconds': 200
    }
    
    score = matcher.calculate_similarity(spotify_track, youtube_track)
    
    # Should still score well (album is only 5% weight)
    assert score >= 90


# ============================================================================
# match_track() Tests
# ============================================================================

def test_match_track_single_result_above_threshold():
    """Test matching with single result above threshold."""
    matcher = TrackMatcher(threshold=75)
    
    spotify_track = {
        'name': 'Blinding Lights',
        'artists': ['The Weeknd'],
        'album': 'After Hours',
        'duration_ms': 200000
    }
    
    youtube_results = [
        {
            'videoId': 'correct123',
            'title': 'The Weeknd - Blinding Lights',
            'artists': [{'name': 'The Weeknd'}],
            'duration_seconds': 200
        }
    ]
    
    video_id, score = matcher.match_track(spotify_track, youtube_results)
    
    assert video_id == 'correct123'
    assert score >= 75


def test_match_track_multiple_results_best_match():
    """Test matching selects best result from multiple options."""
    matcher = TrackMatcher(threshold=70)
    
    spotify_track = {
        'name': 'Shape of You',
        'artists': ['Ed Sheeran'],
        'album': '÷',
        'duration_ms': 233713
    }
    
    youtube_results = [
        {
            'videoId': 'cover123',
            'title': 'Shape of You Cover',
            'artists': [{'name': 'Random Artist'}],
            'duration_seconds': 210
        },
        {
            'videoId': 'original456',
            'title': 'Ed Sheeran - Shape of You',
            'artists': [{'name': 'Ed Sheeran'}],
            'duration_seconds': 234
        },
        {
            'videoId': 'live789',
            'title': 'Shape of You Live',
            'artists': [{'name': 'Ed Sheeran'}],
            'duration_seconds': 280
        }
    ]
    
    video_id, score = matcher.match_track(spotify_track, youtube_results)
    
    assert video_id == 'original456'  # Should pick best match
    assert score >= 85


def test_match_track_no_results_above_threshold():
    """Test matching returns None when no results exceed threshold."""
    matcher = TrackMatcher(threshold=90)  # Very high threshold
    
    spotify_track = {
        'name': 'Obscure Song',
        'artists': ['Indie Artist'],
        'album': 'Unknown Album',
        'duration_ms': 180000
    }
    
    youtube_results = [
        {
            'videoId': 'wrong123',
            'title': 'Different Song',
            'artists': [{'name': 'Different Artist'}],
            'duration_seconds': 120
        }
    ]
    
    video_id, score = matcher.match_track(spotify_track, youtube_results)
    
    assert video_id is None
    assert score == 0.0


def test_match_track_empty_results():
    """Test matching with empty results list."""
    matcher = TrackMatcher()
    
    spotify_track = {
        'name': 'Test Song',
        'artists': ['Artist'],
        'album': 'Album',
        'duration_ms': 200000
    }
    
    video_id, score = matcher.match_track(spotify_track, [])
    
    assert video_id is None
    assert score == 0.0


def test_match_track_threshold_boundary():
    """Test matching at exact threshold boundary."""
    matcher = TrackMatcher(threshold=80)
    
    spotify_track = {
        'name': 'Test Song',
        'artists': ['Artist'],
        'album': 'Album',
        'duration_ms': 200000
    }
    
    youtube_results = [
        {
            'videoId': 'good_match',
            'title': 'Test Song',
            'artists': [{'name': 'Artist'}],
            'duration_seconds': 200
        }
    ]
    
    video_id, score = matcher.match_track(spotify_track, youtube_results)
    
    # Should return match since it exceeds threshold
    assert video_id is not None
    assert score >= 80


def test_no_match_below_threshold():
    """Test that match_track returns None when score below threshold.
    
    Per test_spec.md requirement #6:
    - matcher with threshold=75
    - Best result has score=70
    - Expected: match_track returns (None, 0)
    """
    matcher = TrackMatcher(threshold=75)
    
    spotify_track = {
        'name': 'Some Song Title',
        'artists': ['Artist Name'],
        'album': 'Album Name',
        'duration_ms': 200000
    }
    
    # Create YouTube results that will score below 75
    # Similar title but different artist = low score
    youtube_results = [
        {
            'videoId': 'video_low_score',
            'title': 'Similar Song Title',  # Slightly different
            'artists': [{'name': 'Different Artist'}],  # Wrong artist
            'album': {'name': 'Different Album'},
            'duration_seconds': 220  # Off by 20 seconds
        }
    ]
    
    video_id, score = matcher.match_track(spotify_track, youtube_results)
    
    # Should return None and 0 since no match exceeds threshold
    assert video_id is None
    assert score == 0


def test_multiple_results_picks_best():
    """Test that match_track selects highest scoring result.
    
    Per test_spec.md requirement #7:
    - YouTube results: [score 60, score 85, score 70]
    - Expected: Returns result with score 85
    """
    matcher = TrackMatcher(threshold=60)
    
    spotify_track = {
        'name': 'Blinding Lights',
        'artists': ['The Weeknd'],
        'album': 'After Hours',
        'duration_ms': 200000
    }
    
    youtube_results = [
        # Result 1: Low score (different artist)
        {
            'videoId': 'low_score_60',
            'title': 'Blinding Lights Cover',
            'artists': [{'name': 'Cover Artist'}],
            'album': {'name': 'Cover Album'},
            'duration_seconds': 180
        },
        # Result 2: High score (best match)
        {
            'videoId': 'high_score_85',
            'title': 'The Weeknd - Blinding Lights',
            'artists': [{'name': 'The Weeknd'}],
            'album': {'name': 'After Hours'},
            'duration_seconds': 200  # Perfect duration match
        },
        # Result 3: Medium score (correct artist, wrong album)
        {
            'videoId': 'medium_score_70',
            'title': 'Blinding Lights Live',
            'artists': [{'name': 'The Weeknd'}],
            'album': {'name': 'Live Album'},
            'duration_seconds': 215
        }
    ]
    
    video_id, score = matcher.match_track(spotify_track, youtube_results)
    
    # Should return the best match (high_score_85)
    assert video_id == 'high_score_85'
    assert score >= 85


# ============================================================================
# Real-World Integration Tests
# ============================================================================

def test_real_world_the_weeknd():
    """Test real-world example: The Weeknd - Blinding Lights."""
    matcher = TrackMatcher(threshold=75)
    
    spotify_track = {
        'name': 'Blinding Lights',
        'artists': ['The Weeknd'],
        'album': 'After Hours',
        'duration_ms': 200040
    }
    
    youtube_results = [
        {
            'videoId': 'official_video',
            'title': 'The Weeknd - Blinding Lights (Official Video)',
            'artists': [{'name': 'The Weeknd'}],
            'album': {'name': 'After Hours'},
            'duration_seconds': 200
        },
        {
            'videoId': 'live_performance',
            'title': 'The Weeknd - Blinding Lights (Live)',
            'artists': [{'name': 'The Weeknd'}],
            'duration_seconds': 245
        }
    ]
    
    video_id, score = matcher.match_track(spotify_track, youtube_results)
    
    assert video_id == 'official_video'
    assert score >= 90


def test_real_world_dua_lipa_featured():
    """Test real-world example with featured artist: Dua Lipa - Levitating."""
    matcher = TrackMatcher(threshold=75)
    
    spotify_track = {
        'name': 'Levitating (feat. DaBaby)',
        'artists': ['Dua Lipa'],
        'album': 'Future Nostalgia',
        'duration_ms': 203064
    }
    
    youtube_results = [
        {
            'videoId': 'feat_version',
            'title': 'Dua Lipa - Levitating feat. DaBaby',
            'artists': [{'name': 'Dua Lipa'}, {'name': 'DaBaby'}],
            'duration_seconds': 203
        },
        {
            'videoId': 'solo_version',
            'title': 'Dua Lipa - Levitating',
            'artists': [{'name': 'Dua Lipa'}],
            'duration_seconds': 203
        }
    ]
    
    video_id, score = matcher.match_track(spotify_track, youtube_results)
    
    # Both versions should match well; either is acceptable
    # The solo version may score higher due to simpler title matching
    assert video_id in ['feat_version', 'solo_version']
    assert score >= 85


def test_real_world_accents():
    """Test real-world example with accents: José González."""
    matcher = TrackMatcher(threshold=70)
    
    spotify_track = {
        'name': 'Heartbeats',
        'artists': ['José González'],
        'album': 'Veneer',
        'duration_ms': 177000
    }
    
    youtube_results = [
        {
            'videoId': 'official',
            'title': 'Jose Gonzalez - Heartbeats',  # No accent
            'artists': [{'name': 'José González'}],
            'duration_seconds': 177
        }
    ]
    
    video_id, score = matcher.match_track(spotify_track, youtube_results)
    
    # Should match despite accent differences
    assert video_id == 'official'
    assert score >= 90


def test_real_world_cover_rejection():
    """Test that covers are rejected when original is available."""
    matcher = TrackMatcher(threshold=75)
    
    spotify_track = {
        'name': 'Hallelujah',
        'artists': ['Leonard Cohen'],
        'album': 'Various Positions',
        'duration_ms': 274000
    }
    
    youtube_results = [
        {
            'videoId': 'original',
            'title': 'Leonard Cohen - Hallelujah',
            'artists': [{'name': 'Leonard Cohen'}],
            'duration_seconds': 274
        },
        {
            'videoId': 'cover',
            'title': 'Hallelujah',
            'artists': [{'name': 'Jeff Buckley'}],  # Different artist
            'duration_seconds': 420
        }
    ]
    
    video_id, score = matcher.match_track(spotify_track, youtube_results)
    
    # Should match original, not cover
    assert video_id == 'original'
