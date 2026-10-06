"""Comprehensive pytest tests for src/utils/cache_manager.py.

Tests cover:
- Database table creation and schema validation
- Playlist caching and retrieval with expiration
- Track caching with JSON serialization of artists
- Match caching and retrieval with expiration
- Cache clearing operations
- Error handling and edge cases

Following test_spec.md requirements.
"""

import os
import pytest
import tempfile
import sqlite3
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

from src.utils.cache_manager import CacheManager


@pytest.fixture
def temp_db_path():
    """Create a temporary database file for testing."""
    # Create temp file (will be deleted after test)
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)  # Close the file descriptor
    
    yield path
    
    # Cleanup
    try:
        if os.path.exists(path):
            os.unlink(path)
    except Exception:
        pass


@pytest.fixture
def cache_manager(temp_db_path):
    """Create a CacheManager instance with temporary database."""
    manager = CacheManager(db_path=temp_db_path)
    yield manager
    manager.close()


@pytest.fixture
def sample_playlist():
    """Sample playlist data for testing."""
    return {
        'id': 'playlist123',
        'name': 'My Test Playlist',
        'tracks_count': 10,
        'image_url': 'https://example.com/image.jpg'
    }


@pytest.fixture
def sample_tracks():
    """Sample track data for testing."""
    return [
        {
            'id': 'track001',
            'name': 'Blinding Lights',
            'artists': ['The Weeknd'],
            'album': 'After Hours',
            'duration_ms': 200000,
            'isrc': 'USUG12000123'
        },
        {
            'id': 'track002',
            'name': 'Lose Yourself',
            'artists': ['Eminem'],
            'album': '8 Mile Soundtrack',
            'duration_ms': 326000,
            'isrc': 'USIR10200001'
        }
    ]


# ============================================================================
# Test Class: Database Table Creation
# ============================================================================

class TestCreateTables:
    """Test database table creation and schema validation."""
    
    def test_create_tables(self, cache_manager):
        """Test that all required tables are created.
        
        Verifies:
        - playlists table exists
        - tracks table exists
        - match_cache table exists
        - All required indexes exist
        """
        cursor = cache_manager.connection.cursor()
        
        # Query sqlite_master for all tables
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name NOT LIKE 'sqlite_%'
            ORDER BY name
        """)
        tables = [row[0] for row in cursor.fetchall()]
        
        # Verify all expected tables exist
        assert 'playlists' in tables
        assert 'tracks' in tables
        assert 'match_cache' in tables
    
    def test_playlists_table_schema(self, cache_manager):
        """Test playlists table has correct schema."""
        cursor = cache_manager.connection.cursor()
        cursor.execute("PRAGMA table_info(playlists)")
        columns = {row[1]: row[2] for row in cursor.fetchall()}  # name: type
        
        assert 'id' in columns
        assert 'name' in columns
        assert 'tracks_count' in columns
        assert 'image_url' in columns
        assert 'last_fetched' in columns
    
    def test_tracks_table_schema(self, cache_manager):
        """Test tracks table has correct schema."""
        cursor = cache_manager.connection.cursor()
        cursor.execute("PRAGMA table_info(tracks)")
        columns = {row[1]: row[2] for row in cursor.fetchall()}
        
        assert 'spotify_id' in columns
        assert 'playlist_id' in columns
        assert 'name' in columns
        assert 'artists' in columns  # JSON-encoded
        assert 'album' in columns
        assert 'duration_ms' in columns
        assert 'isrc' in columns
    
    def test_match_cache_table_schema(self, cache_manager):
        """Test match_cache table has correct schema."""
        cursor = cache_manager.connection.cursor()
        cursor.execute("PRAGMA table_info(match_cache)")
        columns = {row[1]: row[2] for row in cursor.fetchall()}
        
        assert 'spotify_id' in columns
        assert 'youtube_video_id' in columns
        assert 'confidence' in columns
        assert 'matched_at' in columns
    
    def test_indexes_created(self, cache_manager):
        """Test that all required indexes are created."""
        cursor = cache_manager.connection.cursor()
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='index' AND name NOT LIKE 'sqlite_%'
        """)
        indexes = [row[0] for row in cursor.fetchall()]
        
        assert 'idx_tracks_spotify_id' in indexes
        assert 'idx_tracks_playlist_id' in indexes
        assert 'idx_match_cache_spotify_id' in indexes
        assert 'idx_playlists_last_fetched' in indexes


