"""Background worker for processing playlist migrations asynchronously.

This module provides a thread-safe worker using the producer-consumer pattern
for handling playlist migrations in the background without blocking the UI.
Supports crash recovery by persisting job state to database.

Example:
    >>> worker = BackgroundWorker(cache_manager)
    >>> worker.start()
    >>> job_id = worker.add_job(
    ...     playlist_name="My Playlist",
    ...     playlist_id="sp_123",
    ...     tracks=spotify_tracks,
    ...     migrator_func=migrator.migrate_playlist,
    ...     progress_callback=update_ui
    ... )
    >>> worker.stop()
"""

import inspect
import json
import queue
import threading
import logging
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any, Callable
import sqlite3

from src.utils.cache_manager import CacheManager
from src.utils.errors import YouTubeAuthError
from src.utils.notifier import Notifier

logger = logging.getLogger(__name__)


class BackgroundWorker:
    """Thread-safe background worker for playlist migrations.
    
    Uses producer-consumer pattern with a job queue and daemon worker thread.
    Persists job state to database for crash recovery.
    
    Attributes:
        cache_manager (CacheManager): Database manager for persistence.
        job_queue (queue.Queue): Thread-safe FIFO queue for jobs.
        worker_thread (threading.Thread): Daemon thread processing jobs.
        is_running (threading.Event): Atomic flag for worker state.
        current_job (Optional[dict]): Currently executing job.
        current_job_lock (threading.Lock): Protects current_job access.
    """
    
    def __init__(self, cache_manager: CacheManager):
        """Initialize the background worker.
        
        Args:
            cache_manager (CacheManager): Database manager for job persistence.
        """
        self.cache_manager = cache_manager
        self.db_path = cache_manager.db_path  # Store path for thread-safe connections
        self.job_queue: queue.Queue = queue.Queue()
        self.worker_thread: Optional[threading.Thread] = None
        self.is_running = threading.Event()
        self.current_job: Optional[Dict[str, Any]] = None
        self.current_job_lock = threading.Lock()
        self._worker_connection: Optional[sqlite3.Connection] = None  # Thread-local connection
        self.notifier = Notifier(app_name="Spotify to YouTube Music Migrator")
        # Migrator used when re-queueing interrupted jobs on startup (set by
        # the owner, e.g. MigrationManager, or passed to resume_incomplete_migrations)
        self.default_migrator_func: Optional[Callable] = None
        self.default_progress_callback: Optional[Callable] = None
        # Set while the YouTube Music session is known to be invalid. Jobs
        # pulled from the queue in that state are parked as paused_auth
        # without touching the API; cleared by resume_auth_paused_jobs().
        self.auth_required = threading.Event()

        # Initialize database table for migrations
        self._init_migrations_table()
        
        logger.info("BackgroundWorker initialized")
    
    RESUME_COLUMNS = {
        'youtube_playlist_ids': 'TEXT',
        'added_tracks': 'INTEGER DEFAULT 0',
        'last_added_index': 'INTEGER DEFAULT 0',
        'matched_tracks': 'INTEGER DEFAULT 0',
        'failed_tracks': 'INTEGER DEFAULT 0',
    }
    
    # Job parked because the YouTube Music session expired mid-job. Distinct
    # from 'failed' (nothing is wrong with the job) and from a user pause.
    # Resumes via resume_auth_paused_jobs() once a fresh client is injected.
    PAUSED_AUTH_STATUS = 'paused_auth'

    # Statuses that mean "work still to do" after a restart. A paused_auth job
    # is included: on restart the client is rebuilt from stored credentials,
    # so it gets another go (and simply pauses again if they are still stale).
    RESUMABLE_STATUSES = ('queued', 'in_progress', PAUSED_AUTH_STATUS)
    
    @staticmethod
    def _ensure_column(cursor: sqlite3.Cursor, table: str, column: str, decl: str) -> None:
        """Add ``column`` to ``table`` if it is missing (data-preserving)."""
        cursor.execute(f"PRAGMA table_info({table})")
        existing = {row[1] for row in cursor.fetchall()}
        if column not in existing:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")
            logger.info(f"Added column {table}.{column}")
    
    def _init_migrations_table(self) -> None:
        """Create migrations table for job persistence if it doesn't exist.
        
        Table structure:
        - job_id: Unique job identifier (UUID)
        - playlist_name: Name of the playlist being migrated
        - playlist_id: Spotify playlist ID
        - status: Job status (queued, in_progress, completed, failed,
          paused_auth = waiting for a YouTube Music reconnect)
        - total_tracks: Total number of tracks to migrate
        - processed_tracks: Number of tracks processed so far
        - last_track_id: Last successfully processed track ID (for resume)
        - created_at: Job creation timestamp
        - started_at: Job start timestamp
        - completed_at: Job completion timestamp
        - error_message: Error message if job failed
        
        Resume columns (added with check-and-add so old databases upgrade in place):
        - youtube_playlist_ids: JSON list of destination playlist ids (one per shard)
        - added_tracks: Items written to YouTube across all shards
        - last_added_index: Leading source tracks whose outcome is durable
        - matched_tracks / failed_tracks: Whole-job counters
        
        Raises:
            sqlite3.Error: If table creation fails.
        """
        try:
            with self.cache_manager.connection:
                cursor = self.cache_manager.connection.cursor()
                
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS migrations (
                        job_id TEXT PRIMARY KEY,
                        playlist_name TEXT NOT NULL,
                        playlist_id TEXT NOT NULL,
                        status TEXT NOT NULL,
                        total_tracks INTEGER NOT NULL,
                        processed_tracks INTEGER DEFAULT 0,
                        last_track_id TEXT,
                        created_at TIMESTAMP NOT NULL,
                        started_at TIMESTAMP,
                        completed_at TIMESTAMP,
                        error_message TEXT
                    )
                """)
                
                # Resume columns: add any that an older database lacks
                for column, decl in self.RESUME_COLUMNS.items():
                    self._ensure_column(cursor, 'migrations', column, decl)
                
                # Create index for status queries
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_migrations_status 
                    ON migrations(status)
                """)
                
                logger.debug("Migrations table initialized")
                
        except sqlite3.Error as e:
            logger.error(f"Failed to initialize migrations table: {str(e)}")
            raise
    
    def start(self) -> None:
        """Start the background worker thread.
        
        Creates a daemon thread that processes jobs from the queue.
        Thread will automatically terminate when main program exits.
        
        Raises:
            RuntimeError: If worker is already running.
        """
        if self.is_running.is_set():
            raise RuntimeError("BackgroundWorker is already running")
        
        self.is_running.set()
        self.worker_thread = threading.Thread(
            target=self._worker_loop,
            name="PlaylistMigrationWorker",
            daemon=True
        )
        self.worker_thread.start()
        
        logger.info("BackgroundWorker started")
    
    def stop(self, timeout: float = 30.0) -> None:
        """Stop the background worker thread gracefully.
        
        Waits for the current job to finish before stopping.
        
        Args:
            timeout (float): Maximum seconds to wait for worker to stop.
                Defaults to 30 seconds.
        
        Raises:
            TimeoutError: If worker doesn't stop within timeout.
        """
        if not self.is_running.is_set():
            logger.warning("BackgroundWorker is not running")
            return
        
        logger.info("Stopping BackgroundWorker...")
        self.is_running.clear()
        
        if self.worker_thread and self.worker_thread.is_alive():
            self.worker_thread.join(timeout=timeout)
            
            if self.worker_thread.is_alive():
                raise TimeoutError(
                    f"Worker thread did not stop within {timeout} seconds"
                )
        
        logger.info("BackgroundWorker stopped")
    
    def add_job(
        self,
        playlist_name: str,
        playlist_id: str,
        tracks: List[Dict[str, Any]],
        migrator_func: Callable,
        progress_callback: Optional[Callable] = None,
        job_id: Optional[str] = None,
        resume_state: Optional[Dict[str, Any]] = None
    ) -> str:
        """Add a new migration job to the queue.
        
        Creates a job record in the database and adds it to the processing queue.
        
        Args:
            playlist_name (str): Name of the playlist to migrate.
            playlist_id (str): Spotify playlist ID.
            tracks (List[Dict[str, Any]]): List of Spotify tracks to migrate.
            migrator_func (Callable): Function to execute migration.
                Signature: migrator_func(playlist_name, tracks, progress_callback) -> dict
                If it also accepts ``resume_state`` and ``state_callback`` keyword
                arguments they are supplied, enabling incremental persistence.
            progress_callback (Optional[Callable]): Callback for progress updates.
                Signature: progress_callback(current, total, track_name, matched=0, failed=0) -> None
            job_id (Optional[str]): Reuse an existing job row instead of
                inserting a new one (used when resuming after a restart).
            resume_state (Optional[Dict[str, Any]]): Durable state from the
                existing row to hand to the migrator (see migrate_playlist).
        
        Returns:
            str: Unique job ID (UUID).
        
        Raises:
            ValueError: If required parameters are invalid.
            sqlite3.Error: If database operation fails.
        """
        if not playlist_name:
            raise ValueError("playlist_name is required")
        if not playlist_id:
            raise ValueError("playlist_id is required")
        if not tracks:
            raise ValueError("tracks list cannot be empty")
        if not callable(migrator_func):
            raise ValueError("migrator_func must be callable")
        
        is_resume = job_id is not None
        if not is_resume:
            job_id = str(uuid.uuid4())
        
        # Create job dictionary
        job = {
            'id': job_id,
            'playlist_name': playlist_name,
            'playlist_id': playlist_id,
            'tracks': tracks,
            'migrator_func': migrator_func,
            'progress_callback': progress_callback,
            'resume_state': resume_state,
            'status': 'queued',
            'created_at': datetime.now()
        }
        
        # Persist job to database
        try:
            with self.cache_manager.connection:
                cursor = self.cache_manager.connection.cursor()
                
                if is_resume:
                    cursor.execute("""
                        UPDATE migrations
                        SET status = 'queued', total_tracks = ?, error_message = NULL
                        WHERE job_id = ?
                    """, (len(tracks), job_id))
                    logger.info(f"Re-queued migration job {job_id} for '{playlist_name}' "
                               f"({len(tracks)} tracks)")
                else:
                    cursor.execute("""
                        INSERT INTO migrations 
                        (job_id, playlist_name, playlist_id, status, 
                         total_tracks, processed_tracks, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (
                        job_id,
                        playlist_name,
                        playlist_id,
                        'queued',
                        len(tracks),
                        0,
                        datetime.now()
                    ))
                    
                    logger.info(f"Created migration job {job_id} for '{playlist_name}' "
                               f"with {len(tracks)} tracks")
        
        except sqlite3.Error as e:
            logger.error(f"Failed to create migration job: {str(e)}")
            raise
        
        # Add job to queue
        self.job_queue.put(job)
        
        logger.debug(f"Job {job_id} added to queue")
        
        return job_id
    
    def _worker_loop(self) -> None:
        """Main worker loop that processes jobs from the queue.
        
        Runs continuously while is_running is set. Processes one job at a time,
        updating status in database and calling progress callbacks.
        
        Handles exceptions gracefully to prevent worker thread from crashing.
        """
        logger.info("Worker loop started")
        
        # Create thread-local database connection (SQLite requires this)
        self._worker_connection = sqlite3.connect(self.db_path, check_same_thread=False)
        self._worker_connection.row_factory = sqlite3.Row
        
        try:
            while self.is_running.is_set():
                try:
                    # Try to get a job from queue (timeout to allow checking is_running)
                    try:
                        job = self.job_queue.get(timeout=1.0)
                    except queue.Empty:
                        continue
                    
                    job_id = job['id']
                    playlist_name = job['playlist_name']
                    
                    logger.info(f"Processing job {job_id}: '{playlist_name}'")
                    
                    # Session already known to be invalid: park the job without
                    # spending a request on it. Its resume state is untouched.
                    if self.auth_required.is_set():
                        logger.warning(
                            f"Job {job_id} '{playlist_name}' parked as {self.PAUSED_AUTH_STATUS}: "
                            "YouTube Music session invalid, waiting for reconnect"
                        )
                        self._update_job_status(
                            job_id, self.PAUSED_AUTH_STATUS,
                            error_message="YouTube Music sign-in expired - reconnect to resume"
                        )
                        self.job_queue.task_done()
                        continue

                    # Set current job (thread-safe)
                    with self.current_job_lock:
                        self.current_job = job

                    # Update status to in_progress
                    self._update_job_status(job_id, 'in_progress', started_at=datetime.now())

                    try:
                        # Create progress wrapper that updates database
                        def progress_wrapper(
                            current: int,
                            total: int,
                            track_name: str,
                            matched: int = 0,
                            failed: int = 0
                        ):
                            # Update database with latest counters
                            self._update_job_progress(job_id, current, total)
                            
                            # Forward progress to caller if callback supplied
                            if job['progress_callback']:
                                try:
                                    job['progress_callback'](
                                        current,
                                        total,
                                        track_name,
                                        matched,
                                        failed
                                    )
                                except TypeError:
                                    # Backwards compatibility with 3-arg callbacks
                                    try:
                                        job['progress_callback'](current, total, track_name)
                                    except Exception as e:
                                        logger.error(f"Progress callback error: {str(e)}")
                                except Exception as e:
                                    logger.error(f"Progress callback error: {str(e)}")
                        
                        # Persist durable state (playlist ids, last added index)
                        # whenever the migrator completes a write to YouTube.
                        def state_callback(**state):
                            self._update_job_progress(
                                job_id, None, None,
                                **{k: v for k, v in state.items()
                                   if k in self.RESUME_COLUMNS}
                            )
                        
                        # Execute migration
                        result = self._call_migrator(job, progress_wrapper, state_callback)
                        
                        # Update status to completed
                        self._update_job_status(
                            job_id,
                            'completed',
                            completed_at=datetime.now()
                        )
                        
                        logger.info(f"Job {job_id} completed successfully: "
                                   f"{result.get('matched_tracks', 0)}/{result.get('total_tracks', 0)} tracks migrated")
                        
                        # Send desktop notification (success)
                        playlist_url = result.get('playlist_url', '')
                        self.notifier.notify_migration_complete(
                            playlist_name=playlist_name,
                            matched=result.get('matched_tracks', 0),
                            total=result.get('total_tracks', 0),
                            playlist_url=playlist_url
                        )
                    
                    except YouTubeAuthError as e:
                        # Pause, don't fail. Progress is already durable: the
                        # migrator reported every write through state_callback
                        # (and progress_wrapper), so the row holds the exact
                        # resume point. Nothing to persist here but the status.
                        self._pause_for_auth(job_id, playlist_name, str(e))

                    except Exception as e:
                        error_message = str(e)
                        logger.error(f"Job {job_id} failed: {error_message}", exc_info=True)

                        # Update status to failed
                        self._update_job_status(
                            job_id,
                            'failed',
                            completed_at=datetime.now(),
                            error_message=error_message
                        )
                        
                        # Send desktop notification (error)
                        self.notifier.notify_migration_failed(
                            playlist_name=playlist_name,
                            error=error_message
                        )
                    
                    finally:
                        # Clear current job (thread-safe)
                        with self.current_job_lock:
                            self.current_job = None
                        
                        # Mark job as done in queue
                        self.job_queue.task_done()
                
                except Exception as e:
                    # Catch-all to prevent worker thread from crashing
                    logger.error(f"Unexpected error in worker loop: {str(e)}", exc_info=True)
                
        finally:
            # Close worker connection when loop exits
            if self._worker_connection:
                self._worker_connection.close()
                logger.info("Worker connection closed")
        
        logger.info("Worker loop stopped")
    
    def _pause_for_auth(self, job_id: str, playlist_name: str, reason: str) -> None:
        """Park ``job_id`` as paused_auth and tell the user to reconnect.

        Sets ``auth_required`` so any further queued jobs are parked too
        (without burning API calls on a dead session). The user-facing
        notification fires once per outage, not once per job.
        """
        logger.warning(
            f"Job {job_id} '{playlist_name}' paused: YouTube Music session invalid ({reason})"
        )
        self._update_job_status(
            job_id,
            self.PAUSED_AUTH_STATUS,
            error_message=f"YouTube Music sign-in expired - reconnect to resume ({reason})"
        )
        first_outage = not self.auth_required.is_set()
        self.auth_required.set()
        if first_outage:
            try:
                self.notifier.notify_auth_required(playlist_name=playlist_name)
            except Exception as e:  # notifications are non-critical
                logger.error(f"Auth-required notification failed: {str(e)}")

    def get_active_job_ids(self) -> List[str]:
        """Ids of jobs that still have work to do (queued, in_progress or
        paused_auth), oldest first. Read-only, straight from the job table, so
        it includes jobs re-queued at launch that no UI callback was attached to."""
        placeholders = ', '.join('?' for _ in self.RESUMABLE_STATUSES)
        try:
            cursor = self.cache_manager.connection.cursor()
            cursor.execute(f"""
                SELECT job_id FROM migrations
                WHERE status IN ({placeholders})
                ORDER BY created_at ASC, rowid ASC
            """, tuple(self.RESUMABLE_STATUSES))
            return [row['job_id'] for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error(f"Failed to list active jobs: {str(e)}")
            raise

    def get_auth_paused_jobs(self) -> List[Dict[str, Any]]:
        """Jobs currently parked as paused_auth (see get_all_jobs for the shape)."""
        return self.get_all_jobs(status=self.PAUSED_AUTH_STATUS, limit=1000)

    def is_auth_required(self) -> bool:
        """True while a reconnect is needed: the worker saw an auth failure
        this run, or paused_auth jobs are waiting in the database."""
        if self.auth_required.is_set():
            return True
        try:
            return len(self.get_auth_paused_jobs()) > 0
        except sqlite3.Error:
            return False

    def resume_auth_paused_jobs(
        self,
        migrator_func: Optional[Callable] = None,
        progress_callback: Optional[Callable] = None
    ) -> List[str]:
        """Re-queue every paused_auth job so it continues from its saved state.

        Call after the refreshed YouTube Music client has been injected into
        the searcher/migrator (``MigrationManager.reauthenticate_youtube()``
        does both). Uses the same resume path as crash recovery: source tracks
        reloaded from the ``tracks`` table, destination playlist ids and the
        last-added index from the job row, decided matches from ``match_cache``.

        Returns:
            List[str]: Job IDs that were re-queued (or failed because their
                source tracks are gone).
        """
        self.auth_required.clear()
        resumed = self._requeue_jobs(
            (self.PAUSED_AUTH_STATUS,), migrator_func, progress_callback
        )
        if resumed:
            logger.info(f"Re-queued {len(resumed)} auth-paused migration(s) after reconnect")
        return resumed

    def _update_job_status(
        self,
        job_id: str,
        status: str,
        started_at: Optional[datetime] = None,
        completed_at: Optional[datetime] = None,
        error_message: Optional[str] = None
    ) -> None:
        """Update job status in database.
        
        Args:
            job_id (str): Job ID to update.
            status (str): New status (queued, in_progress, completed, failed).
            started_at (Optional[datetime]): Start timestamp.
            completed_at (Optional[datetime]): Completion timestamp.
            error_message (Optional[str]): Error message if failed.
        
        Raises:
            sqlite3.Error: If database update fails.
        """
        try:
            # Use worker connection if available (in worker thread), otherwise use cache manager connection
            conn = self._worker_connection if self._worker_connection else self.cache_manager.connection
            
            with conn:
                cursor = conn.cursor()
                
                # Build update query dynamically
                updates = ["status = ?"]
                params = [status]
                
                if started_at:
                    updates.append("started_at = ?")
                    params.append(started_at)
                
                if completed_at:
                    updates.append("completed_at = ?")
                    params.append(completed_at)
                
                if error_message:
                    updates.append("error_message = ?")
                    params.append(error_message)
                
                params.append(job_id)
                
                query = f"UPDATE migrations SET {', '.join(updates)} WHERE job_id = ?"
                cursor.execute(query, params)
                
                logger.debug(f"Updated job {job_id} status to '{status}'")
        
        except sqlite3.Error as e:
            logger.error(f"Failed to update job status: {str(e)}")
            raise
    
    def _call_migrator(
        self,
        job: Dict[str, Any],
        progress_wrapper: Callable,
        state_callback: Callable
    ) -> Dict[str, Any]:
        """Invoke the job's migrator, passing resume/state kwargs when it takes them.
        
        Migrators that only accept (playlist_name, tracks, progress_callback)
        keep working; ones that declare ``resume_state`` / ``state_callback``
        get the persisted state and a hook to record new state.
        """
        func = job['migrator_func']
        kwargs: Dict[str, Any] = {}
        try:
            params = inspect.signature(func).parameters
        except (TypeError, ValueError):
            params = {}
        if 'resume_state' in params:
            kwargs['resume_state'] = job.get('resume_state')
        if 'state_callback' in params:
            kwargs['state_callback'] = state_callback
        if 'playlist_id' in params:
            kwargs['playlist_id'] = job.get('playlist_id')
        
        return func(job['playlist_name'], job['tracks'], progress_wrapper, **kwargs)
    
    def _update_job_progress(
        self,
        job_id: str,
        current: Optional[int],
        total: Optional[int],
        last_track_id: Optional[str] = None,
        **state: Any
    ) -> None:
        """Update job progress and/or durable resume state in database.
        
        Args:
            job_id (str): Job ID to update.
            current (Optional[int]): Number of tracks processed (None = leave as is).
            total (Optional[int]): Total number of tracks (None = leave as is).
            last_track_id (Optional[str]): Last processed track ID.
            **state: Any of the RESUME_COLUMNS (youtube_playlist_ids,
                added_tracks, last_added_index, matched_tracks, failed_tracks).
                ``youtube_playlist_ids`` may be a list; it is stored as JSON.
        
        Raises:
            sqlite3.Error: If database update fails.
        """
        try:
            # Use worker connection if available (in worker thread), otherwise use cache manager connection
            conn = self._worker_connection if self._worker_connection else self.cache_manager.connection
            
            updates: List[str] = []
            params: List[Any] = []
            
            if current is not None:
                updates.append("processed_tracks = ?")
                params.append(current)
            if total is not None:
                updates.append("total_tracks = ?")
                params.append(total)
            
            if last_track_id:
                updates.append("last_track_id = ?")
                params.append(last_track_id)
            
            for column in self.RESUME_COLUMNS:
                if column in state and state[column] is not None:
                    value = state[column]
                    if column == 'youtube_playlist_ids' and not isinstance(value, str):
                        value = json.dumps(list(value))
                    updates.append(f"{column} = ?")
                    params.append(value)
            
            if not updates:
                return
            
            params.append(job_id)
            
            with conn:
                cursor = conn.cursor()
                cursor.execute(
                    f"UPDATE migrations SET {', '.join(updates)} WHERE job_id = ?",
                    params
                )
        
        except sqlite3.Error as e:
            logger.error(f"Failed to update job progress: {str(e)}")
            # Don't raise - progress updates are non-critical
    
    def get_current_job(self) -> Optional[Dict[str, Any]]:
        """Get currently executing job (thread-safe).
        
        Returns:
            Optional[Dict[str, Any]]: Current job dictionary, or None if idle.
                Contains: id, playlist_name, playlist_id, tracks, status, created_at
        """
        with self.current_job_lock:
            if self.current_job and 'id' in self.current_job:
                # Return copy to prevent external modification
                return {
                    'id': self.current_job.get('id', ''),
                    'playlist_name': self.current_job.get('playlist_name', ''),
                    'playlist_id': self.current_job.get('playlist_id', ''),
                    'status': self.current_job.get('status', 'unknown'),
                    'created_at': self.current_job.get('created_at', datetime.now()),
                    'total_tracks': len(self.current_job.get('tracks', []))
                }
            return None
    
    def resume_incomplete_migrations(
        self,
        migrator_func: Optional[Callable] = None,
        progress_callback: Optional[Callable] = None
    ) -> List[str]:
        """Resume migrations that were interrupted (crash recovery).
        
        Finds jobs left 'queued' or 'in_progress' by a previous run and puts
        them back on the queue so they *continue*: the source tracks are
        reloaded from the ``tracks`` table (they were cached when the job was
        first queued), and the job row's durable state (destination playlist
        ids, items already added, index of the last added track) is handed to
        the migrator so it skips what is already on YouTube and reuses the
        existing playlist(s) instead of creating new ones. Already-decided
        matches come back from ``match_cache`` automatically.
        
        A job whose source tracks are no longer cached cannot be continued and
        is marked failed with an explanatory message. The same happens when no
        migrator is available (neither ``migrator_func`` nor
        ``default_migrator_func`` is set).
        
        Note: call after worker.start() so re-queued jobs are processed.
        
        Args:
            migrator_func (Optional[Callable]): Migrator to run the resumed jobs
                with. Defaults to ``self.default_migrator_func``.
            progress_callback (Optional[Callable]): Progress callback for the
                resumed jobs. Defaults to ``self.default_progress_callback``.
        
        Returns:
            List[str]: Job IDs that were found incomplete (re-queued or failed).
        
        Raises:
            sqlite3.Error: If database query fails.
        """
        return self._requeue_jobs(self.RESUMABLE_STATUSES, migrator_func, progress_callback)

    def _requeue_jobs(
        self,
        statuses: tuple,
        migrator_func: Optional[Callable],
        progress_callback: Optional[Callable]
    ) -> List[str]:
        """Shared resume path: re-queue every job whose status is in ``statuses``
        with its persisted resume state (see resume_incomplete_migrations)."""
        resumed_jobs: List[str] = []
        migrator_func = migrator_func or self.default_migrator_func
        progress_callback = progress_callback or self.default_progress_callback

        try:
            cursor = self.cache_manager.connection.cursor()

            # Find incomplete migrations (queued-but-never-run jobs were lost
            # with the in-memory queue, so they are incomplete too)
            placeholders = ', '.join('?' for _ in statuses)
            cursor.execute(f"""
                SELECT job_id, playlist_name, playlist_id, total_tracks,
                       youtube_playlist_ids, added_tracks, last_added_index,
                       matched_tracks, failed_tracks
                FROM migrations
                WHERE status IN ({placeholders})
                ORDER BY COALESCE(started_at, created_at) ASC
            """, tuple(statuses))

            incomplete_jobs = cursor.fetchall()
            
            if not incomplete_jobs:
                logger.info("No incomplete migrations found")
                return resumed_jobs
            
            logger.info(f"Found {len(incomplete_jobs)} incomplete migrations")
            
            for row in incomplete_jobs:
                job_id = row['job_id']
                playlist_name = row['playlist_name']
                playlist_id = row['playlist_id']
                resumed_jobs.append(job_id)
                
                if migrator_func is None:
                    self._fail_resume(job_id, playlist_name,
                                      "Migration was interrupted and no migrator is available to resume it.")
                    continue
                
                tracks = self.cache_manager.get_cached_tracks(playlist_id)
                if not tracks:
                    self._fail_resume(job_id, playlist_name,
                                      "Migration was interrupted and its source tracks are no longer cached. "
                                      "Please start it again.")
                    continue
                
                resume_state = self._row_resume_state(row)
                
                logger.info(
                    f"Resuming job {job_id} '{playlist_name}': "
                    f"{resume_state['last_added_index']}/{len(tracks)} tracks already final, "
                    f"{len(resume_state['youtube_playlist_ids'])} destination playlist(s)"
                )
                
                self.add_job(
                    playlist_name=playlist_name,
                    playlist_id=playlist_id,
                    tracks=tracks,
                    migrator_func=migrator_func,
                    progress_callback=progress_callback,
                    job_id=job_id,
                    resume_state=resume_state
                )
        
        except sqlite3.Error as e:
            logger.error(f"Failed to resume incomplete migrations: {str(e)}")
            raise
        
        return resumed_jobs
    
    @staticmethod
    def _row_resume_state(row: sqlite3.Row) -> Dict[str, Any]:
        """Decode a migrations row's resume columns into a resume_state dict."""
        raw_ids = row['youtube_playlist_ids']
        try:
            playlist_ids = json.loads(raw_ids) if raw_ids else []
        except (TypeError, ValueError):
            playlist_ids = []
        return {
            'youtube_playlist_ids': playlist_ids,
            'added_tracks': row['added_tracks'] or 0,
            'last_added_index': row['last_added_index'] or 0,
            'matched_tracks': row['matched_tracks'] or 0,
            'failed_tracks': row['failed_tracks'] or 0,
        }
    
    def _fail_resume(self, job_id: str, playlist_name: str, reason: str) -> None:
        """Mark an interrupted job failed when it genuinely cannot continue."""
        self._update_job_status(
            job_id,
            'failed',
            completed_at=datetime.now(),
            error_message=reason
        )
        logger.warning(f"Could not resume interrupted job {job_id} '{playlist_name}': {reason}")
        self.notifier.notify_migration_failed(playlist_name=playlist_name, error=reason)
    
    def get_job_status(self, job_id: str) -> Dict[str, Any]:
        """Get status of a specific job.
        
        Args:
            job_id (str): Job ID to query.
        
        Returns:
            Dict[str, Any]: Job status dictionary containing:
                - status (str): Job status (queued, in_progress, completed, failed)
                - progress (int): Number of tracks processed
                - total (int): Total number of tracks
                - playlist_name (str): Playlist name
                - playlist_id (str): Spotify source playlist id
                - created_at (datetime): Job creation time
                - started_at (Optional[datetime]): Job start time
                - completed_at (Optional[datetime]): Job completion time
                - error_message (Optional[str]): Error message if failed
                - youtube_playlist_ids (List[str]): Destination playlist ids (shards)
                - added_tracks (int): Items written to YouTube so far
                - last_added_index (int): Source tracks whose outcome is durable
                - matched_tracks / failed_tracks (int): Whole-job counters
        
        Raises:
            ValueError: If job_id not found.
            sqlite3.Error: If database query fails.
        """
        try:
            cursor = self.cache_manager.connection.cursor()
            
            cursor.execute("""
                SELECT status, processed_tracks, total_tracks, playlist_name,
                       playlist_id, created_at, started_at, completed_at, error_message,
                       youtube_playlist_ids, added_tracks, last_added_index,
                       matched_tracks, failed_tracks
                FROM migrations
                WHERE job_id = ?
            """, (job_id,))
            
            row = cursor.fetchone()
            
            if not row:
                raise ValueError(f"Job {job_id} not found")
            
            resume_state = self._row_resume_state(row)
            
            return {
                'status': row['status'],
                'progress': row['processed_tracks'],
                'total': row['total_tracks'],
                'playlist_name': row['playlist_name'],
                'playlist_id': row['playlist_id'],
                'created_at': row['created_at'],
                'started_at': row['started_at'],
                'completed_at': row['completed_at'],
                'error_message': row['error_message'],
                'youtube_playlist_ids': resume_state['youtube_playlist_ids'],
                'added_tracks': resume_state['added_tracks'],
                'last_added_index': resume_state['last_added_index'],
                'matched_tracks': resume_state['matched_tracks'],
                'failed_tracks': resume_state['failed_tracks'],
            }
        
        except sqlite3.Error as e:
            logger.error(f"Failed to get job status: {str(e)}")
            raise
    
    def get_all_jobs(
        self,
        status: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get all migration jobs, optionally filtered by status.
        
        Args:
            status (Optional[str]): Filter by status (queued, in_progress, completed, failed).
                If None, returns all jobs.
            limit (int): Maximum number of jobs to return. Defaults to 100.
        
        Returns:
            List[Dict[str, Any]]: List of job status dictionaries.
        
        Raises:
            sqlite3.Error: If database query fails.
        """
        try:
            cursor = self.cache_manager.connection.cursor()
            
            if status:
                cursor.execute("""
                    SELECT job_id, status, processed_tracks, total_tracks, 
                           playlist_name, created_at, started_at, completed_at, error_message,
                           playlist_id
                    FROM migrations
                    WHERE status = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                """, (status, limit))
            else:
                cursor.execute("""
                    SELECT job_id, status, processed_tracks, total_tracks,
                           playlist_name, created_at, started_at, completed_at, error_message,
                           playlist_id
                    FROM migrations
                    ORDER BY created_at DESC
                    LIMIT ?
                """, (limit,))
            
            rows = cursor.fetchall()
            
            jobs = []
            for row in rows:
                job_id, status, progress, total, playlist_name, created_at, started_at, completed_at, error_message, playlist_id = row
                
                jobs.append({
                    'job_id': job_id,
                    'status': status,
                    'progress': progress,
                    'total': total,
                    'playlist_name': playlist_name,
                    'created_at': created_at,
                    'started_at': started_at,
                    'completed_at': completed_at,
                    'error_message': error_message,
                    'playlist_id': playlist_id
                })
            
            return jobs
        
        except sqlite3.Error as e:
            logger.error(f"Failed to get jobs: {str(e)}")
            raise
    
    def clear_completed_jobs(self, days_old: int = 30) -> int:
        """Clear completed and failed jobs older than specified days.
        
        Args:
            days_old (int): Remove jobs older than this many days. Defaults to 30.
        
        Returns:
            int: Number of jobs removed.
        
        Raises:
            sqlite3.Error: If database operation fails.
        """
        try:
            with self.cache_manager.connection:
                cursor = self.cache_manager.connection.cursor()
                
                cutoff_date = datetime.now().timestamp() - (days_old * 24 * 60 * 60)
                
                cursor.execute("""
                    DELETE FROM migrations
                    WHERE status IN ('completed', 'failed')
                    AND created_at < ?
                """, (cutoff_date,))
                
                deleted_count = cursor.rowcount
                
                logger.info(f"Cleared {deleted_count} old migration jobs")
                
                return deleted_count
        
        except sqlite3.Error as e:
            logger.error(f"Failed to clear old jobs: {str(e)}")
            raise
