"""Tests for MigrationManager class.

Comprehensive test suite covering:
- Initialization and dependency injection
- Lifecycle management (start/stop)
- Playlist migration orchestration
- Status and control methods
- Error handling and logging
- Thread safety
"""

import pytest
import time
from unittest.mock import Mock, MagicMock, patch, call
from datetime import datetime

from src.migrators.migration_manager import MigrationManager


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_spotify_client():
    """Mock Spotify client."""
    client = Mock()
    client.current_user_playlists = Mock(return_value={'items': []})
    return client


@pytest.fixture
def mock_ytmusic_client():
    """Mock YouTube Music client."""
    client = Mock()
    client.create_playlist = Mock(return_value='yt_playlist_123')
    client.add_playlist_items = Mock()
    return client


@pytest.fixture
def mock_cache_manager():
    """Mock CacheManager with database connection."""
    cache = Mock()
    cache.db_path = ':memory:'
    cache.connection = Mock()
    cache.connection.cursor = Mock(return_value=Mock())
    cache.connection.__enter__ = Mock(return_value=cache.connection)
    cache.connection.__exit__ = Mock(return_value=False)
    return cache


@pytest.fixture
def manager(mock_spotify_client, mock_ytmusic_client, mock_cache_manager):
    """Create MigrationManager instance with mocked dependencies."""
    with patch('src.migrators.migration_manager.BackgroundWorker') as mock_worker_cls, \
         patch('src.migrators.migration_manager.PlaylistMigrator'), \
         patch('src.migrators.migration_manager.YouTubeSearcher'), \
         patch('src.migrators.migration_manager.TrackMatcher'), \
         patch('src.migrators.migration_manager.SpotifyFetcher'), \
         patch('src.migrators.migration_manager.Notifier'), \
         patch('src.migrators.migration_manager.RateLimiter'):
        
        # Setup mock worker instance
        mock_worker = Mock()
        mock_worker.is_running = Mock()
        mock_worker.is_running.is_set = Mock(return_value=True)
        mock_worker.job_queue = Mock()
        mock_worker.job_queue.qsize = Mock(return_value=0)
        mock_worker.start = Mock()
        mock_worker.stop = Mock()
        mock_worker.add_job = Mock(return_value='job-123')
        mock_worker.get_current_job = Mock(return_value=None)
        mock_worker.get_all_jobs = Mock(return_value=[])
        mock_worker.resume_incomplete_migrations = Mock(return_value=[])
        mock_worker.clear_completed_jobs = Mock(return_value=0)
        mock_worker_cls.return_value = mock_worker
        
        manager = MigrationManager(
            spotify_client=mock_spotify_client,
            ytmusic_client=mock_ytmusic_client,
            cache_manager=mock_cache_manager
        )
        
        # Store mock worker for test access
        manager._mock_worker = mock_worker
        
        yield manager


# ============================================================================
# Test: Initialization
# ============================================================================

def test_init_success(mock_spotify_client, mock_ytmusic_client, mock_cache_manager):
    """Test successful initialization of MigrationManager."""
    with patch('src.migrators.migration_manager.BackgroundWorker'), \
         patch('src.migrators.migration_manager.PlaylistMigrator'), \
         patch('src.migrators.migration_manager.YouTubeSearcher'), \
         patch('src.migrators.migration_manager.TrackMatcher'), \
         patch('src.migrators.migration_manager.SpotifyFetcher'), \
         patch('src.migrators.migration_manager.Notifier'), \
         patch('src.migrators.migration_manager.RateLimiter'):
        
        manager = MigrationManager(
            spotify_client=mock_spotify_client,
            ytmusic_client=mock_ytmusic_client,
            cache_manager=mock_cache_manager
        )
        
        assert manager.spotify_client == mock_spotify_client
        assert manager.ytmusic_client == mock_ytmusic_client
        assert manager.cache_manager == mock_cache_manager
        assert manager.rate_limiter is not None
        assert manager.youtube_searcher is not None
        assert manager.track_matcher is not None
        assert manager.playlist_migrator is not None
        assert manager.background_worker is not None
        assert manager.notifier is not None
        assert manager.spotify_fetcher is not None
        assert manager._paused is False
        assert manager._error_log == []