# ============================================================================
# Test Class: Playlist Caching
# ============================================================================

class TestPlaylistCaching:
    """Test playlist caching and retrieval."""
    
    def test_cache_and_retrieve_playlist(self, cache_manager, sample_playlist):
        """Test caching a playlist and retrieving it.
        
        Per test_spec.md requirement #2:
        - Cache a playlist
        - Retrieve it
        - Verify all fields match
        """
        # Cache the playlist
        cache_manager.cache_playlist(sample_playlist)
        
        # Retrieve it
        retrieved = cache_manager.get_cached_playlist(sample_playlist['id'])
        
        # Verify all fields match
        assert retrieved is not None
        assert retrieved['id'] == sample_playlist['id']
        assert retrieved['name'] == sample_playlist['name']
        assert retrieved['tracks_count'] == sample_playlist['tracks_count']
        assert retrieved['image_url'] == sample_playlist['image_url']
        assert 'last_fetched' in retrieved
    
    def test_cache_expiry(self, cache_manager, sample_playlist):
        """Test that cached playlist expires after max_age_hours.
        
        Per test_spec.md requirement #3:
        - Cache playlist
        - Mock time to 25 hours later
        - Try to retrieve (max_age_hours=24)
        - Should return None
        """
        # Cache the playlist
        cache_manager.cache_playlist(sample_playlist)
        
        # Verify it's in cache
        assert cache_manager.get_cached_playlist(sample_playlist['id']) is not None
        
        # Mock datetime to 25 hours later
        with patch('src.utils.cache_manager.datetime') as mock_datetime:
            future_time = datetime.now() + timedelta(hours=25)
            mock_datetime.now.return_value = future_time
            
            # Try to retrieve with max_age_hours=24 (should be expired)
            retrieved = cache_manager.get_cached_playlist(
                sample_playlist['id'], 
                max_age_hours=24
            )
            
            assert retrieved is None
    
    def test_cache_playlist_update(self, cache_manager, sample_playlist):
        """Test that caching same playlist updates existing entry."""
        # Cache initial version
        cache_manager.cache_playlist(sample_playlist)
        
        # Update playlist data
        updated_playlist = sample_playlist.copy()
        updated_playlist['name'] = 'Updated Playlist Name'
        updated_playlist['tracks_count'] = 20
        
        # Cache updated version
        cache_manager.cache_playlist(updated_playlist)
        
        # Retrieve and verify updated data
        retrieved = cache_manager.get_cached_playlist(sample_playlist['id'])
        assert retrieved['name'] == 'Updated Playlist Name'
        assert retrieved['tracks_count'] == 20
    
    def test_cache_playlist_missing_id_raises_error(self, cache_manager):
        """Test that caching playlist without ID raises ValueError."""
        invalid_playlist = {'name': 'Test Playlist'}
        
        with pytest.raises(ValueError, match="Playlist ID is required"):
            cache_manager.cache_playlist(invalid_playlist)
    
    def test_cache_playlist_missing_name_raises_error(self, cache_manager):
        """Test that caching playlist without name raises ValueError."""
        invalid_playlist = {'id': 'playlist123'}
        
        with pytest.raises(ValueError, match="Playlist name is required"):
            cache_manager.cache_playlist(invalid_playlist)
    
    def test_get_cached_playlist_nonexistent(self, cache_manager):
        """Test retrieving non-existent playlist returns None."""
        retrieved = cache_manager.get_cached_playlist('nonexistent_id')
        assert retrieved is None
    
    def test_get_cached_playlist_empty_id_returns_none(self, cache_manager):
        """Test retrieving with empty ID returns None."""
        assert cache_manager.get_cached_playlist('') is None
        assert cache_manager.get_cached_playlist(None) is None


