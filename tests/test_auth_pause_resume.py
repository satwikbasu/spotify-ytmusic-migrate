"""Auth-failure handling for long YouTube Music jobs (contract §4.3, §4.1 seam).

When the browser-cookie session rotates mid-job, the engine must not silently
die or record every remaining track as "no match". These tests cover:

- ``YouTubeAuthError`` is raised (never swallowed to ``[]``) by the searcher
  on 401/403 and on a silent sign-out, and by the migrator's add/create path.
- ``BackgroundWorker`` parks the job as ``paused_auth`` (never ``failed``),
  keeps the resume state, and fires the notifier.
- ``set_client()`` swaps the client without rebuilding anything.
- ``MigrationManager.reauthenticate_youtube()`` swaps the client and resumes
  the paused job from exactly where it stopped.
- Status reports ``paused_auth`` / ``auth_required``.
"""

import json
import time
from datetime import datetime
from unittest.mock import Mock, patch

import pytest
from ytmusicapi.exceptions import YTMusicServerError, YTMusicUserError

from src.matchers.track_matcher import TrackMatcher
from src.migrators.migration_manager import MigrationManager
from src.migrators.playlist_migrator import PlaylistMigrator
from src.searchers.youtube_searcher import YouTubeSearcher
from src.utils.background_worker import BackgroundWorker
from src.utils.cache_manager import CacheManager
from src.utils.errors import YouTubeAuthError, is_auth_error
from src.utils.notifier import Notifier
from src.utils.rate_limiter import RateLimiter


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_rate_limiter():
    limiter = Mock(spec=RateLimiter)
    limiter.check_limit.return_value = True
    return limiter


@pytest.fixture
def signed_in_client():
    """A YTMusic mock whose identity check succeeds."""
    client = Mock()
    client.get_account_info.return_value = {'accountName': 'Test User', 'channelHandle': '@test'}
    client.create_playlist.return_value = 'PL_NEW'
    client.add_playlist_items.return_value = {'status': 'STATUS_SUCCEEDED'}
    return client


@pytest.fixture
def searcher(signed_in_client, mock_rate_limiter):
    return YouTubeSearcher(signed_in_client, mock_rate_limiter)


@pytest.fixture
def cache_manager(tmp_path):
    return CacheManager(str(tmp_path / "auth_pause.db"))


@pytest.fixture
def worker(cache_manager):
    w = BackgroundWorker(cache_manager)
    w.notifier = Mock(spec=Notifier)
    return w


@pytest.fixture
def tracks():
    return [
        {'id': f'sp{i}', 'name': f'Song {i}', 'artists': [f'Artist {i}'],
         'album': 'Album', 'duration_ms': 200000}
        for i in range(1, 7)
    ]


def _yt_result(i):
    return {'videoId': f'vid{i}', 'title': f'Song {i}',
            'artists': [{'name': f'Artist {i}'}], 'album': {'name': 'Album'},
            'duration': '3:20'}


