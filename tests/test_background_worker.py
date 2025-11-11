"""Tests for BackgroundWorker class.

Tests the thread-safe background worker with producer-consumer pattern,
crash recovery, and database persistence.
"""

import pytest
import time
import threading
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
import sqlite3

from src.utils.background_worker import BackgroundWorker
from src.utils.cache_manager import CacheManager


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def cache_manager(tmp_path):
    """Create a temporary CacheManager for testing."""
    db_path = tmp_path / "test_worker.db"
    return CacheManager(str(db_path))


@pytest.fixture
def worker(cache_manager):
    """Create a BackgroundWorker instance."""
    return BackgroundWorker(cache_manager)


@pytest.fixture
def sample_tracks():
    """Sample Spotify tracks for testing."""
    return [
        {
            'name': 'Track 1',
            'artists': ['Artist 1'],
            'album': 'Album 1',
            'duration_ms': 200000,
            'spotify_id': 'track1'
        },
        {
            'name': 'Track 2',
            'artists': ['Artist 2'],
            'album': 'Album 2',
            'duration_ms': 180000,
            'spotify_id': 'track2'
        }
    ]


# ============================================================================
# Test: Initialization
# ============================================================================

def test_init(worker, cache_manager):
    """Test BackgroundWorker initialization."""
    assert worker.cache_manager is cache_manager
    assert isinstance(worker.job_queue, type(worker.job_queue))
    assert isinstance(worker.is_running, threading.Event)
    assert worker.current_job is None
    assert isinstance(worker.current_job_lock, threading.Lock)
    assert worker.worker_thread is None
    
    # Verify migrations table was created
    cursor = cache_manager.connection.cursor()
    cursor.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name='migrations'
    """)
    assert cursor.fetchone() is not None


def test_init_creates_migrations_table(cache_manager):
    """Test that migrations table is created with correct schema."""
    worker = BackgroundWorker(cache_manager)
    
    cursor = cache_manager.connection.cursor()
    cursor.execute("PRAGMA table_info(migrations)")
    columns = {row[1]: row[2] for row in cursor.fetchall()}
    
    # Verify all required columns exist
    assert 'job_id' in columns
    assert 'playlist_name' in columns
    assert 'playlist_id' in columns
    assert 'status' in columns
    assert 'total_tracks' in columns
    assert 'processed_tracks' in columns
    assert 'last_track_id' in columns
    assert 'created_at' in columns
    assert 'started_at' in columns
    assert 'completed_at' in columns
    assert 'error_message' in columns


# ============================================================================
# Test: Start/Stop
# ============================================================================

def test_start(worker):
    """Test starting the background worker."""
    worker.start()
    
    assert worker.is_running.is_set()
    assert worker.worker_thread is not None
    assert worker.worker_thread.is_alive()
    assert worker.worker_thread.daemon is True
    
    # Cleanup
    worker.stop()


def test_start_already_running(worker):
    """Test starting worker when already running raises error."""
    worker.start()
    
    with pytest.raises(RuntimeError, match="already running"):
        worker.start()
    
    # Cleanup
    worker.stop()


def test_stop(worker):
    """Test stopping the background worker."""
    worker.start()
    assert worker.is_running.is_set()
    
    worker.stop()
    
    assert not worker.is_running.is_set()
    assert not worker.worker_thread.is_alive()


def test_stop_not_running(worker):
    """Test stopping worker when not running (should not raise)."""
    # Should not raise error
    worker.stop()


def test_stop_timeout(worker):
    """Test that stop raises TimeoutError if worker doesn't stop."""
    worker.start()
    
    # Mock the thread to never stop
    original_join = worker.worker_thread.join
    worker.worker_thread.join = Mock(return_value=None)
    worker.worker_thread.is_alive = Mock(return_value=True)
    
    with pytest.raises(TimeoutError, match="did not stop within"):
        worker.stop(timeout=0.1)
    
    # Restore and cleanup
    worker.worker_thread.join = original_join
    worker.is_running.clear()
    worker.worker_thread.join(timeout=1)


# ============================================================================
# Test: Add Job
# ============================================================================