# ============================================================================
# Test Class: Track Caching
# ============================================================================

class TestTrackCaching:
    """Test track caching with JSON serialization."""
    
    def test_cache_tracks(self, cache_manager, sample_tracks, sample_playlist):
        """Test caching multiple tracks for a playlist.
        
        Per test_spec.md requirement #4:
        - Cache multiple tracks for a playlist
        - Retrieve them
        - Verify count and content
        """
        playlist_id = sample_playlist['id']
        
        # Cache tracks
        cache_manager.cache_tracks(sample_tracks, playlist_id)
        
        # Retrieve tracks
        retrieved = cache_manager.get_cached_tracks(playlist_id)
        
        # Verify count
        assert len(retrieved) == 2
        
        # Verify content
        track_ids = [t['id'] for t in retrieved]
        assert 'track001' in track_ids
        assert 'track002' in track_ids
        
        # Verify first track details
        track1 = next(t for t in retrieved if t['id'] == 'track001')
        assert track1['name'] == 'Blinding Lights'
        assert track1['artists'] == ['The Weeknd']
        assert track1['album'] == 'After Hours'
        assert track1['duration_ms'] == 200000
    
    def test_cache_tracks_with_json_artists(self, cache_manager, sample_playlist):
        """Test track caching with multiple artists (JSON serialization).
        
        Per test_spec.md requirement #5:
        - Cache track with artists list: ["Artist A", "Artist B"]
        - Retrieve and verify artists list properly deserialized
        """
        tracks = [{
            'id': 'track_multi',
            'name': 'Collaboration Song',
            'artists': ['Artist A', 'Artist B', 'Artist C'],
            'album': 'Collab Album',
            'duration_ms': 250000,
            'isrc': 'TEST12345'
        }]
        
        # Cache track
        cache_manager.cache_tracks(tracks, sample_playlist['id'])
        
        # Retrieve and verify
        retrieved = cache_manager.get_cached_tracks(sample_playlist['id'])
        assert len(retrieved) == 1
        assert retrieved[0]['artists'] == ['Artist A', 'Artist B', 'Artist C']
        assert isinstance(retrieved[0]['artists'], list)
    
    def test_cache_tracks_empty_list(self, cache_manager, sample_playlist):
        """Test caching empty tracks list does nothing."""
        cache_manager.cache_tracks([], sample_playlist['id'])
        
        # Verify no tracks cached
        retrieved = cache_manager.get_cached_tracks(sample_playlist['id'])
        assert len(retrieved) == 0
    
    def test_cache_tracks_missing_playlist_id_raises_error(self, cache_manager, sample_tracks):
        """Test caching tracks without playlist_id raises ValueError."""
        with pytest.raises(ValueError, match="Playlist ID is required"):
            cache_manager.cache_tracks(sample_tracks, '')
    
    def test_cache_tracks_update(self, cache_manager, sample_tracks, sample_playlist):
        """Test that caching same track updates existing entry."""
        playlist_id = sample_playlist['id']
        
        # Cache initial tracks
        cache_manager.cache_tracks(sample_tracks, playlist_id)
        
        # Update track data
        updated_track = [{
            'id': 'track001',  # Same ID
            'name': 'Blinding Lights (Updated)',
            'artists': ['The Weeknd', 'Featured Artist'],
            'album': 'After Hours Deluxe',
            'duration_ms': 205000,
            'isrc': 'USUG12000123'
        }]
        
        # Cache updated track
        cache_manager.cache_tracks(updated_track, playlist_id)
        
        # Retrieve and verify updated data
        retrieved = cache_manager.get_cached_tracks(playlist_id)
        track = next(t for t in retrieved if t['id'] == 'track001')
        assert track['name'] == 'Blinding Lights (Updated)'
        assert len(track['artists']) == 2
    
    def test_get_cached_tracks_nonexistent_playlist(self, cache_manager):
        """Test retrieving tracks for non-existent playlist returns empty list."""
        retrieved = cache_manager.get_cached_tracks('nonexistent_playlist')
        assert retrieved == []
    
    def test_get_cached_tracks_empty_id_returns_empty_list(self, cache_manager):
        """Test retrieving tracks with empty ID returns empty list."""
        assert cache_manager.get_cached_tracks('') == []
        assert cache_manager.get_cached_tracks(None) == []