def test_init_missing_spotify_client(mock_ytmusic_client, mock_cache_manager):
    """Test initialization fails with None spotify_client."""
    with pytest.raises(ValueError, match="spotify_client cannot be None"):
        MigrationManager(
            spotify_client=None,
            ytmusic_client=mock_ytmusic_client,
            cache_manager=mock_cache_manager
        )


def test_init_missing_ytmusic_client(mock_spotify_client, mock_cache_manager):
    """Test initialization fails with None ytmusic_client."""
    with pytest.raises(ValueError, match="ytmusic_client cannot be None"):
        MigrationManager(
            spotify_client=mock_spotify_client,
            ytmusic_client=None,
            cache_manager=mock_cache_manager
        )


def test_init_missing_cache_manager(mock_spotify_client, mock_ytmusic_client):
    """Test initialization fails with None cache_manager."""
    with pytest.raises(ValueError, match="cache_manager cannot be None"):
        MigrationManager(
            spotify_client=mock_spotify_client,
            ytmusic_client=mock_ytmusic_client,
            cache_manager=None
        )


# ============================================================================
# Test: Lifecycle (start/stop)
# ============================================================================

def test_start(manager):
    """Test starting the migration manager."""
    manager._mock_worker.resume_incomplete_migrations.return_value = []
    
    manager.start()
    
    manager._mock_worker.start.assert_called_once()
    manager._mock_worker.resume_incomplete_migrations.assert_called_once()


def test_start_with_incomplete_migrations(manager):
    """Test start resumes incomplete migrations."""
    manager._mock_worker.resume_incomplete_migrations.return_value = ['job-1', 'job-2']
    
    manager.start()
    
    manager._mock_worker.resume_incomplete_migrations.assert_called_once()


def test_stop(manager):
    """Test stopping the migration manager."""
    manager._mock_worker.get_all_jobs.return_value = [
        {'status': 'completed'},
        {'status': 'completed'},
        {'status': 'failed'}
    ]
    
    manager.stop()
    
    manager._mock_worker.stop.assert_called_once_with(timeout=30.0)


def test_stop_with_custom_timeout(manager):
    """Test stop with custom timeout."""
    manager._mock_worker.get_all_jobs.return_value = []
    
    manager.stop(timeout=60.0)
    
    manager._mock_worker.stop.assert_called_once_with(timeout=60.0)


# ============================================================================
# Test: migrate_playlists
# ============================================================================

def test_migrate_playlists_success(manager):
    """Test successful playlist migration queueing."""
    playlists = [
        {'id': 'sp_123', 'name': 'Playlist 1', 'tracks': [{'name': 'Track 1'}]},
        {'id': 'sp_456', 'name': 'Playlist 2', 'tracks': [{'name': 'Track 2'}]}
    ]
    
    manager._mock_worker.add_job.side_effect = ['job-1', 'job-2']
    
    job_ids = manager.migrate_playlists(playlists)
    
    assert len(job_ids) == 2
    assert job_ids == ['job-1', 'job-2']
    assert manager._mock_worker.add_job.call_count == 2


def test_migrate_playlists_with_progress_callback(manager):
    """Test migrate_playlists forwards progress callback."""
    playlists = [
        {'id': 'sp_123', 'name': 'Test Playlist', 'tracks': [{'name': 'Track 1'}]}
    ]
    
    progress_callback = Mock()
    
    manager.migrate_playlists(playlists, progress_callback=progress_callback)
    
    # Verify progress wrapper was created
    manager._mock_worker.add_job.assert_called_once()
    call_kwargs = manager._mock_worker.add_job.call_args[1]
    assert 'progress_callback' in call_kwargs
    assert callable(call_kwargs['progress_callback'])


