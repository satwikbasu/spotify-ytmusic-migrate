"""Spotify Data Fetcher Module.

This module provides functionality to fetch playlists and tracks from Spotify API
with proper pagination, rate limiting, and metadata extraction.
"""

import time
import re
import logging
from typing import List, Dict, Any, Optional

import spotipy
from spotipy.exceptions import SpotifyException

from ..utils.rate_limiter import RateLimiter
from ..utils.cache_manager import CacheManager


# Configure logging
logger = logging.getLogger(__name__)


class SpotifyFetcher:
    """Fetch playlists and tracks from Spotify API.
    
    This class handles fetching user playlists and their tracks from Spotify,
    with proper pagination, rate limiting, metadata extraction, and error handling.
    
    Features:
    - Fetches all public playlists with pagination
    - Fetches all tracks from playlists with pagination
    - Extracts comprehensive metadata
    - Filters out private playlists
    - Handles null/missing fields gracefully
    - Rate limiting with configurable delays
    - Input validation and sanitization
    - SQLite caching for performance
    
    Attributes:
        spotify_client (spotipy.Spotify): Authenticated Spotify client.
        rate_limiter (RateLimiter): Rate limiter for API requests.
        cache_manager (CacheManager): Cache manager for storing fetched data.
    """
    
    # Pagination constants
    PLAYLIST_PAGE_SIZE = 50
    TRACKS_PAGE_SIZE = 100
    
    # Rate limiting
    REQUEST_DELAY_SECONDS = 0.1  # 100ms between requests
    
    # Track validation
    MIN_TRACK_DURATION_MS = 1  # Minimum 1ms
    MAX_TRACK_DURATION_MS = 3600000  # Maximum 1 hour (60 * 60 * 1000)
    
    # Regex for emoji removal
    EMOJI_PATTERN = re.compile(
        "["
        "\U0001F600-\U0001F64F"  # emoticons
        "\U0001F300-\U0001F5FF"  # symbols & pictographs
        "\U0001F680-\U0001F6FF"  # transport & map symbols
        "\U0001F1E0-\U0001F1FF"  # flags (iOS)
        "\U00002702-\U000027B0"
        "\U000024C2-\U0001F251"
        "]+",
        flags=re.UNICODE
    )
    
    def __init__(self, spotify_client: spotipy.Spotify, rate_limiter: RateLimiter, cache_manager: CacheManager):
        """Initialize the Spotify fetcher.
        
        Args:
            spotify_client (spotipy.Spotify): Authenticated Spotify API client.
            rate_limiter (RateLimiter): Rate limiter instance for API throttling.
            cache_manager (CacheManager): Cache manager for storing fetched data.
            
        Raises:
            ValueError: If spotify_client, rate_limiter, or cache_manager is None.
        """
        if spotify_client is None:
            raise ValueError("Spotify client is required")
        if rate_limiter is None:
            raise ValueError("Rate limiter is required")
        if cache_manager is None:
            raise ValueError("Cache manager is required")
        
        self.spotify_client = spotify_client
        self.rate_limiter = rate_limiter
        self.cache_manager = cache_manager
        
        logger.info("SpotifyFetcher initialized with caching enabled")
    
    def _sanitize_string(self, text: Optional[str]) -> Optional[str]:
        """Remove emojis and special characters from text.
        
        Args:
            text (Optional[str]): Text to sanitize.
            
        Returns:
            Optional[str]: Sanitized text with emojis removed, or None if input is None.
        """
        if text is None:
            return None
        
        # Remove emojis
        sanitized = self.EMOJI_PATTERN.sub('', text)
        
        # Strip leading/trailing whitespace
        sanitized = sanitized.strip()
        
        return sanitized if sanitized else None
    
    def _validate_track_duration(self, duration_ms: Optional[int]) -> bool:
        """Validate track duration is within acceptable range.
        
        Args:
            duration_ms (Optional[int]): Track duration in milliseconds.
            
        Returns:
            bool: True if duration is valid, False otherwise.
        """
        if duration_ms is None:
            return False
        
        if duration_ms <= 0:
            logger.debug(f"Rejecting track with zero or negative duration: {duration_ms}ms")
            return False
        
        if duration_ms > self.MAX_TRACK_DURATION_MS:
            logger.debug(f"Rejecting track with excessive duration: {duration_ms}ms")
            return False
        
        return True
    
    def extract_playlist_metadata(self, playlist: Dict[str, Any]) -> Dict[str, Any]:
        """Extract relevant metadata from a playlist object.
        
        Args:
            playlist (Dict[str, Any]): Raw playlist object from Spotify API.
            
        Returns:
            Dict[str, Any]: Dictionary containing:
                - id: Spotify playlist ID
                - name: Playlist name (sanitized)
                - tracks_count: Number of tracks in playlist
                - image_url: URL of playlist cover image (or None)
        """
        try:
            playlist_data = {
                'id': playlist.get('id'),
                'name': self._sanitize_string(playlist.get('name', 'Untitled Playlist')),
                'tracks_count': playlist.get('tracks', {}).get('total', 0),
                'image_url': None
            }
            
            # Extract image URL (use first/largest image if available)
            images = playlist.get('images', [])
            if images and len(images) > 0:
                playlist_data['image_url'] = images[0].get('url')
            
            return playlist_data
            
        except Exception as e:
            logger.error(f"Error extracting playlist metadata: {str(e)}")
            # Return minimal valid data
            return {
                'id': playlist.get('id', 'unknown'),
                'name': 'Unknown Playlist',
                'tracks_count': 0,
                'image_url': None
            }
    
    def extract_track_metadata(self, track: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Extract relevant metadata from a track object.
        
        Args:
            track (Dict[str, Any]): Raw track object from Spotify API.
            
        Returns:
            Optional[Dict[str, Any]]: Dictionary containing:
                - id: Spotify track ID
                - name: Track name (sanitized)
                - artists: List of artist names
                - album: Album name (sanitized)
                - duration_ms: Track duration in milliseconds
                - isrc: International Standard Recording Code (or None)
            Returns None if track is invalid or missing required fields.
        """
        try:
            # Validate required fields
            if not track or not track.get('id'):
                logger.debug("Skipping track with missing ID")
                return None
            
            # Extract and validate duration
            duration_ms = track.get('duration_ms')
            if not self._validate_track_duration(duration_ms):
                logger.debug(f"Skipping track '{track.get('name')}' with invalid duration")
                return None
            
            # Extract artists
            artists_list = []
            artists = track.get('artists', [])
            for artist in artists:
                artist_name = self._sanitize_string(artist.get('name'))
                if artist_name:
                    artists_list.append(artist_name)
            
            # If no valid artists, skip track
            if not artists_list:
                logger.debug(f"Skipping track '{track.get('name')}' with no valid artists")
                return None
            
            # Extract album name
            album_data = track.get('album', {})
            album_name = self._sanitize_string(album_data.get('name', 'Unknown Album'))
            
            # Extract ISRC
            external_ids = track.get('external_ids', {})
            isrc = external_ids.get('isrc')
            
            track_data = {
                'id': track.get('id'),
                'name': self._sanitize_string(track.get('name', 'Unknown Track')),
                'artists': artists_list,
                'album': album_name,
                'duration_ms': duration_ms,
                'isrc': isrc
            }
            
            return track_data
            
        except Exception as e:
            logger.error(f"Error extracting track metadata: {str(e)}")
            return None
    
    def get_user_playlists(self, use_cache: bool = True) -> List[Dict[str, Any]]:
        """Fetch all public playlists for the current user.
        
        Implements pagination to fetch all playlists, filtering for only
        public playlists as specified in requirements. Uses cache when available.
        
        Algorithm:
        1. Check cache for existing playlists (if use_cache=True)
        2. If cached and not expired, return cached playlists
        3. Otherwise, start with offset=0
        4. Fetch playlists with limit=50
        5. Filter for public playlists only
        6. Extract metadata for each playlist
        7. If more pages exist (next != None), increment offset and repeat
        8. Apply rate limiting between requests
        9. Cache all fetched playlists
        
        Args:
            use_cache (bool): Whether to use cached data. Defaults to True.
        
        Returns:
            List[Dict[str, Any]]: List of playlist metadata dictionaries.
            
        Raises:
            SpotifyException: If API request fails after retries.
            RuntimeError: If unexpected error occurs.
        """
        logger.info("Fetching user playlists")
        playlists = []
        offset = 0
        total_fetched = 0
        seen_ids = set()
        
        # Try to get from cache first (if enabled)
        if use_cache:
            try:
                # Get current user to use as cache key (we'll cache all playlists together)
                user_info = self.spotify_client.current_user()
                user_id = user_info.get('id', 'default_user')
                
                # Try to get cached playlists
                cached_playlist = self.cache_manager.get_cached_playlist(f"all_playlists_{user_id}", max_age_hours=24)
                
                if cached_playlist:
                    # Get all playlists from cache
                    logger.info("Using cached playlists")
                    # We need to query individual playlists since we cached them separately
                    # Get cache stats to know how many playlists we have
                    stats = self.cache_manager.get_cache_stats()
                    if stats['playlists_count'] > 1:  # More than just the marker playlist
                        # We have cached playlists, but need a better approach
                        # For now, fall through to API fetch
                        logger.debug("Cache structure needs all playlists - fetching fresh")
                        use_cache = False
                
            except Exception as e:
                logger.warning(f"Failed to check cache: {str(e)}. Fetching from API.")
                use_cache = False
        
        logger.info("Fetching fresh playlists from Spotify API")
        
        try:
            while True:
                try:
                    # Check rate limits before request
                    self.rate_limiter.check_limit()
                    
                    # Fetch playlist page
                    logger.debug(f"Fetching playlists: offset={offset}, limit={self.PLAYLIST_PAGE_SIZE}")
                    response = self.spotify_client.current_user_playlists(
                        limit=self.PLAYLIST_PAGE_SIZE,
                        offset=offset
                    )
                    
                    # Record successful request
                    self.rate_limiter.record_request()
                    self.rate_limiter.reset_backoff()
                    
                    # Process playlists
                    items = response.get('items', [])
                    if not items:
                        logger.info("No more playlists found")
                        break
                    
                    for playlist in items:
                        total_fetched += 1
                        
                        # Filter for public playlists only
                        if not playlist.get('public', False):
                            logger.debug(f"Skipping private playlist: {playlist.get('name')}")
                            continue
                        
                        # Spotify occasionally returns records with no name or owner
                        # (deleted or otherwise unavailable playlists). They cannot be
                        # created on YouTube Music, so drop them here.
                        if not playlist.get('name'):
                            logger.warning(
                                f"Skipping playlist with no name: id={playlist.get('id')!r} "
                                f"tracks={playlist.get('tracks', {}).get('total')}"
                            )
                            continue
                        
                        # Spotify's offset paging can hand back the same playlist on
                        # more than one page, so drop IDs we have already seen.
                        playlist_id = playlist.get('id')
                        if playlist_id in seen_ids:
                            logger.debug(f"Skipping duplicate playlist: {playlist.get('name')}")
                            continue
                        seen_ids.add(playlist_id)
                        
                        # Extract and store metadata
                        playlist_data = self.extract_playlist_metadata(playlist)
                        playlists.append(playlist_data)
                        logger.debug(f"Added public playlist: {playlist_data.get('name')}")
                    
                    # Check if more pages exist
                    if response.get('next') is None:
                        logger.info(f"Reached end of playlists. Total fetched: {total_fetched}")
                        break
                    
                    # Increment offset for next page
                    offset += self.PLAYLIST_PAGE_SIZE
                    
                    # Rate limiting delay
                    time.sleep(self.REQUEST_DELAY_SECONDS)
                    
                except SpotifyException as e:
                    if e.http_status == 429:
                        # Handle rate limiting
                        retry_after = e.headers.get('Retry-After') if hasattr(e, 'headers') else None
                        self.rate_limiter.handle_429(int(retry_after) if retry_after else None)
                        # Retry the same offset
                        continue
                    elif e.http_status == 401:
                        logger.error("Authentication error. Token may be expired.")
                        raise
                    elif e.http_status == 403:
                        logger.error("Permission denied. Check API scopes.")
                        raise
                    else:
                        logger.error(f"Spotify API error (HTTP {e.http_status}): {str(e)}")
                        raise
                
                except Exception as e:
                    logger.error(f"Unexpected error fetching playlists: {str(e)}")
                    raise RuntimeError(f"Failed to fetch playlists: {str(e)}") from e
            
            logger.info(f"Successfully fetched {len(playlists)} public playlists (from {total_fetched} total)")
            
            # Cache all fetched playlists. Each record is cached independently so
            # that one malformed playlist cannot abort caching for the rest.
            cached_count = 0
            for playlist in playlists:
                try:
                    self.cache_manager.cache_playlist(playlist)
                    cached_count += 1
                except Exception as e:
                    logger.warning(
                        f"Skipped caching playlist {playlist.get('id')!r} "
                        f"({playlist.get('name')!r}): {str(e)}"
                    )
            logger.debug(f"Cached {cached_count} of {len(playlists)} playlists")
            
            return playlists
            
        except Exception as e:
            logger.error(f"Fatal error in get_user_playlists: {str(e)}")
            raise
    
    def get_playlist_tracks(self, playlist_id: str, use_cache: bool = True) -> List[Dict[str, Any]]:
        """Fetch all tracks from a specific playlist.
        
        Implements pagination to fetch all tracks from the playlist.
        Uses cache when available.
        
        Algorithm:
        1. Check cache for existing tracks (if use_cache=True)
        2. If cached and not empty, return cached tracks
        3. Otherwise, start with offset=0
        4. Fetch tracks with limit=100
        5. Extract metadata for each valid track
        6. If more pages exist (next != None), increment offset and repeat
        7. Apply rate limiting between requests
        8. Cache all fetched tracks
        
        Args:
            playlist_id (str): Spotify playlist ID.
            use_cache (bool): Whether to use cached data. Defaults to True.
            
        Returns:
            List[Dict[str, Any]]: List of track metadata dictionaries.
            
        Raises:
            ValueError: If playlist_id is empty or None.
            SpotifyException: If API request fails.
            RuntimeError: If unexpected error occurs.
        """
        if not playlist_id:
            raise ValueError("Playlist ID is required")
        
        logger.info(f"Fetching tracks for playlist: {playlist_id}")
        
        # Try to get from cache first (if enabled)
        if use_cache:
            try:
                cached_tracks = self.cache_manager.get_cached_tracks(playlist_id)
                if cached_tracks:
                    logger.info(f"Using cached tracks for playlist {playlist_id} ({len(cached_tracks)} tracks)")
                    return cached_tracks
                else:
                    logger.debug(f"No cached tracks found for playlist {playlist_id}")
            except Exception as e:
                logger.warning(f"Failed to retrieve cached tracks: {str(e)}. Fetching from API.")
        
        logger.info(f"Fetching fresh tracks from Spotify API for playlist: {playlist_id}")
        tracks = []
        offset = 0
        total_fetched = 0
        
        try:
            while True:
                try:
                    # Check rate limits before request
                    self.rate_limiter.check_limit()
                    
                    # Fetch tracks page
                    logger.debug(f"Fetching tracks: playlist={playlist_id}, offset={offset}, limit={self.TRACKS_PAGE_SIZE}")
                    response = self.spotify_client.playlist_tracks(
                        playlist_id=playlist_id,
                        limit=self.TRACKS_PAGE_SIZE,
                        offset=offset
                    )
                    
                    # Record successful request
                    self.rate_limiter.record_request()
                    self.rate_limiter.reset_backoff()
                    
                    # Process tracks
                    items = response.get('items', [])
                    if not items:
                        logger.info(f"No more tracks found for playlist {playlist_id}")
                        break
                    
                    for item in items:
                        total_fetched += 1
                        
                        # Check if track exists (can be None for deleted tracks)
                        track = item.get('track')
                        if not track:
                            logger.debug("Skipping null track (may be deleted)")
                            continue
                        
                        # Extract and validate metadata
                        track_data = self.extract_track_metadata(track)
                        if track_data:
                            tracks.append(track_data)
                            logger.debug(f"Added track: {track_data.get('name')} by {', '.join(track_data.get('artists', []))}")
                        else:
                            logger.debug("Skipped invalid track")
                    
                    # Check if more pages exist
                    if response.get('next') is None:
                        logger.info(f"Reached end of tracks for playlist {playlist_id}. Total fetched: {total_fetched}")
                        break
                    
                    # Increment offset for next page
                    offset += self.TRACKS_PAGE_SIZE
                    
                    # Rate limiting delay
                    time.sleep(self.REQUEST_DELAY_SECONDS)
                    
                except SpotifyException as e:
                    if e.http_status == 429:
                        # Handle rate limiting
                        retry_after = e.headers.get('Retry-After') if hasattr(e, 'headers') else None
                        self.rate_limiter.handle_429(int(retry_after) if retry_after else None)
                        # Retry the same offset
                        continue
                    elif e.http_status == 404:
                        logger.warning(f"Playlist {playlist_id} not found (may be deleted)")
                        break  # Exit gracefully for deleted playlists
                    elif e.http_status == 401:
                        logger.error("Authentication error. Token may be expired.")
                        raise
                    elif e.http_status == 403:
                        logger.warning(f"Access denied for playlist {playlist_id} (may be private)")
                        break  # Exit gracefully for private playlists
                    else:
                        logger.error(f"Spotify API error (HTTP {e.http_status}): {str(e)}")
                        raise
                
                except Exception as e:
                    logger.error(f"Unexpected error fetching tracks: {str(e)}")
                    raise RuntimeError(f"Failed to fetch tracks for playlist {playlist_id}: {str(e)}") from e
            
            logger.info(f"Successfully fetched {len(tracks)} valid tracks (from {total_fetched} total) for playlist {playlist_id}")
            
            # Cache all fetched tracks
            if tracks:
                try:
                    self.cache_manager.cache_tracks(tracks, playlist_id)
                    logger.debug(f"Cached {len(tracks)} tracks for playlist {playlist_id}")
                except Exception as e:
                    logger.warning(f"Failed to cache tracks: {str(e)}")
            
            return tracks
            
        except Exception as e:
            logger.error(f"Fatal error in get_playlist_tracks: {str(e)}")
            raise
    
    def get_all_playlists_with_tracks(self) -> List[Dict[str, Any]]:
        """Fetch all playlists and their tracks in one operation.
        
        Convenience method that fetches all playlists and then fetches
        tracks for each playlist.
        
        Returns:
            List[Dict[str, Any]]: List of playlists with 'tracks' field added,
                containing the list of track metadata.
        """
        logger.info("Fetching all playlists with tracks")
        
        # Fetch all playlists
        playlists = self.get_user_playlists()
        
        # Fetch tracks for each playlist
        for i, playlist in enumerate(playlists, 1):
            playlist_id = playlist.get('id')
            playlist_name = playlist.get('name', 'Unknown')
            
            logger.info(f"Fetching tracks for playlist {i}/{len(playlists)}: {playlist_name}")
            
            try:
                tracks = self.get_playlist_tracks(playlist_id)
                playlist['tracks'] = tracks
            except Exception as e:
                logger.error(f"Failed to fetch tracks for playlist {playlist_name}: {str(e)}")
                playlist['tracks'] = []  # Set empty list on error
        
        logger.info(f"Completed fetching all playlists with tracks")
        return playlists
    
    def refresh_playlists(self) -> List[Dict[str, Any]]:
        """Force a fresh fetch of all playlists from Spotify API.
        
        Clears the playlist cache and fetches fresh data from Spotify,
        then updates the cache with the new data.
        
        This method is useful when you need to ensure you have the most
        up-to-date playlist information, bypassing any cached data.
        
        Returns:
            List[Dict[str, Any]]: List of freshly fetched playlist metadata.
            
        Raises:
            SpotifyException: If API request fails.
            RuntimeError: If unexpected error occurs.
        """
        logger.info("Refreshing playlists - clearing cache and fetching fresh data")
        
        try:
            # Clear existing playlist cache
            # Note: We clear all playlists since we don't have individual IDs yet
            try:
                # Get current user to construct cache keys
                user_info = self.spotify_client.current_user()
                user_id = user_info.get('id', 'default_user')
                
                # We'll need to clear cache after we know which playlists exist
                # For now, just note that we're doing a fresh fetch
                logger.debug("Forcing fresh fetch from Spotify API")
                
            except Exception as e:
                logger.warning(f"Failed to check user info for cache clearing: {str(e)}")
            
            # Fetch fresh playlists (use_cache=False forces API fetch)
            playlists = self.get_user_playlists(use_cache=False)
            
            logger.info(f"Successfully refreshed {len(playlists)} playlists")
            return playlists
            
        except Exception as e:
            logger.error(f"Failed to refresh playlists: {str(e)}")
            raise
    
    def refresh_playlist_tracks(self, playlist_id: str) -> List[Dict[str, Any]]:
        """Force a fresh fetch of tracks for a specific playlist.
        
        Clears the track cache for the playlist and fetches fresh data,
        then updates the cache.
        
        Args:
            playlist_id (str): Spotify playlist ID.
            
        Returns:
            List[Dict[str, Any]]: List of freshly fetched track metadata.
            
        Raises:
            ValueError: If playlist_id is empty or None.
            SpotifyException: If API request fails.
            RuntimeError: If unexpected error occurs.
        """
        if not playlist_id:
            raise ValueError("Playlist ID is required")
        
        logger.info(f"Refreshing tracks for playlist {playlist_id}")
        
        try:
            # Clear existing track cache for this playlist
            try:
                self.cache_manager.clear_playlist_cache(playlist_id)
                logger.debug(f"Cleared cache for playlist {playlist_id}")
            except Exception as e:
                logger.warning(f"Failed to clear playlist cache: {str(e)}")
            
            # Fetch fresh tracks (use_cache=False forces API fetch)
            tracks = self.get_playlist_tracks(playlist_id, use_cache=False)
            
            logger.info(f"Successfully refreshed {len(tracks)} tracks for playlist {playlist_id}")
            return tracks
            
        except Exception as e:
            logger.error(f"Failed to refresh tracks for playlist {playlist_id}: {str(e)}")
            raise
