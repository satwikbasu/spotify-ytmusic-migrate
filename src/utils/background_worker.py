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

import queue
import threading
import logging
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any, Callable
import sqlite3

from src.utils.cache_manager import CacheManager
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
        
        # Initialize database table for migrations
        self._init_migrations_table()
        
        logger.info("BackgroundWorker initialized")
    
    def _init_migrations_table(self) -> None:
        """Create migrations table for job persistence if it doesn't exist.
        
        Table structure:
        - job_id: Unique job identifier (UUID)
        - playlist_name: Name of the playlist being migrated
        - playlist_id: Spotify playlist ID
        - status: Job status (queued, in_progress, completed, failed)
        - total_tracks: Total number of tracks to migrate
        - processed_tracks: Number of tracks processed so far
        - last_track_id: Last successfully processed track ID (for resume)
        - created_at: Job creation timestamp
        - started_at: Job start timestamp
        - completed_at: Job completion timestamp
        - error_message: Error message if job failed
        
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
        progress_callback: Optional[Callable] = None
    ) -> str:
        """Add a new migration job to the queue.
        
        Creates a job record in the database and adds it to the processing queue.
        
        Args:
            playlist_name (str): Name of the playlist to migrate.
            playlist_id (str): Spotify playlist ID.
            tracks (List[Dict[str, Any]]): List of Spotify tracks to migrate.
            migrator_func (Callable): Function to execute migration.
                Signature: migrator_func(playlist_name, tracks, progress_callback) -> dict
            progress_callback (Optional[Callable]): Callback for progress updates.
                Signature: progress_callback(current, total, track_name) -> None
        
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
        
        # Generate unique job ID
        job_id = str(uuid.uuid4())
        
        # Create job dictionary
        job = {
            'id': job_id,
            'playlist_name': playlist_name,
            'playlist_id': playlist_id,
            'tracks': tracks,
            'migrator_func': migrator_func,
            'progress_callback': progress_callback,
            'status': 'queued',
            'created_at': datetime.now()
        }
        
        # Persist job to database
        try:
            with self.cache_manager.connection:
                cursor = self.cache_manager.connection.cursor()
                
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
                    
                    # Set current job (thread-safe)
                    with self.current_job_lock:
                        self.current_job = job
                    
                    # Update status to in_progress
                    self._update_job_status(job_id, 'in_progress', started_at=datetime.now())
                    
                    try:
                        # Create progress wrapper that updates database
                        def progress_wrapper(current: int, total: int, track_name: str):
                            # Update database
                            self._update_job_progress(job_id, current, total)
                            
                            # Call user callback if provided
                            if job['progress_callback']:
                                try:
                                    job['progress_callback'](current, total, track_name)
                                except Exception as e:
                                    logger.error(f"Progress callback error: {str(e)}")
                        
                        # Execute migration
                        result = job['migrator_func'](
                            job['playlist_name'],
                            job['tracks'],
                            progress_wrapper
                        )
                        
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
    
    def _update_job_progress(
        self,
        job_id: str,
        current: int,
        total: int,
        last_track_id: Optional[str] = None
    ) -> None:
        """Update job progress in database.
        
        Args:
            job_id (str): Job ID to update.
            current (int): Number of tracks processed.
            total (int): Total number of tracks.
            last_track_id (Optional[str]): Last processed track ID.
        
        Raises:
            sqlite3.Error: If database update fails.
        """
        try:
            # Use worker connection if available (in worker thread), otherwise use cache manager connection
            conn = self._worker_connection if self._worker_connection else self.cache_manager.connection
            
            with conn:
                cursor = conn.cursor()
                
                if last_track_id:
                    cursor.execute("""
                        UPDATE migrations 
                        SET processed_tracks = ?, total_tracks = ?, last_track_id = ?
                        WHERE job_id = ?
                    """, (current, total, last_track_id, job_id))
                else:
                    cursor.execute("""
                        UPDATE migrations 
                        SET processed_tracks = ?, total_tracks = ?
                        WHERE job_id = ?
                    """, (current, total, job_id))
        
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
    
    def resume_incomplete_migrations(self) -> List[str]:
        """Resume migrations that were interrupted (crash recovery).
        
        Queries database for jobs with status='in_progress' and re-adds them
        to the queue. Useful for recovering from application crashes.
        
        Note: This should be called after worker.start() to ensure jobs
        are processed. The actual track data is not persisted, so jobs
        cannot be fully resumed - they will be marked as failed.
        
        Returns:
            List[str]: List of resumed job IDs.
        
        Raises:
            sqlite3.Error: If database query fails.
        """
        resumed_jobs = []
        
        try:
            cursor = self.cache_manager.connection.cursor()
            
            # Find incomplete migrations
            cursor.execute("""
                SELECT job_id, playlist_name, playlist_id, total_tracks
                FROM migrations
                WHERE status = 'in_progress'
                ORDER BY started_at ASC
            """)
            
            incomplete_jobs = cursor.fetchall()
            
            if not incomplete_jobs:
                logger.info("No incomplete migrations found")
                return resumed_jobs
            
            logger.info(f"Found {len(incomplete_jobs)} incomplete migrations")
            
            # Mark them as failed (cannot resume without track data)
            for job in incomplete_jobs:
                job_id, playlist_name, playlist_id, total_tracks = job
                
                self._update_job_status(
                    job_id,
                    'failed',
                    completed_at=datetime.now(),
                    error_message="Migration interrupted by application crash"
                )
                
                resumed_jobs.append(job_id)
                
                logger.warning(f"Marked interrupted job {job_id} as failed: '{playlist_name}'")
                
                # Send notification
                self.notifier.notify_migration_failed(
                    playlist_name=playlist_name,
                    error="Migration was interrupted by application crash. Please try again."
                )
        
        except sqlite3.Error as e:
            logger.error(f"Failed to resume incomplete migrations: {str(e)}")
            raise
        
        return resumed_jobs
    
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
                - created_at (datetime): Job creation time
                - started_at (Optional[datetime]): Job start time
                - completed_at (Optional[datetime]): Job completion time
                - error_message (Optional[str]): Error message if failed
        
        Raises:
            ValueError: If job_id not found.
            sqlite3.Error: If database query fails.
        """
        try:
            cursor = self.cache_manager.connection.cursor()
            
            cursor.execute("""
                SELECT status, processed_tracks, total_tracks, playlist_name,
                       created_at, started_at, completed_at, error_message
                FROM migrations
                WHERE job_id = ?
            """, (job_id,))
            
            row = cursor.fetchone()
            
            if not row:
                raise ValueError(f"Job {job_id} not found")
            
            status, progress, total, playlist_name, created_at, started_at, completed_at, error_message = row
            
            return {
                'status': status,
                'progress': progress,
                'total': total,
                'playlist_name': playlist_name,
                'created_at': created_at,
                'started_at': started_at,
                'completed_at': completed_at,
                'error_message': error_message
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
                           playlist_name, created_at, started_at, completed_at, error_message
                    FROM migrations
                    WHERE status = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                """, (status, limit))
            else:
                cursor.execute("""
                    SELECT job_id, status, processed_tracks, total_tracks,
                           playlist_name, created_at, started_at, completed_at, error_message
                    FROM migrations
                    ORDER BY created_at DESC
                    LIMIT ?
                """, (limit,))
            
            rows = cursor.fetchall()
            
            jobs = []
            for row in rows:
                job_id, status, progress, total, playlist_name, created_at, started_at, completed_at, error_message = row
                
                jobs.append({
                    'job_id': job_id,
                    'status': status,
                    'progress': progress,
                    'total': total,
                    'playlist_name': playlist_name,
                    'created_at': created_at,
                    'started_at': started_at,
                    'completed_at': completed_at,
                    'error_message': error_message
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
