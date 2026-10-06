"""Playlist migration engine for Spotify to YouTube Music migration.

This module implements the core migration logic, orchestrating search, matching,
caching, and batch addition of tracks to YouTube Music playlists.
"""

import time
import logging
from collections import Counter
from typing import List, Dict, Optional, Callable, Any, Generator

from ytmusicapi import YTMusic
from ytmusicapi.exceptions import YTMusicServerError

from src.searchers.youtube_searcher import YouTubeSearcher
from src.matchers.track_matcher import TrackMatcher
from src.utils.cache_manager import CacheManager
from src.utils.rate_limiter import RateLimiter
from config.app_config import YOUTUBE_PLAYLIST_MAX_ITEMS, INCREMENTAL_FLUSH_SIZE


# Configure logging
logger = logging.getLogger(__name__)


class PlaylistMigrator:
    """Orchestrates migration of Spotify playlists to YouTube Music.

    Implements the complete migration pipeline:
    1. Create (or reuse) the destination YouTube Music playlist(s)
    2. Search and match tracks (with caching)
    3. Flush matched tracks to YouTube as they accumulate (incremental writes)
    4. Spill into a new destination playlist ("shard") every 5,000 items
    5. Generate migration report

    Resume support: every successful write is reported through
    ``state_callback`` (destination playlist ids, total items added, and the
    index of the last source track whose outcome is final). A caller can hand
    that state back in as ``resume_state`` and the migrator continues from the
    next unprocessed track without creating a second playlist.

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

    # Incremental write / sharding configuration (see config/app_config.py)
    FLUSH_SIZE = INCREMENTAL_FLUSH_SIZE
    SHARD_SIZE = YOUTUBE_PLAYLIST_MAX_ITEMS

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
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
        resume_state: Optional[Dict[str, Any]] = None,
        state_callback: Optional[Callable[..., None]] = None
    ) -> Dict[str, Any]:
        """Migrate a Spotify playlist to YouTube Music.
        
        Pipeline:
        1. Reuse the destination playlist(s) from ``resume_state`` or create
           the first one lazily when the first match needs writing
        2. For each Spotify track past the resume point:
           - Check cache for previous match, else search + fuzzy match
           - Cache successful match, queue the video id for writing
           - Report progress
           - Once FLUSH_SIZE matches are queued, write them to YouTube
             (spilling into a new shard at SHARD_SIZE items) and report the
             new durable state through ``state_callback``
        3. Flush whatever is left, then build the report
        
        Args:
            playlist_name: Name for the YouTube Music playlist. Playlists with
                more than SHARD_SIZE source tracks are written to several
                destination playlists named "<name> (1)", "<name> (2)", ...
            tracks: List of Spotify track dicts with keys:
                - name: Track name (str)
                - artists: Artist names (List[str])
                - album: Album name (str)
                - duration_ms: Duration in milliseconds (int)
                - id: Spotify track ID (str)
            progress_callback: Optional callback called after each track is
                processed: callback(current, total, track_name, matched, failed)
                (a 3-argument callback is also accepted).
            resume_state: Optional dict previously emitted via state_callback:
                - youtube_playlist_ids (List[str]): shard ids already created
                - added_tracks (int): items already written across all shards
                - last_added_index (int): number of leading source tracks whose
                  outcome is already final (they are skipped)
                - matched_tracks / failed_tracks (int): prior counters
            state_callback: Optional callback invoked with keyword arguments
                (youtube_playlist_ids, added_tracks, last_added_index,
                matched_tracks, failed_tracks) after every durable write.
        
        Returns:
            Migration report dict with keys:
            - playlist_name: str
            - playlist_url: str (URL of the first destination playlist)
            - playlist_urls: List[str] (one per shard)
            - playlist_ids: List[str] (one per shard)
            - shard_count: int
            - total_tracks: int (whole job, including resumed-over tracks)
            - matched_tracks: int (whole job)
            - failed_tracks: List[dict] with {spotify_track, reason} (this run)
            - failed_count: int (whole job)
            - resumed_from: int (0 when not a resume)
            - success_rate: float (percentage)
            - match_scores: List[float] (confidence scores, this run)
            - duration_seconds: float (time taken)
        
        Raises:
            ValueError: If playlist_name is empty or tracks list is empty
            RuntimeError: If the destination playlist cannot be created
        """
        # Validation
        if not playlist_name:
            raise ValueError("playlist_name cannot be empty")
        if not tracks:
            raise ValueError("tracks list cannot be empty")
        
        start_time = time.time()
        total_tracks = len(tracks)
        
        # Durable state (seeded from a previous run when resuming)
        resume_state = resume_state or {}
        shard_ids: List[str] = list(resume_state.get('youtube_playlist_ids') or [])
        added_total = int(resume_state.get('added_tracks') or 0)
        start_index = int(resume_state.get('last_added_index') or 0)
        prior_matched = int(resume_state.get('matched_tracks') or 0)
        prior_failed = int(resume_state.get('failed_tracks') or 0)
        
        if start_index < 0:
            start_index = 0
        if start_index > total_tracks:
            start_index = total_tracks
        
        if start_index:
            logger.info(
                f"Resuming migration for playlist: {playlist_name} "
                f"({start_index}/{total_tracks} tracks already final, "
                f"{added_total} items already on YouTube in {len(shard_ids)} playlist(s))"
            )
        else:
            logger.info(f"Starting migration for playlist: {playlist_name} ({total_tracks} tracks)")
        
        # Per-run report data
        match_scores: List[float] = []
        failed_tracks: List[Dict[str, Any]] = []
        matched_count = 0
        
        # Matches waiting to be written: list of {'track', 'video_id', 'confidence'}
        pending: List[Dict[str, Any]] = []
        # Source index up to which every track's outcome is durable on YouTube
        final_index = start_index
        
        def emit_state(last_index: int) -> None:
            if not state_callback:
                return
            try:
                state_callback(
                    youtube_playlist_ids=list(shard_ids),
                    added_tracks=added_total,
                    last_added_index=last_index,
                    matched_tracks=prior_matched + matched_count,
                    failed_tracks=prior_failed + len(failed_tracks)
                )
            except Exception as e:
                logger.error(f"State callback error: {e}", exc_info=True)
        
        def ensure_shard(shard_index: int) -> str:
            """Return the destination playlist id for shard_index, creating
            any missing shards (and recording them) on the way."""
            nonlocal shard_ids
            while len(shard_ids) <= shard_index:
                name = self._shard_name(playlist_name, len(shard_ids), total_tracks)
                try:
                    new_id = self._create_youtube_playlist(name)
                except Exception as e:
                    logger.error(f"Failed to create YouTube Music playlist: {e}", exc_info=True)
                    raise RuntimeError(f"Failed to create playlist: {e}") from e
                shard_ids.append(new_id)
                logger.info(f"Created YouTube Music playlist '{name}': {new_id}")
                # Persist the id immediately so a crash between create and the
                # first add does not produce a duplicate playlist on resume.
                emit_state(final_index)
            return shard_ids[shard_index]
        
        def flush(upto_index: int) -> None:
            """Write every pending match to YouTube, spilling across shards,
            then record that all source tracks up to upto_index are final."""
            nonlocal added_total, matched_count, final_index
            while pending:
                shard_index = added_total // self.SHARD_SIZE
                room = self.SHARD_SIZE - (added_total % self.SHARD_SIZE)
                chunk = pending[:min(room, len(pending), self.BATCH_SIZE)]
                del pending[:len(chunk)]
                
                shard_id = ensure_shard(shard_index)
                video_ids = [item['video_id'] for item in chunk]
                added_list = self.add_tracks_batch(shard_id, video_ids)
                # Two source tracks may match the same video; count per occurrence
                remaining = Counter(added_list)
                
                for item in chunk:
                    if remaining[item['video_id']] > 0:
                        remaining[item['video_id']] -= 1
                        matched_count += 1
                        match_scores.append(item['confidence'])
                    else:
                        failed_tracks.append({
                            'spotify_track': item['track'],
                            'reason': 'Failed to add to YouTube Music playlist'
                        })
                added_total += len(added_list)
            
            final_index = upto_index
            emit_state(final_index)
        
        # Make sure the first destination playlist exists up front (matches the
        # previous behaviour and surfaces auth problems before any searching).
        if not shard_ids:
            ensure_shard(0)
        
        # Process each track past the resume point
        for idx in range(start_index + 1, total_tracks + 1):
            spotify_track = tracks[idx - 1]
            track_name = spotify_track.get('name', 'Unknown Track')
            
            try:
                video_id, confidence = self._process_track(spotify_track)
                logger.debug(f"[{idx}/{total_tracks}] _process_track returned: video_id={video_id}, confidence={confidence}")
                
                if video_id:
                    pending.append({'track': spotify_track, 'video_id': video_id, 'confidence': confidence})
                    logger.info(
                        f"[{idx}/{total_tracks}] Matched: {track_name} "
                        f"(confidence: {confidence:.1f}%)"
                    )
                else:
                    failed_tracks.append({
                        'spotify_track': spotify_track,
                        'reason': 'No match found above threshold'
                    })
                    logger.warning(f"[{idx}/{total_tracks}] No match: {track_name}")
            
            except Exception as e:
                failed_tracks.append({
                    'spotify_track': spotify_track,
                    'reason': f'Error: {str(e)}'
                })
                logger.error(
                    f"[{idx}/{total_tracks}] EXCEPTION processing {track_name}: {type(e).__name__}: {e}",
                    exc_info=True
                )
            
            # Report progress with whole-job match/fail counts
            if progress_callback:
                try:
                    matched_so_far = prior_matched + matched_count + len(pending)
                    failed_so_far = prior_failed + len(failed_tracks)
                    progress_callback(idx, total_tracks, track_name, matched_so_far, failed_so_far)
                except TypeError:
                    # Fallback for old callback signature (3 params)
                    try:
                        progress_callback(idx, total_tracks, track_name)
                    except Exception as e:
                        logger.error(f"Progress callback error: {e}", exc_info=True)
                except Exception as e:
                    logger.error(f"Progress callback error: {e}", exc_info=True)
            
            # Incremental write: flush as soon as enough matches have accumulated
            if len(pending) >= self.FLUSH_SIZE:
                logger.info(f"Flushing {len(pending)} matched tracks to YouTube Music...")
                flush(idx)
        
        # Final flush of whatever is left
        if pending:
            logger.info(f"Adding final {len(pending)} matched tracks to YouTube Music...")
        flush(total_tracks)
        
        # Statistics for the whole job (prior runs + this run)
        job_matched = prior_matched + matched_count
        job_failed = prior_failed + len(failed_tracks)
        success_rate = (job_matched / total_tracks * 100) if total_tracks > 0 else 0
        duration = time.time() - start_time
        
        report = {
            'playlist_name': playlist_name,
            'playlist_url': self.PLAYLIST_URL_TEMPLATE.format(shard_ids[0]) if shard_ids else '',
            'playlist_urls': [self.PLAYLIST_URL_TEMPLATE.format(pid) for pid in shard_ids],
            'playlist_ids': list(shard_ids),
            'shard_count': len(shard_ids),
            'total_tracks': total_tracks,
            'matched_tracks': job_matched,
            'failed_tracks': failed_tracks,
            'failed_count': job_failed,
            'resumed_from': start_index,
            'success_rate': success_rate,
            'match_scores': match_scores,
            'duration_seconds': duration
        }
        
        logger.info(
            f"Migration complete: {job_matched}/{total_tracks} tracks "
            f"({success_rate:.1f}%) across {len(shard_ids)} playlist(s) in {duration:.1f}s"
        )
        
        return report
    
    def _shard_name(self, playlist_name: str, shard_index: int, total_tracks: int) -> str:
        """Name for destination shard ``shard_index`` (0-based).
        
        A playlist that fits in one YouTube playlist keeps its own name. One
        that cannot gets numbered shards from the start, so the names are
        stable across a resume regardless of how many matches succeed.
        """
        if total_tracks <= self.SHARD_SIZE and shard_index == 0:
            return playlist_name
        return f"{playlist_name} ({shard_index + 1})"
    
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
    ) -> List[str]:
        """Add tracks to YouTube Music playlist in batches.
        
        Implements batching to avoid request size limits and rate limiting:
        - Maximum 100 tracks per batch (YouTube Music API limit)
        - 500ms delay between batches
        - Retry on 429 rate limit errors
        - Continue with next batch on other errors
        
        Args:
            playlist_id: YouTube Music playlist ID
            video_ids: List of YouTube video IDs to add
        
        Returns:
            The video IDs that were actually written (a batch that exhausted
            its retries is left out), so callers can record durable progress.
        
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
        added: List[str] = []
        
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
                    added.extend(batch)
                    
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
        
        return added
    
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