def _wait_for_status(worker, job_id, wanted, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if worker.get_job_status(job_id)['status'] in wanted:
            return worker.get_job_status(job_id)
        time.sleep(0.02)
    return worker.get_job_status(job_id)


HTTP_401 = YTMusicServerError("Server returned HTTP 401: Unauthorized.\nRequest contains an invalid argument.")
HTTP_403 = YTMusicServerError("Server returned HTTP 403: Forbidden.\nThe caller does not have permission.")
HTTP_429 = YTMusicServerError("Server returned HTTP 429: Too Many Requests.")
NO_AUTH = YTMusicUserError("Please provide authentication before using this function")


# ============================================================================
# is_auth_error classification
# ============================================================================

def test_is_auth_error_recognises_401_403_and_missing_auth():
    assert is_auth_error(HTTP_401)
    assert is_auth_error(HTTP_403)
    assert is_auth_error(NO_AUTH)
    assert is_auth_error(YouTubeAuthError("x"))


def test_is_auth_error_leaves_429_and_other_errors_to_the_rate_limiter():
    assert not is_auth_error(HTTP_429)
    assert not is_auth_error(YTMusicServerError("Server returned HTTP 500: Internal Server Error."))
    assert not is_auth_error(ConnectionError("boom"))
    assert not is_auth_error(ValueError("not ytmusic"))


def test_errors_module_has_no_in_repo_imports():
    """It must be importable from every layer without cycles."""
    import src.utils.errors as errors
    src_imports = [n for n in dir(errors) if n.startswith('src')]
    assert src_imports == []


# ============================================================================
# YouTubeSearcher: 401/403 raise, never swallowed to []
# ============================================================================

@patch('src.searchers.youtube_searcher.time.sleep')
@pytest.mark.parametrize('exc', [HTTP_401, HTTP_403, NO_AUTH], ids=['401', '403', 'no-auth'])
def test_search_auth_failure_raises_not_empty(mock_sleep, searcher, signed_in_client, exc):
    signed_in_client.search.side_effect = exc

    with pytest.raises(YouTubeAuthError) as info:
        searcher.search_track("Song", ["Artist"])

    assert info.value.cause is exc
    # No retries on an auth failure: one call, no backoff
    assert signed_in_client.search.call_count == 1
    mock_sleep.assert_not_called()


@patch('src.searchers.youtube_searcher.time.sleep')
def test_search_429_still_handled_by_rate_limiter_not_auth(mock_sleep, searcher, signed_in_client, mock_rate_limiter):
    signed_in_client.search.side_effect = [HTTP_429, [_yt_result(1)]]

    results = searcher.search_track("Song", ["Artist"])

    assert [r['videoId'] for r in results] == ['vid1']
    mock_rate_limiter.handle_429.assert_called_once()


@patch('src.searchers.youtube_searcher.time.sleep')
def test_search_generic_errors_still_return_empty(mock_sleep, searcher, signed_in_client):
    """Non-auth failures keep the old contract: retried, then []."""
    signed_in_client.search.side_effect = YTMusicServerError("Server returned HTTP 500: Internal Server Error.")

    assert searcher.search_track("Song", ["Artist"]) == []


# ============================================================================
# YouTubeSearcher: silent sign-out detection via get_account_info()
# ============================================================================

@patch('src.searchers.youtube_searcher.time.sleep')
def test_identity_not_checked_on_every_search(mock_sleep, searcher, signed_in_client):
    signed_in_client.search.return_value = [_yt_result(1)]

    for _ in range(YouTubeSearcher.IDENTITY_CHECK_INTERVAL - 1):
        searcher.search_track("Song", ["Artist"])

    signed_in_client.get_account_info.assert_not_called()


@patch('src.searchers.youtube_searcher.time.sleep')
def test_identity_checked_on_cadence_and_goes_through_rate_limiter(mock_sleep, searcher, signed_in_client, mock_rate_limiter):
    signed_in_client.search.return_value = [_yt_result(1)]

    for _ in range(YouTubeSearcher.IDENTITY_CHECK_INTERVAL):
        searcher.search_track("Song", ["Artist"])

    signed_in_client.get_account_info.assert_called_once()
    # Invariant §6.3: the identity call is a request like any other
    assert mock_rate_limiter.check_limit.call_count == YouTubeSearcher.IDENTITY_CHECK_INTERVAL + 1
    assert mock_rate_limiter.record_request.call_count == YouTubeSearcher.IDENTITY_CHECK_INTERVAL + 1


@patch('src.searchers.youtube_searcher.time.sleep')
def test_run_of_empty_results_triggers_identity_check_early(mock_sleep, searcher, signed_in_client):
    signed_in_client.search.return_value = []

    for _ in range(YouTubeSearcher.EMPTY_STREAK_THRESHOLD - 1):
        assert searcher.search_track("Song", ["Artist"]) == []
    signed_in_client.get_account_info.assert_not_called()

    # Still signed in: the empty result is genuine and is returned
    assert searcher.search_track("Song", ["Artist"]) == []
    signed_in_client.get_account_info.assert_called_once()


@patch('src.searchers.youtube_searcher.time.sleep')
def test_silent_signout_empty_identity_raises_instead_of_no_match(mock_sleep, searcher, signed_in_client):
    """A signed-out cookie session answers searches with nothing and
    get_account_info() with no account. That must surface as an auth error,
    not as a run of 'No match found'."""
    signed_in_client.search.return_value = []
    signed_in_client.get_account_info.return_value = {}

    for _ in range(YouTubeSearcher.EMPTY_STREAK_THRESHOLD - 1):
        searcher.search_track("Song", ["Artist"])

    with pytest.raises(YouTubeAuthError, match="signed out"):
        searcher.search_track("Song", ["Artist"])


@patch('src.searchers.youtube_searcher.time.sleep')
def test_silent_signout_identity_parse_failure_raises(mock_sleep, searcher, signed_in_client):
    """ytmusicapi raises KeyError when the account header is missing from an
    anonymous response; that is a sign-out too."""
    signed_in_client.search.return_value = []
    signed_in_client.get_account_info.side_effect = KeyError('activeAccountHeaderRenderer')

    for _ in range(YouTubeSearcher.EMPTY_STREAK_THRESHOLD - 1):
        searcher.search_track("Song", ["Artist"])
    with pytest.raises(YouTubeAuthError):
        searcher.search_track("Song", ["Artist"])


def test_verify_identity_connection_error_is_inconclusive(searcher, signed_in_client):
    signed_in_client.get_account_info.side_effect = ConnectionError("offline")
    assert searcher.verify_identity() == {}


def test_verify_identity_401_raises(searcher, signed_in_client):
    signed_in_client.get_account_info.side_effect = HTTP_401
    with pytest.raises(YouTubeAuthError):
        searcher.verify_identity()


def test_searcher_set_client_swaps_and_resets_counters(searcher, signed_in_client, mock_rate_limiter):
    searcher._searches_since_identity_check = 40
    searcher._empty_result_streak = 3
    fresh = Mock()

    searcher.set_client(fresh)

    assert searcher.ytmusic_client is fresh
    assert searcher.rate_limiter is mock_rate_limiter
    assert searcher._searches_since_identity_check == 0
    assert searcher._empty_result_streak == 0
    with pytest.raises(ValueError):
        searcher.set_client(None)


# ============================================================================
# PlaylistMigrator: write path raises, set_client cascades
# ============================================================================

@pytest.fixture
def migrator(signed_in_client, searcher, mock_rate_limiter, cache_manager):
    return PlaylistMigrator(
        ytmusic_client=signed_in_client,
        youtube_searcher=searcher,
        track_matcher=TrackMatcher(threshold=75),
        cache_manager=cache_manager,
        rate_limiter=mock_rate_limiter,
    )


@patch('src.migrators.playlist_migrator.time.sleep')
@pytest.mark.parametrize('exc', [HTTP_401, HTTP_403, NO_AUTH], ids=['401', '403', 'no-auth'])
def test_add_tracks_batch_auth_failure_raises_not_counted_as_failed(mock_sleep, migrator, signed_in_client, exc):
    signed_in_client.add_playlist_items.side_effect = exc

    with pytest.raises(YouTubeAuthError):
        migrator.add_tracks_batch('PL', ['vid1', 'vid2'])

    assert signed_in_client.add_playlist_items.call_count == 1  # no retry


@patch('src.migrators.playlist_migrator.time.sleep')
def test_add_tracks_batch_non_auth_server_error_still_skips_batch(mock_sleep, migrator, signed_in_client):
    signed_in_client.add_playlist_items.side_effect = YTMusicServerError("Server returned HTTP 500: oops")
    assert migrator.add_tracks_batch('PL', ['vid1']) == []


def test_create_playlist_auth_failure_raises_auth_error(migrator, signed_in_client, tracks):
    signed_in_client.create_playlist.side_effect = HTTP_401
    with pytest.raises(YouTubeAuthError):
        migrator.migrate_playlist("P", tracks)


@patch('src.searchers.youtube_searcher.time.sleep')
@patch('src.migrators.playlist_migrator.time.sleep')
def test_migrate_playlist_propagates_search_auth_error_with_state_intact(
    mock_sleep_m, mock_sleep_s, migrator, signed_in_client, tracks
):
    """Tracks 1-3 match and are flushed; the 401 on track 4 must propagate
    (not become 'Error: ...' failed tracks) with the durable state at 3."""
    migrator.FLUSH_SIZE = 3
    signed_in_client.search.side_effect = [
        [_yt_result(1)], [_yt_result(2)], [_yt_result(3)], HTTP_401,
    ]
    states = []

    def state_callback(**state):
        states.append(state)

    with pytest.raises(YouTubeAuthError):
        migrator.migrate_playlist("P", tracks, state_callback=state_callback)

    assert states[-1]['youtube_playlist_ids'] == ['PL_NEW']
    assert states[-1]['last_added_index'] == 3
    assert states[-1]['added_tracks'] == 3
    assert states[-1]['failed_tracks'] == 0
    # Only the three real matches were written
    signed_in_client.add_playlist_items.assert_called_once()


def test_migrator_set_client_cascades_to_searcher(migrator, searcher):
    fresh = Mock()
    migrator.set_client(fresh)
    assert migrator.ytmusic_client is fresh
    assert searcher.ytmusic_client is fresh
    with pytest.raises(ValueError):
        migrator.set_client(None)


# ============================================================================
# BackgroundWorker: paused_auth, never failed
# ============================================================================

def test_worker_pauses_job_on_auth_error_and_notifies(worker, tracks):
    def migrator_func(playlist_name, trks, progress_callback, resume_state=None, state_callback=None):
        progress_callback(2, len(trks), 'Song 2', 2, 0)
        state_callback(youtube_playlist_ids=['PL_X'], added_tracks=2, last_added_index=2,
                       matched_tracks=2, failed_tracks=0)
        raise YouTubeAuthError("Server returned HTTP 401")

    job_id = worker.add_job("Mix", "sp_mix", tracks, migrator_func)
    worker.start()
    status = _wait_for_status(worker, job_id, {'paused_auth', 'failed', 'completed'})
    worker.stop()

    assert status['status'] == 'paused_auth'
    assert status['completed_at'] is None
    assert 'reconnect' in status['error_message'].lower()
    # Resume state preserved exactly
    assert status['youtube_playlist_ids'] == ['PL_X']
    assert status['last_added_index'] == 2
    assert status['added_tracks'] == 2
    assert status['progress'] == 2
    # User told once, and not with the "failed" notification
    worker.notifier.notify_auth_required.assert_called_once()
    assert worker.notifier.notify_auth_required.call_args.kwargs['playlist_name'] == "Mix"
    worker.notifier.notify_migration_failed.assert_not_called()
    worker.notifier.notify_migration_complete.assert_not_called()
    assert worker.auth_required.is_set()
    assert worker.is_auth_required()
    assert [j['job_id'] for j in worker.get_auth_paused_jobs()] == [job_id]


def test_worker_parks_following_jobs_without_calling_api(worker, tracks):
    """Once the session is known dead, queued jobs are parked, not run."""
    calls = []

    def first(playlist_name, trks, progress_callback):
        calls.append(playlist_name)
        raise YouTubeAuthError()

    def second(playlist_name, trks, progress_callback):
        calls.append(playlist_name)
        return {'matched_tracks': 6, 'total_tracks': 6}

    j1 = worker.add_job("One", "sp1", tracks, first)
    j2 = worker.add_job("Two", "sp2", tracks, second)
    worker.start()
    _wait_for_status(worker, j1, {'paused_auth'})
    _wait_for_status(worker, j2, {'paused_auth'})
    worker.stop()

    assert worker.get_job_status(j1)['status'] == 'paused_auth'
    assert worker.get_job_status(j2)['status'] == 'paused_auth'
    assert calls == ["One"]  # second migrator never invoked
    worker.notifier.notify_auth_required.assert_called_once()
    assert worker.job_queue.unfinished_tasks == 0


def test_resume_auth_paused_jobs_requeues_with_saved_state(worker, cache_manager, tracks):
    cache_manager.cache_tracks(tracks, "sp_mix")
    cursor = cache_manager.connection.cursor()
    cursor.execute("""
        INSERT INTO migrations (job_id, playlist_name, playlist_id, status, total_tracks,
                                processed_tracks, created_at, started_at, error_message,
                                youtube_playlist_ids, added_tracks, last_added_index,
                                matched_tracks, failed_tracks)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, ("job-auth", "Mix", "sp_mix", "paused_auth", 6, 3, datetime.now(), datetime.now(),
          "expired", json.dumps(['PL_X']), 3, 3, 3, 0))
    cache_manager.connection.commit()
    worker.auth_required.set()
    received = {}

    def migrator_func(playlist_name, trks, progress_callback, resume_state=None, state_callback=None):
        received['resume_state'] = resume_state
        received['tracks'] = [t['id'] for t in trks]
        return {'matched_tracks': 6, 'total_tracks': 6, 'playlist_url': ''}

    resumed = worker.resume_auth_paused_jobs(migrator_func=migrator_func)

    assert resumed == ["job-auth"]
    assert not worker.auth_required.is_set()
    assert worker.get_job_status("job-auth")['status'] == 'queued'
    assert worker.get_job_status("job-auth")['error_message'] is None

    worker.start()
    status = _wait_for_status(worker, "job-auth", {'completed', 'failed', 'paused_auth'})
    worker.stop()

    assert status['status'] == 'completed'
    assert received['resume_state']['youtube_playlist_ids'] == ['PL_X']
    assert received['resume_state']['last_added_index'] == 3
    assert received['tracks'] == [t['id'] for t in tracks]


def test_resume_auth_paused_jobs_ignores_other_statuses(worker, cache_manager, tracks):
    cache_manager.cache_tracks(tracks, "sp")
    cursor = cache_manager.connection.cursor()
    for job_id, status in [("c", "completed"), ("f", "failed"), ("q", "queued")]:
        cursor.execute("""
            INSERT INTO migrations (job_id, playlist_name, playlist_id, status, total_tracks,
                                    processed_tracks, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (job_id, "P", "sp", status, 6, 0, datetime.now()))
    cache_manager.connection.commit()

    assert worker.resume_auth_paused_jobs(migrator_func=Mock()) == []
    assert worker.job_queue.qsize() == 0


def test_restart_resumes_paused_auth_jobs_too(worker, cache_manager, tracks):
    """Crash-recovery on launch picks paused_auth jobs up as well."""
    cache_manager.cache_tracks(tracks, "sp")
    cursor = cache_manager.connection.cursor()
    cursor.execute("""
        INSERT INTO migrations (job_id, playlist_name, playlist_id, status, total_tracks,
                                processed_tracks, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, ("pa", "P", "sp", "paused_auth", 6, 0, datetime.now()))
    cache_manager.connection.commit()

    assert worker.resume_incomplete_migrations(migrator_func=Mock()) == ["pa"]
    assert worker.get_job_status("pa")['status'] == 'queued'


# ============================================================================
# Notifier
# ============================================================================

def test_notifier_auth_required_message():
    notifier = Notifier()
    notifier.enabled = True
    with patch('src.utils.notifier.plyer_notification', create=True) as plyer:
        notifier.notify_auth_required("Mix")
    kwargs = plyer.notify.call_args.kwargs
    assert "sign-in expired" in kwargs['title']
    assert kwargs['message'] == "Mix: YouTube Music sign-in expired — reconnect to resume"


# ============================================================================
# MigrationManager: status + the re-auth seam (end to end, real worker)
# ============================================================================

@pytest.fixture
def real_manager(signed_in_client, cache_manager):
    spotify = Mock()
    with patch('src.migrators.migration_manager.SpotifyFetcher'), \
         patch('src.migrators.migration_manager.Notifier'):
        manager = MigrationManager(spotify, signed_in_client, cache_manager)
    manager.background_worker.notifier = Mock(spec=Notifier)
    # Keep tests fast: no pacing sleeps
    manager.rate_limiter.check_limit = Mock(return_value=True)
    manager.rate_limiter.record_request = Mock()
    manager.youtube_searcher.SEARCH_DELAY = 0
    manager.playlist_migrator.BATCH_DELAY = 0
    manager.playlist_migrator.FLUSH_SIZE = 3
    yield manager
    if manager.background_worker.is_running.is_set():
        manager.stop()


def test_reauthenticate_youtube_resumes_from_where_it_paused(real_manager, signed_in_client, tracks):
    """Round trip: 401 after three tracks → paused_auth → fresh client →
    resume continues at track 4 on the same playlist, no second playlist."""
    signed_in_client.search.side_effect = [
        [_yt_result(1)], [_yt_result(2)], [_yt_result(3)], HTTP_401,
    ]
    real_manager.start()
    [job_id] = real_manager.migrate_playlists([{'id': 'sp_mix', 'name': 'Mix', 'tracks': tracks}])
    worker = real_manager.background_worker
    status = _wait_for_status(worker, job_id, {'paused_auth', 'failed', 'completed'})

    assert status['status'] == 'paused_auth'
    assert status['youtube_playlist_ids'] == ['PL_NEW']
    assert status['last_added_index'] == 3
    overall = real_manager.get_migration_status()
    assert overall['paused_auth_jobs'] == 1
    assert overall['auth_required'] is True
    assert overall['failed_jobs'] == 0
    assert real_manager.is_auth_required()
    worker.notifier.notify_auth_required.assert_called_once()

    # The Native-Messaging re-capture layer hands over a fresh client here
    fresh = Mock()
    fresh.get_account_info.return_value = {'accountName': 'Test User'}
    fresh.search.side_effect = [[_yt_result(4)], [_yt_result(5)], [_yt_result(6)]]
    fresh.add_playlist_items.return_value = {'status': 'STATUS_SUCCEEDED'}

    resumed = real_manager.reauthenticate_youtube(fresh)

    assert resumed == [job_id]
    assert real_manager.ytmusic_client is fresh
    assert real_manager.youtube_searcher.ytmusic_client is fresh
    assert real_manager.playlist_migrator.ytmusic_client is fresh

    final = _wait_for_status(worker, job_id, {'completed', 'failed', 'paused_auth'})
    assert final['status'] == 'completed'
    assert final['youtube_playlist_ids'] == ['PL_NEW']  # reused, not recreated
    assert final['added_tracks'] == 6
    assert final['matched_tracks'] == 6
    assert final['failed_tracks'] == 0
    fresh.create_playlist.assert_not_called()
    # Only tracks 4-6 were searched with the fresh client (1-3 came from cache)
    assert fresh.search.call_count == 3
    fresh.add_playlist_items.assert_called_once_with(playlistId='PL_NEW', videoIds=['vid4', 'vid5', 'vid6'])
    overall = real_manager.get_migration_status()
    assert overall['paused_auth_jobs'] == 0
    assert overall['auth_required'] is False
    assert overall['completed_jobs'] == 1


def test_reauthenticate_youtube_rejects_none(real_manager):
    with pytest.raises(ValueError):
        real_manager.reauthenticate_youtube(None)


def test_get_migration_status_reports_paused_auth_with_mock_worker():
    """Status counts from the job table, so the UI sees it after a restart too."""
    with patch('src.migrators.migration_manager.BackgroundWorker') as worker_cls, \
         patch('src.migrators.migration_manager.PlaylistMigrator'), \
         patch('src.migrators.migration_manager.YouTubeSearcher'), \
         patch('src.migrators.migration_manager.TrackMatcher'), \
         patch('src.migrators.migration_manager.SpotifyFetcher'), \
         patch('src.migrators.migration_manager.Notifier'), \
         patch('src.migrators.migration_manager.RateLimiter'):
        mock_worker = Mock()
        mock_worker.is_running.is_set.return_value = True
        mock_worker.job_queue.qsize.return_value = 0
        mock_worker.get_current_job.return_value = None
        mock_worker.get_all_jobs.return_value = [
            {'status': 'paused_auth'}, {'status': 'paused_auth'}, {'status': 'completed'},
        ]
        worker_cls.return_value = mock_worker
        cache = Mock(db_path=':memory:')
        manager = MigrationManager(Mock(), Mock(), cache)

        status = manager.get_migration_status()

    assert status['paused_auth_jobs'] == 2
    assert status['auth_required'] is True
    assert status['failed_jobs'] == 0
    assert MigrationManager.PAUSED_AUTH_STATUS == 'paused_auth'