# ============================================================================
# Test Class: Match Caching
# ============================================================================

class TestMatchCaching:
    """Test Spotify-YouTube match caching."""
    
    def test_cache_match(self, cache_manager):
        """Test caching a Spotify→YouTube match.
        
        Per test_spec.md requirement #6:
        - Cache a Spotify→YouTube match
        - Retrieve it
        - Verify video ID and confidence
        """
        spotify_id = 'spotify_track_123'
        youtube_id = 'youtube_video_456'
        confidence = 0.92
        
        # Cache match
        cache_manager.cache_match(spotify_id, youtube_id, confidence)
        
        # Retrieve match
        retrieved = cache_manager.get_cached_match(spotify_id)
        
        # Verify data
        assert retrieved is not None
        assert retrieved['youtube_video_id'] == youtube_id
        assert retrieved['confidence'] == confidence
        assert 'matched_at' in retrieved
    
    def test_match_cache_expiry(self, cache_manager):
        """Test that cached match expires after max_age_days.
        
        Per test_spec.md requirement #7:
        - Cache match
        - Mock time to 31 days later
        - Try to retrieve (max_age_days=30)
        - Should return None
        """
        spotify_id = 'spotify_track_expire'
        youtube_id = 'youtube_video_expire'
        
        # Cache match
        cache_manager.cache_match(spotify_id, youtube_id, 0.85)
        
        # Verify it's in cache
        assert cache_manager.get_cached_match(spotify_id) is not None
        
        # Mock datetime to 31 days later
        with patch('src.utils.cache_manager.datetime') as mock_datetime:
            future_time = datetime.now() + timedelta(days=31)
            mock_datetime.now.return_value = future_time
            
            # Try to retrieve with max_age_days=30 (should be expired)
            retrieved = cache_manager.get_cached_match(
                spotify_id, 
                max_age_days=30
            )
            
            assert retrieved is None
    
    def test_cache_match_update(self, cache_manager):
        """Test that caching same spotify_id updates match."""
        spotify_id = 'spotify_track_update'
        
        # Cache initial match
        cache_manager.cache_match(spotify_id, 'youtube_v1', 0.75)
        
        # Update with better match
        cache_manager.cache_match(spotify_id, 'youtube_v2', 0.95)
        
        # Retrieve and verify updated match
        retrieved = cache_manager.get_cached_match(spotify_id)
        assert retrieved['youtube_video_id'] == 'youtube_v2'
        assert retrieved['confidence'] == 0.95
    
    def test_cache_match_missing_spotify_id_raises_error(self, cache_manager):
        """Test caching match without spotify_id raises ValueError."""
        with pytest.raises(ValueError, match="Spotify ID is required"):
            cache_manager.cache_match('', 'youtube_id', 0.8)
    
    def test_cache_match_missing_youtube_id_raises_error(self, cache_manager):
        """Test caching match without youtube_id raises ValueError."""
        with pytest.raises(ValueError, match="YouTube ID is required"):
            cache_manager.cache_match('spotify_id', '', 0.8)
    
    def test_cache_match_invalid_confidence_raises_error(self, cache_manager):
        """Test caching match with invalid confidence raises ValueError."""
        # Confidence too high
        with pytest.raises(ValueError, match="Confidence must be between 0.0 and 1.0"):
            cache_manager.cache_match('spotify_id', 'youtube_id', 1.5)
        
        # Confidence too low
        with pytest.raises(ValueError, match="Confidence must be between 0.0 and 1.0"):
            cache_manager.cache_match('spotify_id', 'youtube_id', -0.1)
    
    def test_get_cached_match_nonexistent(self, cache_manager):
        """Test retrieving non-existent match returns None."""
        retrieved = cache_manager.get_cached_match('nonexistent_spotify_id')
        assert retrieved is None
    
    def test_get_cached_match_empty_id_returns_none(self, cache_manager):
        """Test retrieving match with empty ID returns None."""
        assert cache_manager.get_cached_match('') is None
        assert cache_manager.get_cached_match(None) is None