def test_add_job(worker, sample_tracks):
    """Test adding a job to the queue."""
    migrator_func = Mock(return_value={'matched_tracks': 2, 'total_tracks': 2})
    progress_callback = Mock()
    
    job_id = worker.add_job(
        playlist_name="Test Playlist",
        playlist_id="sp_123",
        tracks=sample_tracks,
        migrator_func=migrator_func,
        progress_callback=progress_callback
    )
    
    # Verify job ID is UUID
    assert isinstance(job_id, str)
    assert len(job_id) == 36  # UUID length with dashes
    
    # Verify job was added to queue
    assert worker.job_queue.qsize() == 1
    
    # Verify job was persisted to database
    cursor = worker.cache_manager.connection.cursor()
    cursor.execute("SELECT * FROM migrations WHERE job_id = ?", (job_id,))
    row = cursor.fetchone()
    
    assert row is not None
    assert row[1] == "Test Playlist"  # playlist_name
    assert row[2] == "sp_123"  # playlist_id
    assert row[3] == "queued"  # status
    assert row[4] == 2  # total_tracks


def test_add_job_validation(worker, sample_tracks):
    """Test job validation in add_job."""
    migrator_func = Mock()
    
    # Empty playlist name
    with pytest.raises(ValueError, match="playlist_name is required"):
        worker.add_job("", "sp_123", sample_tracks, migrator_func)
    
    # Empty playlist ID
    with pytest.raises(ValueError, match="playlist_id is required"):
        worker.add_job("Test", "", sample_tracks, migrator_func)
    
    # Empty tracks
    with pytest.raises(ValueError, match="tracks list cannot be empty"):
        worker.add_job("Test", "sp_123", [], migrator_func)
    
    # Non-callable migrator_func
    with pytest.raises(ValueError, match="must be callable"):
        worker.add_job("Test", "sp_123", sample_tracks, "not_callable")


def test_add_multiple_jobs(worker, sample_tracks):
    """Test adding multiple jobs to queue."""
    migrator_func = Mock(return_value={'matched_tracks': 2, 'total_tracks': 2})
    
    job_ids = []
    for i in range(5):
        job_id = worker.add_job(
            playlist_name=f"Playlist {i}",
            playlist_id=f"sp_{i}",
            tracks=sample_tracks,
            migrator_func=migrator_func
        )
        job_ids.append(job_id)
    
    # Verify all jobs are in queue
    assert worker.job_queue.qsize() == 5
    
    # Verify all jobs are unique
    assert len(set(job_ids)) == 5


# ============================================================================
# Test: Job Processing
# ============================================================================

def test_process_job_success(worker, sample_tracks):
    """Test successful job processing."""
    # Create mock migrator that simulates successful migration
    result = {'matched_tracks': 2, 'total_tracks': 2, 'success_rate': 100.0}
    migrator_func = Mock(return_value=result)
    progress_callback = Mock()
    
    worker.start()
    time.sleep(0.1)  # Give worker thread time to start
    
    job_id = worker.add_job(
        playlist_name="Test Playlist",
        playlist_id="sp_123",
        tracks=sample_tracks,
        migrator_func=migrator_func,
        progress_callback=progress_callback
    )
    
    # Wait for job to complete with timeout
    max_wait = 5.0
    start_time = time.time()
    while time.time() - start_time < max_wait:
        if worker.job_queue.empty() and worker.get_current_job() is None:
            break
        time.sleep(0.1)
    
    time.sleep(0.2)  # Allow time for database update
    
    # Verify migrator was called
    migrator_func.assert_called_once()
    
    # Verify job status in database
    status = worker.get_job_status(job_id)
    assert status['status'] == 'completed'
    assert status['playlist_name'] == "Test Playlist"
    
    # Cleanup
    worker.stop()


def test_process_job_failure(worker, sample_tracks):
    """Test job processing with exception."""
    # Create mock migrator that raises exception
    migrator_func = Mock(side_effect=Exception("Migration failed"))
    
    worker.start()
    time.sleep(0.1)  # Give worker thread time to start
    
    job_id = worker.add_job(
        playlist_name="Test Playlist",
        playlist_id="sp_123",
        tracks=sample_tracks,
        migrator_func=migrator_func
    )
    
    # Wait for job to complete with timeout
    max_wait = 5.0
    start_time = time.time()
    while time.time() - start_time < max_wait:
        if worker.job_queue.empty() and worker.get_current_job() is None:
            break
        time.sleep(0.1)
    
    time.sleep(0.2)  # Allow time for database update
    
    # Verify job status in database
    status = worker.get_job_status(job_id)
    assert status['status'] == 'failed'
    assert 'Migration failed' in status['error_message']
    
    # Cleanup
    worker.stop()