def test_migrate_playlists_fetches_tracks(manager):
    """Test migrate_playlists fetches tracks when not provided."""
    playlists = [
        {'id': 'sp_123', 'name': 'Test Playlist'}  # No tracks
    ]
    
    manager.spotify_fetcher.get_playlist_tracks = Mock(return_value=[
        {'name': 'Track 1'},
        {'name': 'Track 2'}
    ])
    
    job_ids = manager.migrate_playlists(playlists)
    
    manager.spotify_fetcher.get_playlist_tracks.assert_called_once_with('sp_123')
    assert len(job_ids) == 1


def test_migrate_playlists_empty_list(manager):
    """Test migrate_playlists with empty list raises error."""
    with pytest.raises(ValueError, match="playlists list cannot be empty"):
        manager.migrate_playlists([])


def test_migrate_playlists_not_started(manager):
    """Test migrate_playlists fails if manager not started."""
    manager._mock_worker.is_running.is_set.return_value = False
    
    playlists = [{'id': 'sp_123', 'name': 'Test'}]
    
    with pytest.raises(RuntimeError, match="MigrationManager is not started"):
        manager.migrate_playlists(playlists)


def test_migrate_playlists_paused(manager):
    """Test migrate_playlists fails if paused."""
    manager._paused = True
    
    playlists = [{'id': 'sp_123', 'name': 'Test', 'tracks': []}]
    
    with pytest.raises(RuntimeError, match="Migrations are paused"):
        manager.migrate_playlists(playlists)


def test_migrate_playlists_invalid_structure(manager):
    """Test migrate_playlists skips invalid playlist structures."""
    playlists = [
        {'name': 'No ID'},  # Missing 'id'
        {'id': 'sp_123'},   # Missing 'name'
        {'id': 'sp_456', 'name': 'Valid', 'tracks': [{'name': 'Track'}]}
    ]
    
    job_ids = manager.migrate_playlists(playlists)
    
    # Only valid playlist should be queued
    assert len(job_ids) == 1


def test_migrate_playlists_empty_tracks(manager):
    """Test migrate_playlists skips playlists with no tracks (when fetched)."""
    playlists = [
        {'id': 'sp_123', 'name': 'Empty'}  # No tracks provided
    ]
    
    # Fetcher returns empty list
    manager.spotify_fetcher.get_playlist_tracks = Mock(return_value=[])
    
    job_ids = manager.migrate_playlists(playlists)
    
    assert len(job_ids) == 0


def test_migrate_playlists_error_handling(manager):
    """Test migrate_playlists handles errors gracefully."""
    playlists = [
        {'id': 'sp_123', 'name': 'Test'}
    ]
    
    manager.spotify_fetcher.get_playlist_tracks = Mock(
        side_effect=Exception("Fetch error")
    )
    
    job_ids = manager.migrate_playlists(playlists)
    
    # Job should not be queued due to error
    assert len(job_ids) == 0
    
    # Error should be logged
    errors = manager.get_error_log()
    assert len(errors) == 1
    assert errors[0]['playlist_name'] == 'Test'
    assert 'Fetch error' in errors[0]['error']


# ============================================================================
# Test: get_migration_status
# ============================================================================

def test_get_migration_status(manager):
    """Test get_migration_status returns correct status."""
    manager._mock_worker.get_all_jobs.return_value = [
        {'status': 'completed'},
        {'status': 'completed'},
        {'status': 'failed'},
        {'status': 'queued'},
        {'status': 'in_progress'}
    ]
    manager._mock_worker.get_current_job.return_value = {
        'id': 'job-1',
        'playlist_name': 'Test'
    }
    manager._mock_worker.job_queue.qsize.return_value = 3
    
    status = manager.get_migration_status()
    
    assert status['total_jobs'] == 5
    assert status['completed_jobs'] == 2
    assert status['failed_jobs'] == 1
    assert status['queued_jobs'] == 1
    assert status['in_progress_jobs'] == 1
    assert status['current_job'] == {'id': 'job-1', 'playlist_name': 'Test'}
    assert status['queue_size'] == 3
    assert status['is_paused'] is False
    assert status['error_count'] == 0
    assert status['is_running'] is True