# ============================================================================
# Test Class: Cache Clearing
# ============================================================================

class TestCacheClearing:
    """Test cache clearing operations."""
    
    def test_clear_cache(self, cache_manager, sample_playlist, sample_tracks):
        """Test clearing all cache data.
        
        Per test_spec.md requirement #8:
        - Populate all tables
        - Call clear_cache()
        - Verify all tables empty
        """
        # Populate all tables
        cache_manager.cache_playlist(sample_playlist)
        cache_manager.cache_tracks(sample_tracks, sample_playlist['id'])
        cache_manager.cache_match('track001', 'youtube_vid', 0.9)
        
        # Verify data exists
        stats = cache_manager.get_cache_stats()
        assert stats['playlists_count'] > 0
        assert stats['tracks_count'] > 0
        assert stats['matches_count'] > 0
        
        # Clear cache
        cache_manager.clear_cache()
        
        # Verify all tables empty
        stats = cache_manager.get_cache_stats()
        assert stats['playlists_count'] == 0
        assert stats['tracks_count'] == 0
        assert stats['matches_count'] == 0
    
    def test_clear_playlist_cache(self, cache_manager, sample_playlist, sample_tracks):
        """Test clearing cache for specific playlist."""
        playlist_id = sample_playlist['id']
        
        # Cache playlist and tracks
        cache_manager.cache_playlist(sample_playlist)
        cache_manager.cache_tracks(sample_tracks, playlist_id)
        
        # Add another playlist
        other_playlist = {'id': 'other123', 'name': 'Other Playlist', 'tracks_count': 5}
        cache_manager.cache_playlist(other_playlist)
        
        # Clear specific playlist
        cache_manager.clear_playlist_cache(playlist_id)
        
        # Verify specific playlist cleared
        assert cache_manager.get_cached_playlist(playlist_id) is None
        assert cache_manager.get_cached_tracks(playlist_id) == []
        
        # Verify other playlist still exists
        assert cache_manager.get_cached_playlist('other123') is not None
    
    def test_clear_playlist_cache_empty_id_does_nothing(self, cache_manager):
        """Test clearing with empty playlist_id does nothing."""
        # Should not raise error
        cache_manager.clear_playlist_cache('')
        cache_manager.clear_playlist_cache(None)


# ============================================================================
# Test Class: Cache Statistics
# ============================================================================

class TestCacheStatistics:
    """Test cache statistics retrieval."""
    
    def test_get_cache_stats_empty(self, cache_manager):
        """Test cache stats when empty."""
        stats = cache_manager.get_cache_stats()
        
        assert stats['playlists_count'] == 0
        assert stats['tracks_count'] == 0
        assert stats['matches_count'] == 0
    
    def test_get_cache_stats_populated(self, cache_manager, sample_playlist, sample_tracks):
        """Test cache stats with data."""
        # Populate cache
        cache_manager.cache_playlist(sample_playlist)
        cache_manager.cache_tracks(sample_tracks, sample_playlist['id'])
        cache_manager.cache_match('track001', 'youtube_vid', 0.9)
        
        # Get stats
        stats = cache_manager.get_cache_stats()
        
        assert stats['playlists_count'] == 1
        assert stats['tracks_count'] == 2
        assert stats['matches_count'] == 1