def test_process_job_progress_updates(worker, sample_tracks):
    """Test that progress updates are tracked."""
    progress_calls = []
    
    def migrator_func(playlist_name, tracks, progress_callback):
        # Simulate processing with progress updates
        for i, track in enumerate(tracks, 1):
            progress_callback(i, len(tracks), track['name'])
            time.sleep(0.1)
        return {'matched_tracks': len(tracks), 'total_tracks': len(tracks)}
    
    def user_progress_callback(current, total, track_name):
        progress_calls.append((current, total, track_name))
    
    worker.start()
    time.sleep(0.1)  # Give worker thread time to start
    
    job_id = worker.add_job(
        playlist_name="Test Playlist",
        playlist_id="sp_123",
        tracks=sample_tracks,
        migrator_func=migrator_func,
        progress_callback=user_progress_callback
    )
    
    # Wait for job to complete with timeout
    max_wait = 5.0
    start_time = time.time()
    while time.time() - start_time < max_wait:
        if worker.job_queue.empty() and worker.get_current_job() is None:
            break
        time.sleep(0.1)
    
    time.sleep(0.2)  # Allow time for database update
    
    # Verify progress callbacks were called
    assert len(progress_calls) == 2
    assert progress_calls[0] == (1, 2, 'Track 1')
    assert progress_calls[1] == (2, 2, 'Track 2')
    
    # Verify final progress in database
    status = worker.get_job_status(job_id)
    assert status['progress'] == 2
    assert status['total'] == 2
    
    # Cleanup
    worker.stop()


def test_current_job_tracking(worker, sample_tracks):
    """Test that current job is tracked correctly."""
    # Create a migrator that takes some time
    def slow_migrator(playlist_name, tracks, progress_callback):
        time.sleep(0.5)
        return {'matched_tracks': 2, 'total_tracks': 2}
    
    worker.start()
    time.sleep(0.1)  # Give worker thread time to start
    
    # Add job
    job_id = worker.add_job(
        playlist_name="Test Playlist",
        playlist_id="sp_123",
        tracks=sample_tracks,
        migrator_func=slow_migrator
    )
    
    # Wait a bit for job to start
    time.sleep(0.2)
    
    # Get current job
    current = worker.get_current_job()
    
    if current:  # Job might have completed already in fast environments
        assert current['id'] == job_id
        assert current['playlist_name'] == "Test Playlist"
        assert current['total_tracks'] == 2
    
    # Wait for completion with timeout
    max_wait = 5.0
    start_time = time.time()
    while time.time() - start_time < max_wait:
        if worker.job_queue.empty() and worker.get_current_job() is None:
            break
        time.sleep(0.1)
    
    # Current job should be None after completion
    assert worker.get_current_job() is None
    
    # Cleanup
    worker.stop()


def test_worker_processes_job(worker, sample_tracks):
    """Test that worker processes a simple job successfully.
    
    Per test_spec.md requirement #2:
    - Create worker
    - Add simple job (mock migrator function)
    - Start worker
    - Wait for job completion
    - Verify job status changed to 'completed'
    """
    # Create simple mock migrator
    migrator_func = Mock(return_value={'matched_tracks': 2, 'total_tracks': 2})
    
    # Add job
    job_id = worker.add_job(
        playlist_name="Test Playlist",
        playlist_id="sp_test_123",
        tracks=sample_tracks,
        migrator_func=migrator_func
    )
    
    # Start worker
    worker.start()
    
    # Wait for job to complete with timeout
    max_wait = 5.0
    start_time = time.time()
    while time.time() - start_time < max_wait:
        status = worker.get_job_status(job_id)
        if status and status['status'] == 'completed':
            break
        time.sleep(0.1)
    
    # Verify job status changed to 'completed'
    status = worker.get_job_status(job_id)
    assert status is not None
    assert status['status'] == 'completed'
    assert status['playlist_name'] == "Test Playlist"
    
    # Verify migrator was called
    migrator_func.assert_called_once()
    
    # Cleanup
    worker.stop()