def test_get_migration_status_no_current_job(manager):
    """Test get_migration_status with no current job."""
    manager._mock_worker.get_all_jobs.return_value = []
    manager._mock_worker.get_current_job.return_value = None
    
    status = manager.get_migration_status()
    
    assert status['current_job'] is None
    assert status['total_jobs'] == 0


# ============================================================================
# Test: pause/resume
# ============================================================================

def test_pause_migrations(manager):
    """Test pausing migrations."""
    manager.pause_migrations()
    
    assert manager._paused is True


def test_pause_migrations_already_paused(manager):
    """Test pausing when already paused."""
    manager._paused = True
    
    manager.pause_migrations()  # Should not raise
    
    assert manager._paused is True


def test_pause_migrations_not_started(manager):
    """Test pause fails if manager not started."""
    manager._mock_worker.is_running.is_set.return_value = False
    
    with pytest.raises(RuntimeError, match="MigrationManager is not started"):
        manager.pause_migrations()


def test_resume_migrations(manager):
    """Test resuming migrations."""
    manager._paused = True
    
    manager.resume_migrations()
    
    assert manager._paused is False


def test_resume_migrations_not_paused(manager):
    """Test resuming when not paused."""
    manager._paused = False
    
    manager.resume_migrations()  # Should not raise
    
    assert manager._paused is False


def test_resume_migrations_not_started(manager):
    """Test resume fails if manager not started."""
    manager._mock_worker.is_running.is_set.return_value = False
    
    with pytest.raises(RuntimeError, match="MigrationManager is not started"):
        manager.resume_migrations()


# ============================================================================
# Test: cancel_all
# ============================================================================

def test_cancel_all_with_force(manager):
    """Test cancelling all migrations with force=True."""
    manager._mock_worker.job_queue.qsize.return_value = 5
    
    # Setup mock context manager
    mock_mutex = MagicMock()
    mock_queue = Mock()
    mock_queue.clear = Mock()
    manager._mock_worker.job_queue.mutex = mock_mutex
    manager._mock_worker.job_queue.queue = mock_queue
    
    count = manager.cancel_all(force=True)
    
    assert count == 5
    mock_queue.clear.assert_called_once()


def test_cancel_all_without_force(manager):
    """Test cancel_all without force raises ValueError."""
    with pytest.raises(ValueError, match="Cancellation requires confirmation"):
        manager.cancel_all(force=False)


def test_cancel_all_empty_queue(manager):
    """Test cancel_all with empty queue."""
    manager._mock_worker.job_queue.qsize.return_value = 0
    
    count = manager.cancel_all(force=True)
    
    assert count == 0


def test_cancel_all_not_started(manager):
    """Test cancel_all fails if manager not started."""
    manager._mock_worker.is_running.is_set.return_value = False
    
    with pytest.raises(RuntimeError, match="MigrationManager is not started"):
        manager.cancel_all(force=True)


# ============================================================================
# Test: Error log
# ============================================================================

def test_get_error_log(manager):
    """Test getting error log."""
    manager._error_log = [
        {'playlist_id': 'sp_1', 'error': 'Error 1'},
        {'playlist_id': 'sp_2', 'error': 'Error 2'}
    ]
    
    errors = manager.get_error_log()
    
    assert len(errors) == 2
    assert errors[0]['playlist_id'] == 'sp_1'
    assert errors[1]['playlist_id'] == 'sp_2'


def test_get_error_log_empty(manager):
    """Test getting empty error log."""
    errors = manager.get_error_log()
    
    assert errors == []