# ============================================================================
# Test Class: Context Manager
# ============================================================================

class TestContextManager:
    """Test context manager functionality."""
    
    def test_context_manager_closes_connection(self, temp_db_path):
        """Test that context manager properly closes connection."""
        with CacheManager(db_path=temp_db_path) as manager:
            # Verify connection is open
            assert manager.connection is not None
            
            # Use the manager
            stats = manager.get_cache_stats()
            assert isinstance(stats, dict)
        
        # After exiting context, connection should be closed
        # Attempting to use it should raise error
        with pytest.raises(sqlite3.ProgrammingError):
            manager.connection.cursor()
    
    def test_close_method_can_be_called_multiple_times(self, cache_manager):
        """Test that close() is idempotent."""
        # Should not raise error
        cache_manager.close()
        cache_manager.close()
        cache_manager.close()


# ============================================================================
# Test Class: Edge Cases and Error Handling
# ============================================================================

class TestEdgeCases:
    """Test edge cases and error handling."""
    
    def test_track_without_id_skipped(self, cache_manager, sample_playlist):
        """Test that tracks without ID are skipped during caching."""
        tracks = [
            {'id': 'track001', 'name': 'Valid Track', 'artists': ['Artist']},
            {'name': 'Invalid Track', 'artists': ['Artist']},  # No ID
            {'id': 'track002', 'name': 'Another Valid Track', 'artists': ['Artist']}
        ]
        
        cache_manager.cache_tracks(tracks, sample_playlist['id'])
        
        # Should only cache the 2 valid tracks
        retrieved = cache_manager.get_cached_tracks(sample_playlist['id'])
        assert len(retrieved) == 2
    
    def test_database_directory_creation(self):
        """Test that database directory is created if it doesn't exist."""
        # Create path with non-existent directory
        import uuid
        temp_dir = os.path.join(tempfile.gettempdir(), str(uuid.uuid4()))
        db_path = os.path.join(temp_dir, 'test.db')
        
        try:
            # Create cache manager (should create directory)
            manager = CacheManager(db_path=db_path)
            
            # Verify directory was created
            assert os.path.exists(temp_dir)
            assert os.path.exists(db_path)
            
            manager.close()
        finally:
            # Cleanup
            if os.path.exists(db_path):
                os.unlink(db_path)
            if os.path.exists(temp_dir):
                os.rmdir(temp_dir)
    
    def test_track_with_minimal_fields(self, cache_manager, sample_playlist):
        """Test caching track with only required fields."""
        minimal_track = [{
            'id': 'minimal_track',
            'name': 'Minimal Track'
            # Missing: artists, album, duration_ms, isrc
        }]
        
        # Should not raise error
        cache_manager.cache_tracks(minimal_track, sample_playlist['id'])
        
        # Retrieve and verify
        retrieved = cache_manager.get_cached_tracks(sample_playlist['id'])
        assert len(retrieved) == 1
        assert retrieved[0]['id'] == 'minimal_track'
        assert retrieved[0]['artists'] == []  # Default empty list
    
    def test_playlist_with_minimal_fields(self, cache_manager):
        """Test caching playlist with only required fields."""
        minimal_playlist = {
            'id': 'minimal_playlist',
            'name': 'Minimal Playlist'
            # Missing: tracks_count, image_url
        }
        
        # Should not raise error
        cache_manager.cache_playlist(minimal_playlist)
        
        # Retrieve and verify
        retrieved = cache_manager.get_cached_playlist('minimal_playlist')
        assert retrieved is not None
        assert retrieved['tracks_count'] == 0  # Default value
    
    def test_match_confidence_boundary_values(self, cache_manager):
        """Test match caching with boundary confidence values."""
        # Exact 0.0
        cache_manager.cache_match('track_0', 'youtube_0', 0.0)
        match = cache_manager.get_cached_match('track_0')
        assert match['confidence'] == 0.0
        
        # Exact 1.0
        cache_manager.cache_match('track_1', 'youtube_1', 1.0)
        match = cache_manager.get_cached_match('track_1')
        assert match['confidence'] == 1.0


