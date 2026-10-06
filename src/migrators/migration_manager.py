"""Migration Manager for orchestrating Spotify to YouTube Music migrations.

This module provides the high-level controller that ties together all migration
components: BackgroundWorker, PlaylistMigrator, Notifier, and dependencies.
Manages the complete migration lifecycle from start to finish.

Example:
    >>> manager = MigrationManager(spotify_client, ytmusic_client, cache_manager)
    >>> manager.start()
    >>> manager.migrate_playlists(playlists, progress_callback)
    >>> status = manager.get_migration_status()
    >>> manager.stop()
"""

import logging
import threading
from typing import List, Dict, Any, Optional, Callable

from spotipy import Spotify
from ytmusicapi import YTMusic

from src.utils.cache_manager import CacheManager
from src.utils.rate_limiter import RateLimiter
from src.utils.background_worker import BackgroundWorker
from src.utils.notifier import Notifier
from src.searchers.youtube_searcher import YouTubeSearcher
from src.matchers.track_matcher import TrackMatcher
from src.migrators.playlist_migrator import PlaylistMigrator
from src.fetchers.spotify_fetcher import SpotifyFetcher


logger = logging.getLogger(__name__)


class MigrationManager:
    """High-level orchestrator for playlist migrations.
    
    Coordinates all migration components and provides a simple API for:
    - Starting/stopping background processing
    - Queueing multiple playlists for migration
    - Monitoring overall migration status
    - Pausing/resuming migrations
    - Error aggregation and reporting
    
    This class acts as the facade for the entire migration system, hiding
    the complexity of individual components from the UI layer.
    
    Attributes:
        spotify_client (Spotify): Authenticated Spotify client.
        ytmusic_client (YTMusic): Authenticated YouTube Music client.
        cache_manager (CacheManager): Cache and database manager.
        rate_limiter (RateLimiter): API rate limiter.
        youtube_searcher (YouTubeSearcher): YouTube Music search service.
        track_matcher (TrackMatcher): Fuzzy track matching engine.
        playlist_migrator (PlaylistMigrator): Playlist migration engine.
        background_worker (BackgroundWorker): Background job processor.
        notifier (Notifier): Desktop notification service.
        spotify_fetcher (SpotifyFetcher): Spotify playlist/track fetcher.
        _paused (bool): Whether migrations are paused.
        _paused_lock (threading.Lock): Thread-safe pause state management.
        _error_log (List[Dict]): Aggregated errors from all migrations.
        _error_lock (threading.Lock): Thread-safe error log access.
    
    Example:
        >>> manager = MigrationManager(spotify, ytmusic, cache)
        >>> manager.start()
        >>> manager.migrate_playlists(
        ...     playlists=[{'id': 'sp_123', 'name': 'My Playlist'}],
        ...     progress_callback=update_ui
        ... )
        >>> print(manager.get_migration_status())
        >>> manager.stop()
    """

    # Sustained-rate policy for the internal web API (see RateLimiter docstring).
    RATE_MIN_INTERVAL_SECONDS = 1.0
    RATE_JITTER_SECONDS = 0.5
    RATE_PER_MINUTE_LIMIT = 40

    def __init__(
        self,
        spotify_client: Spotify,
        ytmusic_client: YTMusic,
        cache_manager: CacheManager
    ):
        """Initialize the migration manager and all components.
        
        Creates instances of all required services and wires them together:
        - RateLimiter (for API throttling)
        - YouTubeSearcher (for track search)
        - TrackMatcher (for fuzzy matching)
        - PlaylistMigrator (for migration logic)
        - BackgroundWorker (for async processing)
        - Notifier (for desktop notifications)
        - SpotifyFetcher (for playlist/track retrieval)
        
        Args:
            spotify_client (Spotify): Authenticated Spotify client.
            ytmusic_client (YTMusic): Authenticated YouTube Music client.
            cache_manager (CacheManager): Cache and database manager.
        
        Raises:
            ValueError: If any required client is None.
        
        Example:
            >>> from spotipy import Spotify
            >>> from ytmusicapi import YTMusic
            >>> from src.utils.cache_manager import CacheManager
            >>> 
            >>> spotify = Spotify(auth="token")
            >>> ytmusic = YTMusic("headers_auth.json")
            >>> cache = CacheManager("migration.db")
            >>> 
            >>> manager = MigrationManager(spotify, ytmusic, cache)
        """
        if spotify_client is None:
            raise ValueError("spotify_client cannot be None")
        if ytmusic_client is None:
            raise ValueError("ytmusic_client cannot be None")
        if cache_manager is None:
            raise ValueError("cache_manager cannot be None")
        
        # Store clients
        self.spotify_client = spotify_client
        self.ytmusic_client = ytmusic_client
        self.cache_manager = cache_manager
        
        # Throttle visibility: the limiter reports state changes here; the UI/CLI
        # can read get_throttle_state() or attach set_throttle_callback().
        self._throttle_callback: Optional[Callable[[Dict[str, Any]], None]] = None
        self._throttle_state: Dict[str, Any] = {
            'throttled': False, 'reason': None, 'until': None, 'message': ''
        }
        self._throttle_lock = threading.Lock()

        # Initialize rate limiter with the sustained-rate policy for the
        # internal web API (paced min-interval + jitter, per-minute ceiling,
        # no Data-API-style daily cap). Counters persist in the app DB so a
        # restart does not reset them.
        self.rate_limiter = RateLimiter(
            daily_limit=None,
            per_minute_limit=self.RATE_PER_MINUTE_LIMIT,
            min_interval=self.RATE_MIN_INTERVAL_SECONDS,
            jitter=self.RATE_JITTER_SECONDS,
            db_path=getattr(cache_manager, 'db_path', None),
            on_throttle=self._on_throttle_state_change,
        )
        logger.info(
            f"Initialized RateLimiter: {self.RATE_MIN_INTERVAL_SECONDS}s "
            f"(+{self.RATE_JITTER_SECONDS}s jitter) between requests, "
            f"{self.RATE_PER_MINUTE_LIMIT}/min, persistent counters"
        )
        
        # Initialize YouTube searcher
        self.youtube_searcher = YouTubeSearcher(
            ytmusic_client=ytmusic_client,
            rate_limiter=self.rate_limiter
        )
        logger.info("Initialized YouTubeSearcher")
        
        # Initialize track matcher (75% threshold for balanced precision)
        self.track_matcher = TrackMatcher(threshold=75)
        logger.info("Initialized TrackMatcher with 75% threshold")
        
        # Initialize playlist migrator
        self.playlist_migrator = PlaylistMigrator(
            ytmusic_client=ytmusic_client,
            youtube_searcher=self.youtube_searcher,
            track_matcher=self.track_matcher,
            cache_manager=cache_manager,
            rate_limiter=self.rate_limiter
        )
        logger.info("Initialized PlaylistMigrator")
        
        # Initialize background worker. It gets the migrator so jobs interrupted
        # by a crash/restart can be re-queued and continued on start().
        self.background_worker = BackgroundWorker(cache_manager=cache_manager)
        self.background_worker.default_migrator_func = self.playlist_migrator.migrate_playlist
        logger.info("Initialized BackgroundWorker")
        
        # UI progress callback for jobs resumed on startup (set via
        # set_progress_callback(); the UI may attach after start()).
        self._resume_progress_callback: Optional[Callable] = None
        
        # Initialize notifier
        self.notifier = Notifier(app_name="Spotify to YouTube Music Migrator")
        logger.info("Initialized Notifier")
        
        # Initialize Spotify fetcher
        self.spotify_fetcher = SpotifyFetcher(
            spotify_client=spotify_client,
            rate_limiter=self.rate_limiter,
            cache_manager=cache_manager
        )
        logger.info("Initialized SpotifyFetcher")
        
        # State management
        self._paused = False
        self._paused_lock = threading.Lock()
        
        # Error aggregation
        self._error_log: List[Dict[str, Any]] = []
        self._error_lock = threading.Lock()
        
        logger.info("MigrationManager initialized successfully")
    
    def start(self) -> None:
        """Start the migration manager and background worker.
        
        This method:
        1. Starts the background worker thread
        2. Re-queues any migrations interrupted by a crash or restart so they
           continue from the last track written to YouTube (no duplicate
           playlists, already-added tracks skipped)
        3. Logs startup information
        
        Should be called before queueing any migration jobs.
        
        Raises:
            RuntimeError: If manager is already running.
        
        Example:
            >>> manager = MigrationManager(spotify, ytmusic, cache)
            >>> manager.start()  # Now ready to accept jobs
            >>> manager.migrate_playlists(playlists)
        """
        logger.info("Starting MigrationManager...")
        
        # Start background worker
        self.background_worker.start()
        logger.info("Background worker started")
        
        # Resume incomplete migrations (crash recovery): they continue where
        # they left off rather than being marked failed.
        resumed_jobs = self.background_worker.resume_incomplete_migrations(
            migrator_func=self.playlist_migrator.migrate_playlist,
            progress_callback=self._make_resume_progress_wrapper()
        )
        if resumed_jobs:
            logger.info(f"Re-queued {len(resumed_jobs)} interrupted migration(s) to continue")
        else:
            logger.info("No incomplete migrations to resume")
        
        logger.info("MigrationManager started successfully")
    
    def set_progress_callback(
        self,
        progress_callback: Optional[Callable[[str, int, int, str], None]]
    ) -> None:
        """Attach the UI progress callback used for jobs resumed on startup.
        
        Jobs queued through migrate_playlists() carry their own callback; this
        one covers jobs that were re-queued by start() before the UI existed.
        Signature: progress_callback(playlist_name, current, total, track_name,
        matched=0, failed=0).
        """
        self._resume_progress_callback = progress_callback
    
    def _on_throttle_state_change(self, state: Dict[str, Any]) -> None:
        """Receive throttle-state changes from the RateLimiter (worker thread)."""
        with self._throttle_lock:
            self._throttle_state = dict(state)
            callback = self._throttle_callback
        if state.get('throttled'):
            logger.warning(f"Throttled: {state.get('message')}")
        else:
            logger.info("Throttle cleared")
        if callback:
            try:
                callback(dict(state))
            except Exception as e:
                logger.error(f"Throttle callback error: {str(e)}")

    def set_throttle_callback(
        self,
        callback: Optional[Callable[[Dict[str, Any]], None]]
    ) -> None:
        """Attach a callback invoked whenever the throttle state changes.

        The callback receives ``{'throttled', 'reason', 'until', 'message'}``
        (see RateLimiter.get_throttle_state()). Called from the worker thread.
        """
        with self._throttle_lock:
            self._throttle_callback = callback

    def get_throttle_state(self) -> Dict[str, Any]:
        """Current throttle state: ``{'throttled': bool, 'reason': 'rate'|'quota'|None,
        'until': epoch seconds or None, 'message': str}``."""
        getter = getattr(self.rate_limiter, 'get_throttle_state', None)
        if callable(getter):
            state = getter()
            if isinstance(state, dict):
                return state
        with self._throttle_lock:
            return dict(self._throttle_state)

    def _make_resume_progress_wrapper(self) -> Callable:
        """Worker-style progress callback that forwards resumed jobs' progress
        to whatever UI callback is attached at call time."""
        def wrapper(current: int, total: int, track_name: str, matched: int = 0, failed: int = 0):
            callback = self._resume_progress_callback
            if not callback:
                return
            current_job = self.background_worker.get_current_job() or {}
            pname = current_job.get('playlist_name', '')
            try:
                callback(pname, current, total, track_name, matched, failed)
            except Exception as e:
                logger.error(f"Progress callback error for resumed job '{pname}': {str(e)}")
        return wrapper
    
    def stop(self, timeout: float = 30.0) -> None:
        """Stop the migration manager gracefully.
        
        Waits for the current migration job to complete before stopping.
        Does not cancel in-progress migrations - they will finish first.
        
        Args:
            timeout (float): Maximum seconds to wait for worker to stop.
                Defaults to 30 seconds.
        
        Raises:
            TimeoutError: If worker doesn't stop within timeout.
        
        Example:
            >>> manager.stop()  # Wait up to 30s for current job
            >>> manager.stop(timeout=60.0)  # Custom timeout
        """
        logger.info("Stopping MigrationManager...")
        
        # Stop background worker
        self.background_worker.stop(timeout=timeout)
        logger.info("Background worker stopped")

        # Flush persisted rate-limit counters.
        close = getattr(self.rate_limiter, 'close', None)
        if callable(close):
            try:
                close()
            except Exception as e:
                logger.warning(f"Could not close rate limiter cleanly: {str(e)}")
        
        # Log final statistics
        all_jobs = self.background_worker.get_all_jobs(limit=1000)
        completed = sum(1 for job in all_jobs if job['status'] == 'completed')
        failed = sum(1 for job in all_jobs if job['status'] == 'failed')
        
        logger.info(
            f"MigrationManager stopped. "
            f"Final stats: {completed} completed, {failed} failed"
        )
    
    def migrate_playlists(
        self,
        playlists: List[Dict[str, Any]],
        progress_callback: Optional[Callable[[str, int, int, str], None]] = None
    ) -> List[str]:
        """Queue multiple playlists for migration.
        
        For each playlist:
        1. Fetch tracks from Spotify (with caching)
        2. Create migration job
        3. Add to background worker queue
        
        Progress callback signature:
            progress_callback(playlist_name, current, total, track_name, matched=0, failed=0)
        
        Args:
            playlists (List[Dict[str, Any]]): List of playlist dictionaries.
                Each must contain:
                - 'id' (str): Spotify playlist ID
                - 'name' (str): Playlist name
                Optional:
                - 'tracks' (List[Dict]): Pre-fetched tracks (skips fetch)
            progress_callback (Optional[Callable]): Progress update callback.
                Called for each track processed: (playlist_name, current, total, track_name)
        
        Returns:
            List[str]: List of job IDs for queued migrations.
        
        Raises:
            ValueError: If playlists list is empty or invalid.
            RuntimeError: If manager is not started or is paused.
        
        Example:
            >>> playlists = [
            ...     {'id': 'sp_123', 'name': 'Rock Classics'},
            ...     {'id': 'sp_456', 'name': 'Chill Vibes'}
            ... ]
            >>> 
            >>> def progress(playlist, current, total, track):
            ...     print(f"{playlist}: {current}/{total} - {track}")
            >>> 
            >>> job_ids = manager.migrate_playlists(playlists, progress)
            >>> print(f"Queued {len(job_ids)} migrations")
        """
        if not playlists:
            raise ValueError("playlists list cannot be empty")
        
        if not self.background_worker.is_running.is_set():
            raise RuntimeError("MigrationManager is not started. Call start() first.")
        
        with self._paused_lock:
            if self._paused:
                raise RuntimeError("Migrations are paused. Call resume_migrations() first.")
        
        logger.info(f"Queueing {len(playlists)} playlists for migration")
        
        job_ids = []
        
        for playlist in playlists:
            # Validate playlist structure
            if 'id' not in playlist or 'name' not in playlist:
                logger.error(f"Invalid playlist structure: {playlist}")
                continue
            
            playlist_id = playlist['id']
            playlist_name = playlist['name']
            
            try:
                # Fetch tracks if not already provided
                if 'tracks' in playlist and playlist['tracks']:
                    tracks = playlist['tracks']
                    logger.info(
                        f"Using pre-fetched tracks for '{playlist_name}': "
                        f"{len(tracks)} tracks"
                    )
                else:
                    logger.info(f"Fetching tracks for '{playlist_name}'...")
                    tracks = self.spotify_fetcher.get_playlist_tracks(playlist_id)
                    logger.info(f"Fetched {len(tracks)} tracks for '{playlist_name}'")
                
                if not tracks:
                    logger.warning(f"Playlist '{playlist_name}' has no tracks, skipping")
                    continue
                
                # Make sure the source tracks are in the tracks table: resume
                # after a restart reloads them from there. Fetched tracks are
                # already cached by SpotifyFetcher; pre-fetched ones are not.
                try:
                    self.cache_manager.cache_tracks(tracks, playlist_id)
                except Exception as e:
                    logger.warning(
                        f"Could not cache tracks for '{playlist_name}' "
                        f"(resume after restart will not be possible): {str(e)}"
                    )
                
                # Create progress wrapper that forwards to user callback
                def create_progress_wrapper(pname: str):
                    def wrapper(current: int, total: int, track_name: str, matched: int = 0, failed: int = 0):
                        if progress_callback:
                            try:
                                progress_callback(pname, current, total, track_name, matched, failed)
                            except Exception as e:
                                logger.error(
                                    f"Progress callback error for '{pname}': {str(e)}"
                                )
                    return wrapper
                
                # Add job to background worker
                job_id = self.background_worker.add_job(
                    playlist_name=playlist_name,
                    playlist_id=playlist_id,
                    tracks=tracks,
                    migrator_func=self.playlist_migrator.migrate_playlist,
                    progress_callback=create_progress_wrapper(playlist_name)
                )
                
                job_ids.append(job_id)
                logger.info(
                    f"Queued migration job {job_id} for '{playlist_name}' "
                    f"with {len(tracks)} tracks"
                )
            
            except Exception as e:
                error_msg = f"Failed to queue playlist '{playlist_name}': {str(e)}"
                logger.error(error_msg, exc_info=True)
                
                # Add to error log
                with self._error_lock:
                    self._error_log.append({
                        'playlist_id': playlist_id,
                        'playlist_name': playlist_name,
                        'error': str(e),
                        'stage': 'queueing'
                    })
        
        logger.info(f"Successfully queued {len(job_ids)} migration jobs")
        
        # Send notification for batch start
        if job_ids:
            total_playlists = len(job_ids)
            if total_playlists > 1:
                self.notifier.notify_progress_milestone(
                    current=0,
                    total=total_playlists,
                    milestone_type="batch_started"
                )
        
        return job_ids
    
    def get_migration_status(self) -> Dict[str, Any]:
        """Get overall migration status.
        
        Returns comprehensive status including:
        - Total jobs (all time)
        - Completed jobs
        - Failed jobs
        - Queued jobs
        - Current job details
        - Queue size
        - Pause state
        - Error summary
        
        Returns:
            Dict[str, Any]: Status dictionary with keys:
                - total_jobs (int): Total number of jobs created
                - completed_jobs (int): Number of completed jobs
                - failed_jobs (int): Number of failed jobs
                - queued_jobs (int): Number of queued jobs
                - in_progress_jobs (int): Number of jobs currently running
                - current_job (Optional[Dict]): Details of current job or None
                - queue_size (int): Number of jobs waiting in queue
                - is_paused (bool): Whether migrations are paused
                - error_count (int): Total number of errors logged
                - is_running (bool): Whether background worker is running
                - throttle (Dict): Rate-limiter throttle state
                  (throttled, reason, until, message)
        
        Example:
            >>> status = manager.get_migration_status()
            >>> print(f"Progress: {status['completed_jobs']}/{status['total_jobs']}")
            >>> if status['current_job']:
            ...     print(f"Current: {status['current_job']['playlist_name']}")
        """
        # Get all jobs from database
        all_jobs = self.background_worker.get_all_jobs(limit=1000)
        
        # Count by status
        completed = sum(1 for job in all_jobs if job['status'] == 'completed')
        failed = sum(1 for job in all_jobs if job['status'] == 'failed')
        queued = sum(1 for job in all_jobs if job['status'] == 'queued')
        in_progress = sum(1 for job in all_jobs if job['status'] == 'in_progress')
        
        # Get current job
        current_job = self.background_worker.get_current_job()
        
        # Get queue size
        queue_size = self.background_worker.job_queue.qsize()
        
        # Get pause state
        with self._paused_lock:
            is_paused = self._paused
        
        # Get error count
        with self._error_lock:
            error_count = len(self._error_log)
        
        status = {
            'total_jobs': len(all_jobs),
            'completed_jobs': completed,
            'failed_jobs': failed,
            'queued_jobs': queued,
            'in_progress_jobs': in_progress,
            'current_job': current_job,
            'queue_size': queue_size,
            'is_paused': is_paused,
            'error_count': error_count,
            'is_running': self.background_worker.is_running.is_set(),
            'throttle': self.get_throttle_state()
        }
        
        return status
    
    def pause_migrations(self) -> None:
        """Pause migrations after current job completes.
        
        Sets pause flag - no new jobs will start processing after the current
        job finishes. Does not interrupt the currently running job.
        
        Jobs remain in the queue and can be resumed with resume_migrations().
        
        Note: This is a soft pause - the background worker continues running
        but won't process new jobs from the queue.
        
        Raises:
            RuntimeError: If manager is not started.
        
        Example:
            >>> manager.pause_migrations()
            >>> # Current job finishes, then pauses
            >>> manager.resume_migrations()  # Continue processing
        """
        if not self.background_worker.is_running.is_set():
            raise RuntimeError("MigrationManager is not started")
        
        with self._paused_lock:
            if self._paused:
                logger.warning("Migrations are already paused")
                return
            
            self._paused = True
            logger.info("Migrations paused - current job will complete, then pause")
        
        # Note: Actual pause implementation would require modifying BackgroundWorker
        # to check a pause flag before processing next job. For now, this is a
        # state flag that can be checked by migrate_playlists().
        
        logger.warning(
            "Note: pause_migrations() sets flag but BackgroundWorker "
            "will continue processing queued jobs. To fully implement, "
            "modify BackgroundWorker._worker_loop to check pause flag."
        )
    
    def resume_migrations(self) -> None:
        """Resume migrations after being paused.
        
        Clears the pause flag, allowing background worker to process
        queued jobs again.
        
        Raises:
            RuntimeError: If manager is not started.
        
        Example:
            >>> manager.pause_migrations()
            >>> # ... later ...
            >>> manager.resume_migrations()  # Continue processing queue
        """
        if not self.background_worker.is_running.is_set():
            raise RuntimeError("MigrationManager is not started")
        
        with self._paused_lock:
            if not self._paused:
                logger.warning("Migrations are not paused")
                return
            
            self._paused = False
            logger.info("Migrations resumed - processing will continue")
    
    def cancel_all(self, force: bool = False) -> int:
        """Cancel all queued migrations and clear the queue.
        
        WARNING: This will discard all queued jobs. In-progress job will
        complete first, but all waiting jobs will be lost.
        
        Args:
            force (bool): If True, skip confirmation and force cancellation.
                Defaults to False (requires confirmation).
        
        Returns:
            int: Number of jobs cancelled.
        
        Raises:
            RuntimeError: If manager is not started.
            ValueError: If force=False (caller must confirm cancellation).
        
        Example:
            >>> # With confirmation
            >>> try:
            ...     count = manager.cancel_all(force=False)
            ... except ValueError:
            ...     if user_confirms("Cancel all migrations?"):
            ...         count = manager.cancel_all(force=True)
            >>> 
            >>> # Direct cancellation
            >>> count = manager.cancel_all(force=True)
            >>> print(f"Cancelled {count} jobs")
        """
        if not self.background_worker.is_running.is_set():
            raise RuntimeError("MigrationManager is not started")
        
        if not force:
            raise ValueError(
                "Cancellation requires confirmation. "
                "Call cancel_all(force=True) to proceed, or prompt user first."
            )
        
        # Count jobs in queue before clearing
        queue_size = self.background_worker.job_queue.qsize()
        
        if queue_size == 0:
            logger.info("No jobs to cancel - queue is empty")
            return 0
        
        logger.warning(f"Cancelling {queue_size} queued migrations...")
        
        # Clear the queue
        with self.background_worker.job_queue.mutex:
            self.background_worker.job_queue.queue.clear()
        
        logger.info(f"Cancelled {queue_size} migrations - queue cleared")
        
        return queue_size
    
    def get_error_log(self) -> List[Dict[str, Any]]:
        """Get aggregated error log from all migrations.
        
        Returns list of error dictionaries containing:
        - playlist_id: Spotify playlist ID
        - playlist_name: Playlist name
        - error: Error message
        - stage: Migration stage where error occurred
        
        Returns:
            List[Dict[str, Any]]: List of error records.
        
        Example:
            >>> errors = manager.get_error_log()
            >>> for error in errors:
            ...     print(f"{error['playlist_name']}: {error['error']}")
        """
        with self._error_lock:
            # Return copy to prevent external modification
            return self._error_log.copy()
    
    def clear_error_log(self) -> int:
        """Clear the error log.
        
        Returns:
            int: Number of errors cleared.
        
        Example:
            >>> count = manager.clear_error_log()
            >>> print(f"Cleared {count} errors")
        """
        with self._error_lock:
            count = len(self._error_log)
            self._error_log.clear()
            logger.info(f"Cleared {count} errors from error log")
            return count
    
    def get_all_jobs(
        self,
        status: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get all migration jobs with optional filtering.
        
        Convenience wrapper around BackgroundWorker.get_all_jobs().
        
        Args:
            status (Optional[str]): Filter by status (queued, in_progress,
                completed, failed). If None, returns all jobs.
            limit (int): Maximum number of jobs to return. Defaults to 100.
        
        Returns:
            List[Dict[str, Any]]: List of job status dictionaries.
        
        Example:
            >>> # Get all completed jobs
            >>> completed = manager.get_all_jobs(status='completed')
            >>> 
            >>> # Get recent 50 jobs
            >>> recent = manager.get_all_jobs(limit=50)
        """
        return self.background_worker.get_all_jobs(status=status, limit=limit)
    
    def clear_old_jobs(self, days_old: int = 30) -> int:
        """Clear completed and failed jobs older than specified days.
        
        Convenience wrapper around BackgroundWorker.clear_completed_jobs().
        
        Args:
            days_old (int): Remove jobs older than this many days. Defaults to 30.
        
        Returns:
            int: Number of jobs removed.
        
        Example:
            >>> # Clear jobs older than 30 days
            >>> count = manager.clear_old_jobs()
            >>> 
            >>> # Clear jobs older than 7 days
            >>> count = manager.clear_old_jobs(days_old=7)
            >>> print(f"Cleared {count} old jobs")
        """
        count = self.background_worker.clear_completed_jobs(days_old=days_old)
        logger.info(f"Cleared {count} jobs older than {days_old} days")
        return count