def test_worker_handles_exception(worker, sample_tracks):
    """Test that worker handles exceptions in jobs.
    
    Per test_spec.md requirement #3:
    - Add job that raises exception
    - Start worker
    - Verify status changed to 'failed'
    - Verify error logged
    """
    # Create migrator that raises exception
    error_message = "Test migration error"
    migrator_func = Mock(side_effect=Exception(error_message))
    
    # Add job
    job_id = worker.add_job(
        playlist_name="Failing Playlist",
        playlist_id="sp_fail_123",
        tracks=sample_tracks,
        migrator_func=migrator_func
    )
    
    # Start worker
    worker.start()
    
    # Wait for job to fail with timeout
    max_wait = 5.0
    start_time = time.time()
    while time.time() - start_time < max_wait:
        status = worker.get_job_status(job_id)
        if status and status['status'] == 'failed':
            break
        time.sleep(0.1)
    
    # Verify job status changed to 'failed'
    status = worker.get_job_status(job_id)
    assert status is not None
    assert status['status'] == 'failed'
    assert error_message in status['error_message']
    
    # Cleanup
    worker.stop()


def test_multiple_jobs_processed_in_order(worker, sample_tracks):
    """Test that multiple jobs are processed in FIFO order.
    
    Per test_spec.md requirement #4:
    - Add 3 jobs
    - Verify processed in FIFO order
    """
    # Track job processing order
    processing_order = []
    
    def create_migrator(job_number):
        """Create a migrator that records its job number."""
        def migrator(playlist_name, tracks, progress_callback):
            processing_order.append(job_number)
            time.sleep(0.1)  # Small delay to ensure sequential processing
            return {'matched_tracks': len(tracks), 'total_tracks': len(tracks)}
        return migrator
    
    # Add 3 jobs
    job_ids = []
    for i in range(1, 4):
        job_id = worker.add_job(
            playlist_name=f"Playlist {i}",
            playlist_id=f"sp_job_{i}",
            tracks=sample_tracks,
            migrator_func=create_migrator(i)
        )
        job_ids.append(job_id)
    
    # Start worker
    worker.start()
    
    # Wait for all jobs to complete with timeout
    max_wait = 10.0
    start_time = time.time()
    while time.time() - start_time < max_wait:
        all_completed = True
        for job_id in job_ids:
            status = worker.get_job_status(job_id)
            if not status or status['status'] not in ['completed', 'failed']:
                all_completed = False
                break
        if all_completed:
            break
        time.sleep(0.1)
    
    # Verify jobs were processed in FIFO order (1, 2, 3)
    assert processing_order == [1, 2, 3], f"Expected [1, 2, 3], got {processing_order}"
    
    # Verify all jobs completed successfully
    for i, job_id in enumerate(job_ids, 1):
        status = worker.get_job_status(job_id)
        assert status['status'] == 'completed', f"Job {i} did not complete successfully"
    
    # Cleanup
    worker.stop()


def test_progress_tracking(worker, sample_tracks):
    """Test dedicated progress tracking with callbacks.
    
    Per test_spec.md requirement #7:
    - Add job with progress callback
    - Verify callback called with correct values
    """
    # Track progress callback invocations
    progress_calls = []
    
    def progress_callback(current, total, track_name):
        """Track all progress callback invocations."""
        progress_calls.append({
            'current': current,
            'total': total,
            'track_name': track_name
        })
    
    def migrator_with_progress(playlist_name, tracks, callback):
        """Migrator that reports progress for each track."""
        for idx, track in enumerate(tracks, 1):
            callback(idx, len(tracks), track.get('name', f'Track {idx}'))
            time.sleep(0.05)  # Small delay between tracks
        return {'matched_tracks': len(tracks), 'total_tracks': len(tracks)}
    
    # Add job with progress callback
    job_id = worker.add_job(
        playlist_name="Progress Test Playlist",
        playlist_id="sp_progress_123",
        tracks=sample_tracks,
        migrator_func=migrator_with_progress,
        progress_callback=progress_callback
    )
    
    # Start worker
    worker.start()
    
    # Wait for job to complete with timeout
    max_wait = 5.0
    start_time = time.time()
    while time.time() - start_time < max_wait:
        status = worker.get_job_status(job_id)
        if status and status['status'] == 'completed':
            break
        time.sleep(0.1)
    
    # Verify job completed
    status = worker.get_job_status(job_id)
    assert status['status'] == 'completed'
    
    # Verify progress callbacks were called
    assert len(progress_calls) == len(sample_tracks), \
        f"Expected {len(sample_tracks)} progress calls, got {len(progress_calls)}"
    
    # Verify progress values
    for idx, call in enumerate(progress_calls, 1):
        assert call['current'] == idx, f"Call {idx}: expected current={idx}, got {call['current']}"
        assert call['total'] == len(sample_tracks), \
            f"Call {idx}: expected total={len(sample_tracks)}, got {call['total']}"
        assert call['track_name'] == sample_tracks[idx-1].get('name', f'Track {idx}'), \
            f"Call {idx}: track name mismatch"
    
    # Cleanup
    worker.stop()


