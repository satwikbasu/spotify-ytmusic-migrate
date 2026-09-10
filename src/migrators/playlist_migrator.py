"""Playlist migration engine for Spotify to YouTube Music migration.

This module implements the core migration logic, orchestrating search, matching,
caching, and batch addition of tracks to YouTube Music playlists.
"""

import time
import logging
from typing import List, Dict, Optional, Callable, Any, Generator

from ytmusicapi import YTMusic
from ytmusicapi.exceptions import YTMusicServerError

from src.searchers.youtube_searcher import YouTubeSearcher
from src.matchers.track_matcher import TrackMatcher
from src.utils.cache_manager import CacheManager
from src.utils.rate_limiter import RateLimiter


# Configure logging
logger = logging.getLogger(__name__)


class PlaylistMigrator:
    """Orchestrates migration of Spotify playlists to YouTube Music.
    
    Implements the complete migration pipeline:
    1. Create YouTube Music playlist
    2. Search and match tracks (with caching)
    3. Batch add matched tracks (100 at a time)
    4. Generate migration report
    
    Attributes:
        ytmusic_client: Authenticated YTMusic API client
        youtube_searcher: YouTube Music search service
        track_matcher: Fuzzy matching engine
        cache_manager: SQLite cache for matched tracks
        rate_limiter: Rate limiting service
    """
    
    # Batch configuration
    BATCH_SIZE = 100  # YouTube Music allows 100 tracks per request
    BATCH_DELAY = 0.5  # 500ms delay between batch additions
    
    # YouTube Music URL template
    PLAYLIST_URL_TEMPLATE = "https://music.youtube.com/playlist?list={}"
    
    def __init__(
        self,
        ytmusic_client: YTMusic,
        youtube_searcher: YouTubeSearcher,
        track_matcher: TrackMatcher,
        cache_manager: CacheManager,
        rate_limiter: RateLimiter
    ):
        """Initialize the playlist migrator.
        
        Args:
            ytmusic_client: Authenticated YTMusic client
            youtube_searcher: YouTube Music search service
            track_matcher: Track matching service
            cache_manager: Cache manager for match results
            rate_limiter: Rate limiter for API requests
        
        Raises:
            ValueError: If any required dependency is None
        """
        if ytmusic_client is None:
            raise ValueError("ytmusic_client cannot be None")
        if youtube_searcher is None:
            raise ValueError("youtube_searcher cannot be None")
        if track_matcher is None:
            raise ValueError("track_matcher cannot be None")
        if cache_manager is None:
            raise ValueError("cache_manager cannot be None")
        if rate_limiter is None:
            raise ValueError("rate_limiter cannot be None")
        
        self.ytmusic_client = ytmusic_client
        self.youtube_searcher = youtube_searcher
        self.track_matcher = track_matcher
        self.cache_manager = cache_manager
        self.rate_limiter = rate_limiter
        
        logger.info("PlaylistMigrator initialized")
    
    def migrate_playlist(
        self,
        playlist_name: str,
        tracks: List[Dict[str, Any]],
        progress_callback: Optional[Callable[[int, int, str], None]] = None
    ) -> Dict[str, Any]:
        """Migrate a Spotify playlist to YouTube Music.
        
        Complete migration pipeline:
        1. Create YouTube Music playlist
        2. For each Spotify track:
           - Check cache for previous match
           - If not cached, search YouTube Music
           - Fuzzy match best result
           - Cache successful match
           - Collect video ID
           - Report progress
        3. Batch add all matched video IDs (100 per batch)
        4. Generate and return migration report
        
        Args:
            playlist_name: Name for the YouTube Music playlist
            tracks: List of Spotify track dicts with keys:
                - name: Track name (str)
                - artists: Artist names (List[str])
                - album: Album name (str)
                - duration_ms: Duration in milliseconds (int)
                - isrc: ISRC code (str, optional)
                - spotify_id: Spotify track ID (str)
            progress_callback: Optional callback function called after
                each track is processed. Signature:
                callback(current: int, total: int, track_name: str)
        
        Returns:
            Migration report dict with keys:
            - playlist_name: str
            - playlist_url: str (YouTube Music URL)
            - total_tracks: int
            - matched_tracks: int
            - failed_tracks: List[dict] with {spotify_track, reason}
            - success_rate: float (percentage)
            - match_scores: List[float] (confidence scores)
            - duration_seconds: float (time taken)
        
        Raises:
            ValueError: If playlist_name is empty or tracks list is empty
        
        Example:
            >>> migrator = PlaylistMigrator(ytmusic, searcher, matcher, cache, limiter)
            >>> tracks = [
            ...     {
            ...         'name': 'Blinding Lights',
            ...         'artists': ['The Weeknd'],
            ...         'album': 'After Hours',
            ...         'duration_ms': 200040,
            ...         'spotify_id': 'abc123'
            ...     }
            ... ]
            >>> report = migrator.migrate_playlist("My Playlist", tracks)
            >>> report['success_rate']
            100.0
        """
        # Validation
        if not playlist_name:
            raise ValueError("playlist_name cannot be empty")
        if not tracks:
            raise ValueError("tracks list cannot be empty")
        
        # Start timing
        start_time = time.time()
        
        logger.info(f"Starting migration for playlist: {playlist_name} ({len(tracks)} tracks)")
        
        # Initialize report data
        total_tracks = len(tracks)
        matched_video_ids = []
        match_scores = []
        failed_tracks = []
        
        # STEP 1: Create YouTube Music playlist
        try:
            playlist_id = self._create_youtube_playlist(playlist_name)
            logger.info(f"Created YouTube Music playlist: {playlist_id}")
        except Exception as e:
            logger.error(f"Failed to create YouTube Music playlist: {e}", exc_info=True)
            raise RuntimeError(f"Failed to create playlist: {e}") from e
        
        # STEP 2: Process each track (search, match, cache)
        for idx, spotify_track in enumerate(tracks, start=1):
            track_name = spotify_track.get('name', 'Unknown Track')
            
            try:
                # Debug track data
                
                # Process the track
                video_id, confidence = self._process_track(spotify_track)
                
                # Debug logging
                logger.debug(f"[{idx}/{total_tracks}] _process_track returned: video_id={video_id}, confidence={confidence}")
                
                if video_id:
                    matched_video_ids.append(video_id)
                    match_scores.append(confidence)
                    logger.info(
                        f"[{idx}/{total_tracks}] Matched: {track_name} "
                        f"(confidence: {confidence:.1f}%)"
                    )
                else:
                    # No match found
                    failed_tracks.append({
                        'spotify_track': spotify_track,
                        'reason': 'No match found above threshold'
                    })
                    logger.warning(f"[{idx}/{total_tracks}] No match: {track_name}")
            
            except Exception as e:
                # Track processing failed
                failed_tracks.append({
                    'spotify_track': spotify_track,
                    'reason': f'Error: {str(e)}'
                })
                logger.error(
                    f"[{idx}/{total_tracks}] EXCEPTION processing {track_name}: {type(e).__name__}: {e}",
                    exc_info=True
                )
            
            # Report progress with current match/fail counts
            if progress_callback:
                try:
                    # Pass current matched and failed counts
                    matched_so_far = len(matched_video_ids)
                    failed_so_far = len(failed_tracks)
                    progress_callback(idx, total_tracks, track_name, matched_so_far, failed_so_far)
                except TypeError:
                    # Fallback for old callback signature (3 params)
                    try:
                        progress_callback(idx, total_tracks, track_name)
                    except Exception as e:
                        logger.error(f"Progress callback error: {e}", exc_info=True)
                except Exception as e:
                    logger.error(f"Progress callback error: {e}", exc_info=True)
        
        # STEP 3: Batch add matched tracks to playlist
        if matched_video_ids:
            logger.info(f"Adding {len(matched_video_ids)} tracks to playlist in batches...")
            try:
                self.add_tracks_batch(playlist_id, matched_video_ids)
                logger.info("Successfully added all matched tracks")
            except Exception as e:
                logger.error(f"Error adding tracks to playlist: {e}", exc_info=True)
                # Don't raise - we still want to return the report
        
        # Calculate migration statistics
        matched_count = len(matched_video_ids)
        success_rate = (matched_count / total_tracks * 100) if total_tracks > 0 else 0
        duration = time.time() - start_time
        
        # STEP 4: Generate migration report
        report = {
            'playlist_name': playlist_name,
            'playlist_url': self.PLAYLIST_URL_TEMPLATE.format(playlist_id),
            'total_tracks': total_tracks,
            'matched_tracks': matched_count,
            'failed_tracks': failed_tracks,
            'success_rate': success_rate,
            'match_scores': match_scores,
            'duration_seconds': duration
        }
        
        logger.info(
            f"Migration complete: {matched_count}/{total_tracks} tracks "
            f"({success_rate:.1f}%) in {duration:.1f}s"
        )
        
        return report
    
    def _create_youtube_playlist(self, playlist_name: str) -> str:
        """Create a new YouTube Music playlist.
        
        Args:
            playlist_name: Name for the playlist
        
        Returns:
            YouTube Music playlist ID
        
        Raises:
            Exception: If playlist creation fails
        """
        description = f"Migrated from Spotify by spotify-yt-migrate"
        
        try:
            # Check rate limiter (blocks if necessary)
            self.rate_limiter.check_limit()
            
            # Create playlist
            playlist_id = self.ytmusic_client.create_playlist(
                title=playlist_name,
                description=description
            )
            
            # Record request
            self.rate_limiter.record_request()
            
            return playlist_id
        
        except Exception as e:
            logger.error(f"Failed to create playlist '{playlist_name}': {e}")
            raise
    
    def _process_track(
        self,
        spotify_track: Dict[str, Any]
    ) -> tuple[Optional[str], float]:
        """Process a single track: search, match, and cache.
        
        Pipeline:
        1. Check cache for previous match
        2. If not cached:
           a. Try ISRC search (if available)
           b. If no ISRC or ISRC fails, fuzzy search
           c. Match best result
           d. Cache successful match
        3. Return video ID and confidence score
        
        Args:
            spotify_track: Spotify track dict
        
        Returns:
            Tuple of (video_id, confidence_score)
            Returns (None, 0.0) if no match found
        """
        spotify_id = spotify_track.get('id', '')
        track_name = spotify_track.get('name', 'Unknown')
        artists = spotify_track.get('artists', [])
        isrc = spotify_track.get('isrc')
        
        # STEP 1: Check cache first
        cached_match = self.cache_manager.get_cached_match(spotify_id)
        if cached_match:
            logger.debug(f"Cache hit for: {track_name}")
            # Convert confidence back to percentage (0-100) to match search results
            confidence_percentage = cached_match['confidence'] * 100.0
            return cached_match['youtube_video_id'], confidence_percentage
        
        logger.debug(f"Cache miss for: {track_name}, searching YouTube Music...")
        
        # STEP 2: Search YouTube Music
        youtube_results = []
        
        # ISRC lookup is deliberately not attempted. YouTube Music has no isrc:
        # search operator -- the query is treated as literal text and matched
        # nothing for any of the 12 tracks in a real playlist, while doubling the
        # request count. Title and artist search is the only path that works.
        
        if not youtube_results:
            logger.debug(f"Fuzzy searching for: {track_name}")
            youtube_results = self.youtube_searcher.search_track(track_name, artists)
        
        # STEP 3: Match best result
        if not youtube_results:
            logger.warning(f"No YouTube results found for: {track_name}")
            return None, 0.0
        
        video_id, confidence = self.track_matcher.match_track(
            spotify_track,
            youtube_results
        )
        
        # STEP 4: Cache successful match
        if video_id:
            try:
                # Convert confidence from percentage (0-100) to decimal (0.0-1.0)
                confidence_decimal = confidence / 100.0
                self.cache_manager.cache_match(
                    spotify_id=spotify_id,
                    youtube_id=video_id,
                    confidence=confidence_decimal
                )
                logger.debug(f"Cached match for: {track_name}")
            except Exception as e:
                logger.error(f"Failed to cache match for {track_name}: {e}")
                # Don't fail the migration for cache errors
        
        return video_id, confidence
    
    def add_tracks_batch(
        self,
        playlist_id: str,
        video_ids: List[str]
    ) -> None:
        """Add tracks to YouTube Music playlist in batches.
        
        Implements batching to avoid request size limits and rate limiting:
        - Maximum 100 tracks per batch (YouTube Music API limit)
        - 500ms delay between batches
        - Retry on 429 rate limit errors
        - Continue with next batch on other errors
        
        Args:
            playlist_id: YouTube Music playlist ID
            video_ids: List of YouTube video IDs to add
        
        Raises:
            ValueError: If playlist_id is empty or video_ids is empty
        """
        if not playlist_id:
            raise ValueError("playlist_id cannot be empty")
        if not video_ids:
            raise ValueError("video_ids list cannot be empty")
        
        logger.info(f"Adding {len(video_ids)} tracks in batches of {self.BATCH_SIZE}")
        
        # Split into batches
        batches = list(self.chunks(video_ids, self.BATCH_SIZE))
        
        for batch_idx, batch in enumerate(batches, start=1):
            batch_size = len(batch)
            logger.info(f"Processing batch {batch_idx}/{len(batches)} ({batch_size} tracks)")
            
            # Retry logic for this batch
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    # Check rate limiter (blocks if necessary)
                    self.rate_limiter.check_limit()
                    
                    # Add batch to playlist
                    self.ytmusic_client.add_playlist_items(
                        playlistId=playlist_id,
                        videoIds=batch
                    )
                    
                    # Record successful request
                    self.rate_limiter.record_request()
                    
                    logger.info(f"Batch {batch_idx} added successfully")
                    
                    # Delay between batches (except for last batch)
                    if batch_idx < len(batches):
                        time.sleep(self.BATCH_DELAY)
                    
                    # Success - break retry loop
                    break
                
                except YTMusicServerError as e:
                    # Handle 429 rate limit errors
                    if '429' in str(e) or 'rate limit' in str(e).lower():
                        logger.warning(
                            f"429 rate limit on batch {batch_idx}, attempt {attempt + 1}"
                        )
                        self.rate_limiter.handle_429()
                        
                        if attempt < max_retries - 1:
                            logger.info("Retrying batch after rate limit...")
                            continue
                        else:
                            logger.error(f"Max retries exceeded for batch {batch_idx}")
                            # Continue with next batch
                    else:
                        # Other server errors
                        logger.error(
                            f"Server error on batch {batch_idx}: {e}",
                            exc_info=True
                        )
                        if attempt < max_retries - 1:
                            time.sleep(2 ** attempt)  # Exponential backoff
                            continue
                        else:
                            logger.error(f"Skipping batch {batch_idx} after errors")
                
                except Exception as e:
                    # Unexpected errors
                    logger.error(
                        f"Unexpected error on batch {batch_idx}: {e}",
                        exc_info=True
                    )
                    if attempt < max_retries - 1:
                        time.sleep(2 ** attempt)
                        continue
                    else:
                        logger.error(f"Skipping batch {batch_idx} after unexpected errors")
                        break
    
    @staticmethod
    def chunks(lst: List[Any], n: int) -> Generator[List[Any], None, None]:
        """Yield successive n-sized chunks from list.
        
        Args:
            lst: List to chunk
            n: Chunk size
        
        Yields:
            Lists of size n (last chunk may be smaller)
        
        Example:
            >>> list(PlaylistMigrator.chunks([1, 2, 3, 4, 5], 2))
            [[1, 2], [3, 4], [5]]
        """
        for i in range(0, len(lst), n):
            yield lst[i:i + n]