def test_clear_error_log(manager):
    """Test clearing error log."""
    manager._error_log = [
        {'playlist_id': 'sp_1', 'error': 'Error 1'},
        {'playlist_id': 'sp_2', 'error': 'Error 2'}
    ]
    
    count = manager.clear_error_log()
    
    assert count == 2
    assert len(manager._error_log) == 0


def test_clear_error_log_empty(manager):
    """Test clearing empty error log."""
    count = manager.clear_error_log()
    
    assert count == 0


# ============================================================================
# Test: Convenience methods
# ============================================================================

def test_get_all_jobs(manager):
    """Test get_all_jobs wrapper."""
    manager._mock_worker.get_all_jobs.return_value = [
        {'job_id': 'job-1', 'status': 'completed'},
        {'job_id': 'job-2', 'status': 'queued'}
    ]
    
    jobs = manager.get_all_jobs()
    
    assert len(jobs) == 2
    manager._mock_worker.get_all_jobs.assert_called_once_with(status=None, limit=100)


def test_get_all_jobs_filtered(manager):
    """Test get_all_jobs with status filter."""
    manager._mock_worker.get_all_jobs.return_value = [
        {'job_id': 'job-1', 'status': 'completed'}
    ]
    
    jobs = manager.get_all_jobs(status='completed', limit=50)
    
    manager._mock_worker.get_all_jobs.assert_called_once_with(status='completed', limit=50)


def test_clear_old_jobs(manager):
    """Test clear_old_jobs wrapper."""
    manager._mock_worker.clear_completed_jobs.return_value = 10
    
    count = manager.clear_old_jobs()
    
    assert count == 10
    manager._mock_worker.clear_completed_jobs.assert_called_once_with(days_old=30)


def test_clear_old_jobs_custom_days(manager):
    """Test clear_old_jobs with custom days."""
    manager._mock_worker.clear_completed_jobs.return_value = 5
    
    count = manager.clear_old_jobs(days_old=7)
    
    assert count == 5
    manager._mock_worker.clear_completed_jobs.assert_called_once_with(days_old=7)


# ============================================================================
# Test: Thread safety
# ============================================================================

def test_thread_safety_pause_state(manager):
    """Test thread-safe access to pause state."""
    import threading
    
    def toggle_pause():
        for _ in range(100):
            manager.pause_migrations()
            manager.resume_migrations()
    
    threads = [threading.Thread(target=toggle_pause) for _ in range(3)]
    
    for t in threads:
        t.start()
    
    for t in threads:
        t.join(timeout=5)
    
    # If we get here without deadlock, test passes
    assert True


def test_thread_safety_error_log(manager):
    """Test thread-safe access to error log."""
    import threading
    
    def add_errors():
        for i in range(50):
            manager._error_lock.acquire()
            manager._error_log.append({'error': f'Error {i}'})
            manager._error_lock.release()
    
    threads = [threading.Thread(target=add_errors) for _ in range(3)]
    
    for t in threads:
        t.start()
    
    for t in threads:
        t.join(timeout=5)
    
    # Should have 150 errors (50 * 3 threads)
    assert len(manager._error_log) == 150


# ============================================================================
# Test: Resume wiring (contract §4.3)
# ============================================================================

def test_start_hands_migrator_to_resume(manager):
    """start() must give the worker a migrator so interrupted jobs continue
    instead of being marked failed."""
    manager.start()
    
    kwargs = manager._mock_worker.resume_incomplete_migrations.call_args.kwargs
    assert kwargs['migrator_func'] is manager.playlist_migrator.migrate_playlist
    assert callable(kwargs['progress_callback'])


def test_worker_gets_default_migrator_at_init(manager):
    assert manager._mock_worker.default_migrator_func is manager.playlist_migrator.migrate_playlist