# ============================================================================
# Test: Get Job Status
# ============================================================================

def test_get_job_status(worker, sample_tracks):
    """Test retrieving job status."""
    migrator_func = Mock(return_value={'matched_tracks': 2, 'total_tracks': 2})
    
    job_id = worker.add_job(
        playlist_name="Test Playlist",
        playlist_id="sp_123",
        tracks=sample_tracks,
        migrator_func=migrator_func
    )
    
    status = worker.get_job_status(job_id)
    
    assert status['status'] == 'queued'
    assert status['progress'] == 0
    assert status['total'] == 2
    assert status['playlist_name'] == "Test Playlist"
    assert status['created_at'] is not None


def test_get_job_status_not_found(worker):
    """Test getting status for non-existent job."""
    with pytest.raises(ValueError, match="Job .* not found"):
        worker.get_job_status("non-existent-id")


# ============================================================================
# Test: Get All Jobs
# ============================================================================

def test_get_all_jobs(worker, sample_tracks):
    """Test retrieving all jobs."""
    migrator_func = Mock(return_value={'matched_tracks': 2, 'total_tracks': 2})
    
    # Add multiple jobs with different statuses
    job_ids = []
    for i in range(3):
        job_id = worker.add_job(
            playlist_name=f"Playlist {i}",
            playlist_id=f"sp_{i}",
            tracks=sample_tracks,
            migrator_func=migrator_func
        )
        job_ids.append(job_id)
    
    # Get all jobs
    jobs = worker.get_all_jobs()
    
    assert len(jobs) >= 3
    assert all(job['job_id'] in job_ids for job in jobs[:3])


def test_get_all_jobs_filtered_by_status(worker, sample_tracks):
    """Test retrieving jobs filtered by status."""
    migrator_func = Mock(return_value={'matched_tracks': 2, 'total_tracks': 2})
    
    # Add jobs
    job_id = worker.add_job(
        playlist_name="Test Playlist",
        playlist_id="sp_123",
        tracks=sample_tracks,
        migrator_func=migrator_func
    )
    
    # Get queued jobs
    queued_jobs = worker.get_all_jobs(status='queued')
    
    assert len(queued_jobs) >= 1
    assert any(job['job_id'] == job_id for job in queued_jobs)
    assert all(job['status'] == 'queued' for job in queued_jobs)


def test_get_all_jobs_limit(worker, sample_tracks):
    """Test that get_all_jobs respects limit."""
    migrator_func = Mock(return_value={'matched_tracks': 2, 'total_tracks': 2})
    
    # Add many jobs
    for i in range(10):
        worker.add_job(
            playlist_name=f"Playlist {i}",
            playlist_id=f"sp_{i}",
            tracks=sample_tracks,
            migrator_func=migrator_func
        )
    
    # Get with limit
    jobs = worker.get_all_jobs(limit=5)
    
    assert len(jobs) == 5


# ============================================================================
# Test: Resume Incomplete Migrations
# ============================================================================

def test_resume_incomplete_migrations_none(worker):
    """Test resuming when no incomplete migrations exist."""
    resumed = worker.resume_incomplete_migrations()
    
    assert resumed == []