# ============================================================================
# Test Class: Track order and multi-playlist membership (resume depends on both)
# ============================================================================

class TestTrackOrderAndMembership:
    """get_cached_tracks must return source order, and a track in two
    playlists must be kept for each - a resumed job walks the tracks table."""
    
    def test_tracks_come_back_in_source_order(self, cache_manager):
        tracks = [{'id': f'z{i:03d}', 'name': f'Song {i}', 'artists': []} for i in range(20, 0, -1)]
        cache_manager.cache_tracks(tracks, 'pl')
        
        retrieved = cache_manager.get_cached_tracks('pl')
        assert [t['id'] for t in retrieved] == [t['id'] for t in tracks]
    
    def test_recache_keeps_original_position(self, cache_manager):
        tracks = [{'id': 'a', 'name': 'A', 'artists': []}, {'id': 'b', 'name': 'B', 'artists': []}]
        cache_manager.cache_tracks(tracks, 'pl')
        cache_manager.cache_tracks([{'id': 'a', 'name': 'A2', 'artists': []}], 'pl')
        
        retrieved = cache_manager.get_cached_tracks('pl')
        assert [t['id'] for t in retrieved] == ['a', 'b']
        assert retrieved[0]['name'] == 'A2'
    
    def test_same_track_in_two_playlists_kept_for_both(self, cache_manager):
        track = [{'id': 'shared', 'name': 'Shared', 'artists': ['X']}]
        cache_manager.cache_tracks(track, 'pl1')
        cache_manager.cache_tracks(track, 'pl2')
        
        assert [t['id'] for t in cache_manager.get_cached_tracks('pl1')] == ['shared']
        assert [t['id'] for t in cache_manager.get_cached_tracks('pl2')] == ['shared']
    
    def test_legacy_tracks_table_is_upgraded_keeping_rows(self, temp_db_path):
        """A database created before the composite key / position column is
        rebuilt in place and its rows survive."""
        conn = sqlite3.connect(temp_db_path)
        conn.execute("""
            CREATE TABLE tracks (
                spotify_id TEXT PRIMARY KEY,
                playlist_id TEXT NOT NULL,
                name TEXT NOT NULL,
                artists TEXT NOT NULL,
                album TEXT,
                duration_ms INTEGER,
                isrc TEXT
            )
        """)
        conn.execute("INSERT INTO tracks VALUES ('old1', 'pl', 'Old One', '[\"A\"]', 'Alb', 1000, NULL)")
        conn.execute("INSERT INTO tracks VALUES ('old2', 'pl', 'Old Two', '[]', NULL, NULL, NULL)")
        conn.commit()
        conn.close()
        
        manager = CacheManager(db_path=temp_db_path)
        try:
            cursor = manager.connection.cursor()
            cursor.execute("PRAGMA table_info(tracks)")
            info = cursor.fetchall()
            assert 'position' in {row[1] for row in info}
            assert {row[1] for row in info if row[5]} == {'spotify_id', 'playlist_id'}
            
            retrieved = manager.get_cached_tracks('pl')
            assert [t['id'] for t in retrieved] == ['old1', 'old2']
            assert retrieved[0]['artists'] == ['A']
            
            # Now the same track can live in a second playlist
            manager.cache_tracks([{'id': 'old1', 'name': 'Old One', 'artists': ['A']}], 'pl2')
            assert len(manager.get_cached_tracks('pl')) == 2
            assert len(manager.get_cached_tracks('pl2')) == 1
        finally:
            manager.close()