def test_migrate_playlists_caches_prefetched_tracks_for_resume(manager, mock_cache_manager):
    """Pre-fetched tracks are not cached by SpotifyFetcher, so the manager
    stores them - a resume after restart reloads tracks from that table."""
    tracks = [{'id': 't1', 'name': 'Track 1', 'artists': []}]
    manager.migrate_playlists([{'id': 'sp_123', 'name': 'P', 'tracks': tracks}])
    
    mock_cache_manager.cache_tracks.assert_called_once_with(tracks, 'sp_123')


def test_migrate_playlists_survives_cache_failure(manager, mock_cache_manager):
    mock_cache_manager.cache_tracks.side_effect = Exception("disk full")
    job_ids = manager.migrate_playlists([{'id': 'sp_123', 'name': 'P', 'tracks': [{'name': 'T'}]}])
    assert job_ids == ['job-123']


def test_resume_progress_wrapper_forwards_to_attached_callback(manager):
    """A UI callback attached after start() still receives progress for resumed jobs."""
    wrapper = manager._make_resume_progress_wrapper()
    manager._mock_worker.get_current_job.return_value = {'playlist_name': 'Resumed'}
    
    wrapper(1, 2, 'Song')  # no callback attached yet: must not raise
    
    callback = Mock()
    manager.set_progress_callback(callback)
    wrapper(2, 2, 'Song', 1, 1)
    callback.assert_called_once_with('Resumed', 2, 2, 'Song', 1, 1)


# ============================================================================
# Test: rate-limit policy wiring and throttle visibility
# ============================================================================

def test_rate_limiter_constructed_with_sustained_rate_policy(
    mock_spotify_client, mock_ytmusic_client, mock_cache_manager
):
    """The limiter gets a paced policy (no Data-API daily cap), persists to the
    app DB, and reports throttle changes back to the manager."""
    with patch('src.migrators.migration_manager.BackgroundWorker'), \
         patch('src.migrators.migration_manager.PlaylistMigrator'), \
         patch('src.migrators.migration_manager.YouTubeSearcher'), \
         patch('src.migrators.migration_manager.TrackMatcher'), \
         patch('src.migrators.migration_manager.SpotifyFetcher'), \
         patch('src.migrators.migration_manager.Notifier'), \
         patch('src.migrators.migration_manager.RateLimiter') as mock_limiter_cls:
        mock_cache_manager.db_path = '/tmp/some/cache.db'
        manager = MigrationManager(mock_spotify_client, mock_ytmusic_client, mock_cache_manager)

    kwargs = mock_limiter_cls.call_args.kwargs
    assert kwargs['daily_limit'] is None
    assert kwargs['per_minute_limit'] == MigrationManager.RATE_PER_MINUTE_LIMIT
    assert kwargs['min_interval'] == MigrationManager.RATE_MIN_INTERVAL_SECONDS
    assert kwargs['jitter'] == MigrationManager.RATE_JITTER_SECONDS
    assert kwargs['db_path'] == '/tmp/some/cache.db'
    assert kwargs['on_throttle'] == manager._on_throttle_state_change
    assert 15000 not in kwargs.values()


def test_single_rate_limiter_shared_by_all_api_paths(
    mock_spotify_client, mock_ytmusic_client, mock_cache_manager
):
    """Every API call path (fetcher, searcher, migrator) gets the same limiter."""
    with patch('src.migrators.migration_manager.BackgroundWorker'), \
         patch('src.migrators.migration_manager.PlaylistMigrator') as migrator_cls, \
         patch('src.migrators.migration_manager.YouTubeSearcher') as searcher_cls, \
         patch('src.migrators.migration_manager.TrackMatcher'), \
         patch('src.migrators.migration_manager.SpotifyFetcher') as fetcher_cls, \
         patch('src.migrators.migration_manager.Notifier'), \
         patch('src.migrators.migration_manager.RateLimiter'):
        manager = MigrationManager(mock_spotify_client, mock_ytmusic_client, mock_cache_manager)

    assert searcher_cls.call_args.kwargs['rate_limiter'] is manager.rate_limiter
    assert migrator_cls.call_args.kwargs['rate_limiter'] is manager.rate_limiter
    assert fetcher_cls.call_args.kwargs['rate_limiter'] is manager.rate_limiter