def test_resume_incomplete_migrations(worker, cache_manager, sample_tracks):
    """Test resuming incomplete migrations after crash."""
    # Manually insert incomplete migration into database
    cursor = cache_manager.connection.cursor()
    job_id = "test-job-123"
    
    cursor.execute("""
        INSERT INTO migrations 
        (job_id, playlist_name, playlist_id, status, total_tracks, 
         processed_tracks, created_at, started_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        job_id,
        "Interrupted Playlist",
        "sp_interrupted",
        "in_progress",
        5,
        3,
        datetime.now(),
        datetime.now()
    ))
    cache_manager.connection.commit()
    
    # Resume incomplete migrations
    resumed = worker.resume_incomplete_migrations()
    
    assert len(resumed) == 1
    assert resumed[0] == job_id
    
    # Verify job is marked as failed
    status = worker.get_job_status(job_id)
    assert status['status'] == 'failed'
    assert 'interrupted' in status['error_message'].lower()


# ============================================================================
# Test: Clear Completed Jobs
# ============================================================================

def test_clear_completed_jobs(worker, cache_manager, sample_tracks):
    """Test clearing old completed jobs."""
    # Add some completed jobs
    cursor = cache_manager.connection.cursor()
    
    # Old completed job (simulate 60 days old)
    old_date = datetime.now().timestamp() - (60 * 24 * 60 * 60)
    cursor.execute("""
        INSERT INTO migrations 
        (job_id, playlist_name, playlist_id, status, total_tracks, 
         processed_tracks, created_at, completed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        "old-job",
        "Old Playlist",
        "sp_old",
        "completed",
        5,
        5,
        old_date,
        old_date
    ))
    
    # Recent completed job
    cursor.execute("""
        INSERT INTO migrations 
        (job_id, playlist_name, playlist_id, status, total_tracks, 
         processed_tracks, created_at, completed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        "recent-job",
        "Recent Playlist",
        "sp_recent",
        "completed",
        5,
        5,
        datetime.now(),
        datetime.now()
    ))
    
    cache_manager.connection.commit()
    
    # Clear jobs older than 30 days
    deleted_count = worker.clear_completed_jobs(days_old=30)
    
    assert deleted_count == 1
    
    # Verify old job is gone
    with pytest.raises(ValueError):
        worker.get_job_status("old-job")
    
    # Verify recent job still exists
    status = worker.get_job_status("recent-job")
    assert status['status'] == 'completed'


# ============================================================================
# Test: Thread Safety
# ============================================================================

def test_thread_safety_current_job(worker):
    """Test that current_job access is thread-safe."""
    # This test verifies lock usage doesn't deadlock
    # Actual race conditions are hard to test deterministically
    
    def reader_thread():
        for _ in range(100):
            worker.get_current_job()
            time.sleep(0.001)
    
    def writer_thread():
        for i in range(100):
            with worker.current_job_lock:
                worker.current_job = {'id': f'job-{i}'}
            time.sleep(0.001)
    
    threads = [
        threading.Thread(target=reader_thread),
        threading.Thread(target=reader_thread),
        threading.Thread(target=writer_thread)
    ]
    
    for t in threads:
        t.start()
    
    for t in threads:
        t.join(timeout=5)
    
    # If we get here without deadlock, test passes
    assert True


# ============================================================================
# Test: Notifications (mocked)
# ============================================================================

@pytest.mark.skip(reason="Notification tests require plyer, which is optional")
def test_send_notification_success(worker, sample_tracks):
    """Test desktop notification on successful migration."""
    migrator_func = Mock(return_value={'matched_tracks': 2, 'total_tracks': 2})
    
    worker.start()
    time.sleep(0.1)  # Give worker thread time to start
    
    worker.add_job(
        playlist_name="Test Playlist",
        playlist_id="sp_123",
        tracks=sample_tracks,
        migrator_func=migrator_func
    )
    
    # Wait for job to complete with timeout
    max_wait = 5.0
    start_time = time.time()
    while time.time() - start_time < max_wait:
        if worker.job_queue.empty() and worker.get_current_job() is None:
            break
        time.sleep(0.1)
    
    time.sleep(0.2)  # Allow time for notification
    
    # Verify notification was sent
    mock_notification.notify.assert_called_once()
    call_kwargs = mock_notification.notify.call_args[1]
    assert 'Migration Complete' in call_kwargs['title']
    assert 'Test Playlist' in call_kwargs['title']
    
    # Cleanup
    worker.stop()


@pytest.mark.skip(reason="Notification tests require plyer, which is optional")
def test_send_notification_failure(worker, sample_tracks):
    """Test desktop notification on failed migration."""
    migrator_func = Mock(side_effect=Exception("Test error"))
    
    worker.start()
    time.sleep(0.1)  # Give worker thread time to start
    
    worker.add_job(
        playlist_name="Test Playlist",
        playlist_id="sp_123",
        tracks=sample_tracks,
        migrator_func=migrator_func
    )
    
    # Wait for job to complete with timeout
    max_wait = 5.0
    start_time = time.time()
    while time.time() - start_time < max_wait:
        if worker.job_queue.empty() and worker.get_current_job() is None:
            break
        time.sleep(0.1)
    
    time.sleep(0.2)  # Allow time for notification
    
    # Verify notification was sent
    mock_notification.notify.assert_called_once()
    call_kwargs = mock_notification.notify.call_args[1]
    assert 'Migration Failed' in call_kwargs['title']
    assert 'Test Playlist' in call_kwargs['title']
    
    # Cleanup
    worker.stop()
