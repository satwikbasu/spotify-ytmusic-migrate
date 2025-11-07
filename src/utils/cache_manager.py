"""SQLite Cache Manager Module.

This module provides SQLite-based caching for playlists, tracks, and match results
to minimize API calls and improve performance.
"""

import os
import json
import sqlite3
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta


# Configure logging
logger = logging.getLogger(__name__)


class CacheManager:
    """SQLite-based cache manager for playlist and track data.
    
    This class manages a SQLite database cache for:
    - Playlists with metadata and fetch timestamps
    - Tracks with full metadata and JSON-encoded artists
    - Match results linking Spotify tracks to YouTube videos
    
    The cache supports expiration policies for both playlists (hours) and
    matches (days) to ensure data freshness while reducing API calls.
    
    Schema:
        playlists:
            - id (TEXT PRIMARY KEY): Spotify playlist ID
            - name (TEXT): Playlist name
            - tracks_count (INTEGER): Number of tracks
            - image_url (TEXT): Cover image URL
            - last_fetched (TIMESTAMP): When playlist was last cached
            
        tracks:
            - spotify_id (TEXT PRIMARY KEY): Spotify track ID
            - playlist_id (TEXT): Associated playlist ID
            - name (TEXT): Track name
            - artists (TEXT): JSON-encoded list of artist names
            - album (TEXT): Album name
            - duration_ms (INTEGER): Track duration in milliseconds
            - isrc (TEXT): International Standard Recording Code
            
        match_cache:
            - spotify_id (TEXT PRIMARY KEY): Spotify track ID
            - youtube_video_id (TEXT): Matched YouTube video ID
            - confidence (REAL): Match confidence score (0.0-1.0)
            - matched_at (TIMESTAMP): When match was cached
    
    Attributes:
        db_path (str): Path to the SQLite database file.
        connection (sqlite3.Connection): Database connection.
    """
    
    DEFAULT_DB_PATH = "~/.playlist_migrator/cache.db"
    
    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        """Initialize the cache manager and create tables.
        
        Args:
            db_path (str): Path to SQLite database file. Supports ~ for home directory.
                Defaults to ~/.playlist_migrator/cache.db.
                
        Raises:
            sqlite3.Error: If database connection or table creation fails.
        """
        # Expand user home directory
        self.db_path = os.path.expanduser(db_path)
        
        # Create parent directory if it doesn't exist
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, mode=0o700)
            logger.info(f"Created cache directory: {db_dir}")
        
        try:
            # Create database connection
            self.connection = sqlite3.connect(self.db_path)
            self.connection.row_factory = sqlite3.Row  # Enable column access by name
            
            logger.info(f"Connected to cache database: {self.db_path}")
            
            # Create tables
            self.create_tables()
            
        except sqlite3.Error as e:
            logger.error(f"Failed to initialize cache database: {str(e)}")
            raise
    
    def create_tables(self) -> None:
        """Create database tables and indexes if they don't exist.
        
        Creates three tables: playlists, tracks, and match_cache.
        Also creates indexes on frequently queried columns for performance.
        
        Raises:
            sqlite3.Error: If table or index creation fails.
        """
        try:
            with self.connection:
                cursor = self.connection.cursor()
                
                # Create playlists table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS playlists (
                        id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        tracks_count INTEGER DEFAULT 0,
                        image_url TEXT,
                        last_fetched TIMESTAMP NOT NULL
                    )
                """)
                
                # Create tracks table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS tracks (
                        spotify_id TEXT PRIMARY KEY,
                        playlist_id TEXT NOT NULL,
                        name TEXT NOT NULL,
                        artists TEXT NOT NULL,
                        album TEXT,
                        duration_ms INTEGER,
                        isrc TEXT,
                        FOREIGN KEY (playlist_id) REFERENCES playlists(id)
                    )
                """)
                
                # Create match_cache table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS match_cache (
                        spotify_id TEXT PRIMARY KEY,
                        youtube_video_id TEXT NOT NULL,
                        confidence REAL NOT NULL,
                        matched_at TIMESTAMP NOT NULL
                    )
                """)
                
                # Create indexes for performance
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_tracks_spotify_id 
                    ON tracks(spotify_id)
                """)
                
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_tracks_playlist_id 
                    ON tracks(playlist_id)
                """)
                
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_match_cache_spotify_id 
                    ON match_cache(spotify_id)
                """)
                
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_playlists_last_fetched 
                    ON playlists(last_fetched)
                """)
                
                logger.info("Database tables and indexes created successfully")
                
        except sqlite3.Error as e:
            logger.error(f"Failed to create tables: {str(e)}")
            raise
    
    def cache_playlist(self, playlist: Dict[str, Any]) -> None:
        """Cache playlist metadata.
        
        Inserts or updates playlist information in the cache with current timestamp.
        
        Args:
            playlist (Dict[str, Any]): Playlist dictionary containing:
                - id: Spotify playlist ID
                - name: Playlist name
                - tracks_count: Number of tracks
                - image_url: Cover image URL (optional)
                
        Raises:
            ValueError: If required fields are missing.
            sqlite3.Error: If database operation fails.
        """
        if not playlist.get('id'):
            raise ValueError("Playlist ID is required")
        if not playlist.get('name'):
            raise ValueError("Playlist name is required")
        
        try:
            with self.connection:
                cursor = self.connection.cursor()
                
                cursor.execute("""
                    INSERT OR REPLACE INTO playlists 
                    (id, name, tracks_count, image_url, last_fetched)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    playlist.get('id'),
                    playlist.get('name'),
                    playlist.get('tracks_count', 0),
                    playlist.get('image_url'),
                    datetime.now()
                ))
                
                logger.debug(f"Cached playlist: {playlist.get('name')} ({playlist.get('id')})")
                
        except sqlite3.Error as e:
            logger.error(f"Failed to cache playlist: {str(e)}")
            raise
    
    def cache_tracks(self, tracks: List[Dict[str, Any]], playlist_id: str) -> None:
        """Cache multiple tracks for a playlist.
        
        Bulk inserts or updates track metadata using executemany for efficiency.
        Artists list is converted to JSON string for storage.
        
        Args:
            tracks (List[Dict[str, Any]]): List of track dictionaries containing:
                - id: Spotify track ID
                - name: Track name
                - artists: List of artist names
                - album: Album name
                - duration_ms: Duration in milliseconds
                - isrc: ISRC code (optional)
            playlist_id (str): Spotify playlist ID these tracks belong to.
            
        Raises:
            ValueError: If playlist_id is empty or tracks list is invalid.
            sqlite3.Error: If database operation fails.
        """
        if not playlist_id:
            raise ValueError("Playlist ID is required")
        
        if not tracks:
            logger.debug("No tracks to cache")
            return
        
        try:
            with self.connection:
                cursor = self.connection.cursor()
                
                # Prepare track data for bulk insert
                track_data = []
                for track in tracks:
                    if not track.get('id'):
                        logger.warning(f"Skipping track without ID: {track.get('name')}")
                        continue
                    
                    # Convert artists list to JSON string
                    artists_json = json.dumps(track.get('artists', []))
                    
                    track_data.append((
                        track.get('id'),
                        playlist_id,
                        track.get('name', 'Unknown'),
                        artists_json,
                        track.get('album'),
                        track.get('duration_ms'),
                        track.get('isrc')
                    ))
                
                # Bulk insert tracks
                cursor.executemany("""
                    INSERT OR REPLACE INTO tracks 
                    (spotify_id, playlist_id, name, artists, album, duration_ms, isrc)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, track_data)
                
                logger.info(f"Cached {len(track_data)} tracks for playlist {playlist_id}")
                
        except sqlite3.Error as e:
            logger.error(f"Failed to cache tracks: {str(e)}")
            raise
        except json.JSONEncodeError as e:
            logger.error(f"Failed to encode artists to JSON: {str(e)}")
            raise ValueError(f"Invalid artists data: {str(e)}") from e
    
    def get_cached_playlist(self, playlist_id: str, max_age_hours: int = 24) -> Optional[Dict[str, Any]]:
        """Retrieve cached playlist if not expired.
        
        Args:
            playlist_id (str): Spotify playlist ID.
            max_age_hours (int): Maximum age in hours for cache validity.
                Defaults to 24 hours.
                
        Returns:
            Optional[Dict[str, Any]]: Playlist dictionary if cached and not expired,
                None otherwise.
                
        Raises:
            sqlite3.Error: If database query fails.
        """
        if not playlist_id:
            return None
        
        try:
            cursor = self.connection.cursor()
            
            # Calculate cutoff timestamp
            cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
            
            cursor.execute("""
                SELECT id, name, tracks_count, image_url, last_fetched
                FROM playlists
                WHERE id = ? AND last_fetched > ?
            """, (playlist_id, cutoff_time))
            
            row = cursor.fetchone()
            
            if row:
                playlist = {
                    'id': row['id'],
                    'name': row['name'],
                    'tracks_count': row['tracks_count'],
                    'image_url': row['image_url'],
                    'last_fetched': row['last_fetched']
                }
                logger.debug(f"Cache hit for playlist: {playlist_id}")
                return playlist
            else:
                logger.debug(f"Cache miss for playlist: {playlist_id}")
                return None
                
        except sqlite3.Error as e:
            logger.error(f"Failed to retrieve cached playlist: {str(e)}")
            raise
    
    def get_cached_tracks(self, playlist_id: str) -> List[Dict[str, Any]]:
        """Retrieve all cached tracks for a playlist.
        
        Args:
            playlist_id (str): Spotify playlist ID.
            
        Returns:
            List[Dict[str, Any]]: List of track dictionaries. Returns empty list
                if no tracks found.
                
        Raises:
            sqlite3.Error: If database query fails.
        """
        if not playlist_id:
            return []
        
        try:
            cursor = self.connection.cursor()
            
            cursor.execute("""
                SELECT spotify_id, playlist_id, name, artists, album, duration_ms, isrc
                FROM tracks
                WHERE playlist_id = ?
            """, (playlist_id,))
            
            rows = cursor.fetchall()
            
            tracks = []
            for row in rows:
                try:
                    # Convert JSON artists back to list
                    artists_list = json.loads(row['artists'])
                    
                    track = {
                        'id': row['spotify_id'],
                        'playlist_id': row['playlist_id'],
                        'name': row['name'],
                        'artists': artists_list,
                        'album': row['album'],
                        'duration_ms': row['duration_ms'],
                        'isrc': row['isrc']
                    }
                    tracks.append(track)
                    
                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to decode artists JSON for track {row['spotify_id']}: {str(e)}")
                    continue
            
            logger.debug(f"Retrieved {len(tracks)} cached tracks for playlist {playlist_id}")
            return tracks
            
        except sqlite3.Error as e:
            logger.error(f"Failed to retrieve cached tracks: {str(e)}")
            raise
    
    def cache_match(self, spotify_id: str, youtube_id: str, confidence: float) -> None:
        """Cache a Spotify-to-YouTube track match.
        
        Args:
            spotify_id (str): Spotify track ID.
            youtube_id (str): YouTube video ID.
            confidence (float): Match confidence score (0.0-1.0).
            
        Raises:
            ValueError: If required fields are missing or confidence out of range.
            sqlite3.Error: If database operation fails.
        """
        if not spotify_id:
            raise ValueError("Spotify ID is required")
        if not youtube_id:
            raise ValueError("YouTube ID is required")
        if not 0.0 <= confidence <= 1.0:
            raise ValueError("Confidence must be between 0.0 and 1.0")
        
        try:
            with self.connection:
                cursor = self.connection.cursor()
                
                cursor.execute("""
                    INSERT OR REPLACE INTO match_cache 
                    (spotify_id, youtube_video_id, confidence, matched_at)
                    VALUES (?, ?, ?, ?)
                """, (
                    spotify_id,
                    youtube_id,
                    confidence,
                    datetime.now()
                ))
                
                logger.debug(f"Cached match: {spotify_id} -> {youtube_id} (confidence: {confidence:.2f})")
                
        except sqlite3.Error as e:
            logger.error(f"Failed to cache match: {str(e)}")
            raise
    
    def get_cached_match(self, spotify_id: str, max_age_days: int = 30) -> Optional[Dict[str, Any]]:
        """Retrieve cached YouTube match for a Spotify track.
        
        Args:
            spotify_id (str): Spotify track ID.
            max_age_days (int): Maximum age in days for cache validity.
                Defaults to 30 days.
                
        Returns:
            Optional[Dict[str, Any]]: Match dictionary containing youtube_video_id
                and confidence if cached and not expired, None otherwise.
                
        Raises:
            sqlite3.Error: If database query fails.
        """
        if not spotify_id:
            return None
        
        try:
            cursor = self.connection.cursor()
            
            # Calculate cutoff timestamp
            cutoff_time = datetime.now() - timedelta(days=max_age_days)
            
            cursor.execute("""
                SELECT youtube_video_id, confidence, matched_at
                FROM match_cache
                WHERE spotify_id = ? AND matched_at > ?
            """, (spotify_id, cutoff_time))
            
            row = cursor.fetchone()
            
            if row:
                match = {
                    'youtube_video_id': row['youtube_video_id'],
                    'confidence': row['confidence'],
                    'matched_at': row['matched_at']
                }
                logger.debug(f"Cache hit for match: {spotify_id} -> {match['youtube_video_id']}")
                return match
            else:
                logger.debug(f"Cache miss for match: {spotify_id}")
                return None
                
        except sqlite3.Error as e:
            logger.error(f"Failed to retrieve cached match: {str(e)}")
            raise
    
    def clear_cache(self) -> None:
        """Clear all cached data from all tables.
        
        Warning:
            This permanently deletes all cached playlists, tracks, and matches.
            
        Raises:
            sqlite3.Error: If database operation fails.
        """
        try:
            with self.connection:
                cursor = self.connection.cursor()
                
                cursor.execute("DELETE FROM match_cache")
                cursor.execute("DELETE FROM tracks")
                cursor.execute("DELETE FROM playlists")
                
                logger.info("All cache data cleared")
                
        except sqlite3.Error as e:
            logger.error(f"Failed to clear cache: {str(e)}")
            raise
    
    def clear_playlist_cache(self, playlist_id: str) -> None:
        """Clear cached data for a specific playlist.
        
        Removes the playlist and all its associated tracks from cache.
        
        Args:
            playlist_id (str): Spotify playlist ID.
            
        Raises:
            sqlite3.Error: If database operation fails.
        """
        if not playlist_id:
            return
        
        try:
            with self.connection:
                cursor = self.connection.cursor()
                
                cursor.execute("DELETE FROM tracks WHERE playlist_id = ?", (playlist_id,))
                cursor.execute("DELETE FROM playlists WHERE id = ?", (playlist_id,))
                
                logger.info(f"Cleared cache for playlist: {playlist_id}")
                
        except sqlite3.Error as e:
            logger.error(f"Failed to clear playlist cache: {str(e)}")
            raise
    
    def get_cache_stats(self) -> Dict[str, int]:
        """Get statistics about cached data.
        
        Returns:
            Dict[str, int]: Dictionary containing:
                - playlists_count: Number of cached playlists
                - tracks_count: Number of cached tracks
                - matches_count: Number of cached matches
        """
        try:
            cursor = self.connection.cursor()
            
            cursor.execute("SELECT COUNT(*) as count FROM playlists")
            playlists_count = cursor.fetchone()['count']
            
            cursor.execute("SELECT COUNT(*) as count FROM tracks")
            tracks_count = cursor.fetchone()['count']
            
            cursor.execute("SELECT COUNT(*) as count FROM match_cache")
            matches_count = cursor.fetchone()['count']
            
            return {
                'playlists_count': playlists_count,
                'tracks_count': tracks_count,
                'matches_count': matches_count
            }
            
        except sqlite3.Error as e:
            logger.error(f"Failed to get cache stats: {str(e)}")
            return {'playlists_count': 0, 'tracks_count': 0, 'matches_count': 0}
    
    def close(self) -> None:
        """Close the database connection.
        
        Should be called when finished using the cache manager.
        Safe to call multiple times.
        """
        if self.connection:
            try:
                self.connection.close()
                logger.info("Cache database connection closed")
            except sqlite3.Error as e:
                logger.error(f"Error closing database connection: {str(e)}")
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - ensures connection is closed."""
        self.close()
    
    def __del__(self):
        """Destructor - ensures connection is closed."""
        self.close()