def test_real_rate_limiter_persists_in_cache_db(
    mock_spotify_client, mock_ytmusic_client, tmp_path
):
    """With a real limiter, the manager's limiter writes its own table into the
    same SQLite file CacheManager uses, without CacheManager's involvement."""
    import sqlite3
    cache = Mock()
    cache.db_path = str(tmp_path / 'cache.db')
    with patch('src.migrators.migration_manager.BackgroundWorker'), \
         patch('src.migrators.migration_manager.PlaylistMigrator'), \
         patch('src.migrators.migration_manager.YouTubeSearcher'), \
         patch('src.migrators.migration_manager.TrackMatcher'), \
         patch('src.migrators.migration_manager.SpotifyFetcher'), \
         patch('src.migrators.migration_manager.Notifier'):
        manager = MigrationManager(mock_spotify_client, mock_ytmusic_client, cache)
        manager.rate_limiter.record_request()
        manager.rate_limiter.close()

    with sqlite3.connect(cache.db_path) as conn:
        rows = dict(conn.execute("SELECT key, value FROM rate_limit_state").fetchall())
    assert rows['daily_operations'] == '1'


def test_get_throttle_state_delegates_to_limiter(manager):
    state = {'throttled': True, 'reason': 'rate', 'until': 123.0, 'message': 'Rate limited - throttled until 00:02'}
    manager.rate_limiter.get_throttle_state = Mock(return_value=state)
    assert manager.get_throttle_state() == state


def test_get_throttle_state_falls_back_to_last_reported(manager):
    """If the limiter cannot answer, the last state it reported is returned."""
    manager.rate_limiter.get_throttle_state = Mock(return_value=None)
    assert manager.get_throttle_state() == {
        'throttled': False, 'reason': None, 'until': None, 'message': ''
    }
    manager._on_throttle_state_change({'throttled': True, 'reason': 'quota', 'until': 5.0, 'message': 'q'})
    assert manager.get_throttle_state()['reason'] == 'quota'


def test_throttle_callback_forwarded_and_errors_contained(manager):
    callback = Mock(side_effect=RuntimeError('ui broke'))
    manager.set_throttle_callback(callback)
    state = {'throttled': True, 'reason': 'rate', 'until': 1.0, 'message': 'm'}
    manager._on_throttle_state_change(state)  # must not raise
    callback.assert_called_once_with(state)
    manager.set_throttle_callback(None)
    manager._on_throttle_state_change({'throttled': False, 'reason': None, 'until': None, 'message': ''})
    callback.assert_called_once()


def test_migration_status_includes_throttle_state(manager):
    manager.rate_limiter.get_throttle_state = Mock(return_value={
        'throttled': True, 'reason': 'quota', 'until': 99.0, 'message': 'Quota exhausted - throttled until 00:01'
    })
    status = manager.get_migration_status()
    assert status['throttle']['throttled'] is True
    assert status['throttle']['reason'] == 'quota'


def test_stop_closes_rate_limiter(manager):
    manager.rate_limiter.close = Mock()
    manager.stop()
    manager.rate_limiter.close.assert_called_once()


def test_stop_survives_rate_limiter_close_failure(manager):
    manager.rate_limiter.close = Mock(side_effect=RuntimeError('db gone'))
    manager.stop()  # must not raise


# ---------------------------------------------------------------------------
# get_batch_progress: aggregate over one run's job rows (CONTEXT_CONTRACT §4.3,
# multi-playlist completion). Read-only; paused_auth is never terminal.
# ---------------------------------------------------------------------------

def _row(status, progress, total, matched=0, failed=0, ids=None, name='P', error=None):
    return {
        'status': status, 'progress': progress, 'total': total,
        'playlist_name': name, 'created_at': None, 'started_at': None,
        'completed_at': None, 'error_message': error,
        'youtube_playlist_ids': list(ids or []), 'added_tracks': 0,
        'last_added_index': 0, 'matched_tracks': matched, 'failed_tracks': failed,
    }


class TestGetBatchProgress:

    def _manager_with_rows(self, manager, rows):
        rows_by_id = dict(rows)

        def get_job_status(job_id):
            if job_id not in rows_by_id:
                raise ValueError(f"Job {job_id} not found")
            return rows_by_id[job_id]

        manager.background_worker.get_job_status = Mock(side_effect=get_job_status)
        manager.get_throttle_state = Mock(return_value={
            'throttled': False, 'reason': None, 'until': None, 'message': ''
        })
        return manager

    def test_sums_across_jobs_and_is_not_done_mid_run(self, manager):
        self._manager_with_rows(manager, [
            ('j1', _row('completed', 50, 50, 48, 2, ids=['a'], name='Rock')),
            ('j2', _row('in_progress', 10, 30, 9, 1, ids=['b'], name='Pop')),
            ('j3', _row('queued', 0, 20, name='Jazz')),
        ])
        b = manager.get_batch_progress(['j1', 'j2', 'j3'])
        assert b['total_jobs'] == 3
        assert (b['completed_jobs'], b['in_progress_jobs'], b['queued_jobs']) == (1, 1, 1)
        assert b['total_tracks'] == 100
        assert b['processed_tracks'] == 60
        assert b['matched_tracks'] == 57
        assert b['failed_tracks'] == 3
        assert b['playlists_created'] == 2
        assert b['all_done'] is False
        assert b['auth_required'] is False
        assert [j['playlist_name'] for j in b['jobs']] == ['Rock', 'Pop', 'Jazz']
        assert b['jobs'][0]['youtube_playlist_ids'] == ['a']

    def test_all_done_when_every_job_completed_or_failed(self, manager):
        self._manager_with_rows(manager, [
            ('j1', _row('completed', 50, 50, 50, 0, ids=['a', 'b'])),
            ('j2', _row('failed', 12, 30, 11, 1, error='boom')),
        ])
        b = manager.get_batch_progress(['j1', 'j2'])
        assert b['all_done'] is True
        assert b['failed_jobs'] == 1
        assert b['processed_tracks'] == 62   # completed counts full total
        assert b['playlists_created'] == 2   # the sharded one
        assert b['jobs'][1]['error_message'] == 'boom'

    def test_paused_auth_is_not_done_and_flags_auth_required(self, manager):
        self._manager_with_rows(manager, [
            ('j1', _row('completed', 50, 50, 50, 0)),
            ('j2', _row('paused_auth', 10, 30, 9, 1)),
        ])
        b = manager.get_batch_progress(['j1', 'j2'])
        assert b['all_done'] is False
        assert b['paused_auth_jobs'] == 1
        assert b['auth_required'] is True

    def test_unknown_job_ids_are_skipped(self, manager):
        self._manager_with_rows(manager, [('j1', _row('completed', 5, 5, 5, 0))])
        b = manager.get_batch_progress(['j1', 'missing'])
        assert b['total_jobs'] == 1
        assert b['all_done'] is True

    def test_empty_job_list_is_never_done(self, manager):
        self._manager_with_rows(manager, [])
        b = manager.get_batch_progress([])
        assert b['total_jobs'] == 0
        assert b['all_done'] is False
        assert b['total_tracks'] == 0

    def test_includes_throttle_state(self, manager):
        self._manager_with_rows(manager, [('j1', _row('in_progress', 1, 5))])
        manager.get_throttle_state = Mock(return_value={
            'throttled': True, 'reason': 'rate', 'until': 123.0, 'message': 'slow'
        })
        b = manager.get_batch_progress(['j1'])
        assert b['throttle']['throttled'] is True
        assert b['all_done'] is False
