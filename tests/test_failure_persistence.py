"""Persisted failed tracks, active job ids and resumed-job duration."""

import os
import sqlite3
from datetime import datetime, timedelta
from unittest.mock import Mock

import flet as ft
import pytest

from src.migrators.migration_manager import MigrationManager
from src.migrators.playlist_migrator import PlaylistMigrator
from src.ui.screens.results_screen import ResultsScreen
from src.utils.background_worker import BackgroundWorker
from src.utils.cache_manager import CacheManager


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "cache.db")


def _tracks(n):
    return [{'id': f't{i}', 'name': f'Song {i}', 'artists': [f'Artist {i}']} for i in range(1, n + 1)]


def _migrator(cache, matcher_results, add_fail=False):
    searcher = Mock()
    searcher.search_track.return_value = [{'videoId': 'x'}]
    matcher = Mock()
    matcher.match_track.side_effect = matcher_results
    client = Mock()
    client.create_playlist.return_value = 'PL1'
    if add_fail:
        client.add_playlist_items.side_effect = RuntimeError('boom')
    limiter = Mock()
    m = PlaylistMigrator(client, searcher, matcher, cache, limiter)
    m.BATCH_DELAY = 0
    return m


class TestFailedTracksTable:
    def test_migration_preserves_existing_rows_and_is_idempotent(self, db_path):
        c = CacheManager(db_path)
        c.cache_playlist({'id': 'p', 'name': 'P'})
        c.cache_tracks(_tracks(3), 'p')
        c.close()
        for _ in range(2):  # reopen twice: create_tables must be idempotent
            c = CacheManager(db_path)
            assert len(c.get_cached_tracks('p')) == 3
            c.close()

    def test_upgrades_db_without_failed_tracks_table(self, db_path):
        c = CacheManager(db_path)
        c.cache_playlist({'id': 'p', 'name': 'P'})
        c.cache_tracks(_tracks(2), 'p')
        c.connection.execute("DROP TABLE failed_tracks")
        c.connection.commit()
        c.close()
        c = CacheManager(db_path)
        assert len(c.get_cached_tracks('p')) == 2
        assert c.get_failed_tracks('p') == []

    def test_record_upsert_and_read(self, db_path):
        c = CacheManager(db_path)
        t = {'id': 'a', 'name': 'Song', 'artists': ['X', 'Y']}
        c.record_failed_track('p', t, 'No match', 2)
        c.record_failed_track('p', t, 'Other', 2)  # same track again: replaced
        rows = c.get_failed_tracks('p')
        assert len(rows) == 1
        assert rows[0]['name'] == 'Song' and rows[0]['reason'] == 'Other'
        assert rows[0]['artist'] == 'X, Y'
        assert c.get_failed_tracks('other') == []

    def test_survives_reopen(self, db_path):
        c = CacheManager(db_path)
        c.record_failed_track('p', {'id': 'a', 'name': 'Song'}, 'No match')
        c.close()
        c2 = CacheManager(db_path)
        assert c2.get_failed_tracks('p')[0]['reason'] == 'No match'


class TestMigratorRecordsFailures:
    def test_unmatched_and_error_tracks_persisted(self, db_path):
        cache = CacheManager(db_path)
        m = _migrator(cache, [('v1', 90.0), (None, 0.0), RuntimeError('kaput')])
        report = m.migrate_playlist('P', _tracks(3), playlist_id='p')
        assert len(report['failed_tracks']) == 2
        cache.close()
        rows = {r['name']: r['reason'] for r in CacheManager(db_path).get_failed_tracks('p')}
        assert rows['Song 2'] == 'No match found above threshold'
        assert 'kaput' in rows['Song 3']
        assert 'Song 1' not in rows

    def test_failed_write_persisted(self, db_path):
        cache = CacheManager(db_path)
        m = _migrator(cache, [('v1', 90.0)], add_fail=True)
        m.add_tracks_batch = Mock(return_value=[])
        m.migrate_playlist('P', _tracks(1), playlist_id='p')
        rows = cache.get_failed_tracks('p')
        assert rows[0]['reason'] == 'Failed to add to YouTube Music playlist'

    def test_playlist_id_falls_back_to_track_field(self, db_path):
        cache = CacheManager(db_path)
        tracks = [dict(t, playlist_id='pp') for t in _tracks(1)]
        _migrator(cache, [(None, 0.0)]).migrate_playlist('P', tracks)
        assert len(cache.get_failed_tracks('pp')) == 1

    def test_fresh_run_clears_old_resume_keeps(self, db_path):
        cache = CacheManager(db_path)
        cache.record_failed_track('p', {'id': 'old', 'name': 'Old'}, 'r')
        _migrator(cache, [('v', 90.0)]).migrate_playlist('P', _tracks(1), playlist_id='p')
        assert cache.get_failed_tracks('p') == []
        cache.record_failed_track('p', {'id': 't1', 'name': 'Song 1'}, 'r')
        m = _migrator(cache, [('v', 90.0)])
        m.migrate_playlist('P', _tracks(2), playlist_id='p',
                           resume_state={'youtube_playlist_ids': ['PL1'], 'last_added_index': 1})
        assert [r['name'] for r in cache.get_failed_tracks('p')] == ['Song 1']

    def test_worker_passes_playlist_id(self, db_path):
        cache = CacheManager(db_path)
        w = BackgroundWorker(cache)
        seen = {}

        def fn(name, tracks, cb, playlist_id=None):
            seen['pid'] = playlist_id
            return {}
        w._call_migrator({'migrator_func': fn, 'playlist_name': 'n', 'tracks': [], 'playlist_id': 'p9'},
                         None, None)
        assert seen['pid'] == 'p9'


def _manager(db_path):
    cache = CacheManager(db_path)
    mgr = MigrationManager(Mock(), Mock(), cache)
    return mgr, cache


class TestActiveJobsAndDuration:
    def _job(self, cache, job_id, status, created, completed=None, pid='p'):
        cache.connection.execute(
            "INSERT INTO migrations (job_id, playlist_name, playlist_id, status, total_tracks, "
            "created_at, completed_at) VALUES (?,?,?,?,?,?,?)",
            (job_id, 'N-' + job_id, pid, status, 10, created, completed))
        cache.connection.commit()

    def test_active_job_ids(self, db_path):
        mgr, cache = _manager(db_path)
        now = datetime.now()
        self._job(cache, 'a', 'queued', now)
        self._job(cache, 'b', 'in_progress', now + timedelta(seconds=1))
        self._job(cache, 'c', 'paused_auth', now + timedelta(seconds=2))
        self._job(cache, 'd', 'completed', now, now)
        self._job(cache, 'e', 'failed', now, now)
        assert mgr.get_active_job_ids() == ['a', 'b', 'c']

    def test_duration_across_restart(self, db_path):
        mgr, cache = _manager(db_path)
        start = datetime(2026, 1, 1, 10, 0, 0)
        self._job(cache, 'a', 'completed', start, start + timedelta(hours=5, minutes=30))
        cache.close()
        mgr2, _ = _manager(db_path)  # a new process: no in-memory timers
        batch = mgr2.get_batch_progress(['a'])
        assert batch['duration_seconds'] == pytest.approx(5.5 * 3600)
        assert batch['jobs'][0]['playlist_id'] == 'p'

    def test_duration_running_uses_now(self, db_path):
        mgr, cache = _manager(db_path)
        self._job(cache, 'a', 'in_progress', datetime.now() - timedelta(seconds=100))
        assert 99 <= mgr.get_batch_progress(['a'])['duration_seconds'] < 200

    def test_manager_failed_tracks_with_names(self, db_path):
        mgr, cache = _manager(db_path)
        self._job(cache, 'a', 'completed', datetime.now(), datetime.now())
        cache.record_failed_track('p', {'id': 'x', 'name': 'S'}, 'why')
        rows = mgr.get_failed_tracks(job_ids=['a'])
        assert rows[0]['name'] == 'S' and rows[0]['reason'] == 'why'
        assert rows[0]['playlist_name'] == 'N-a'


class TestResultsScreenRealList:
    def test_results_lists_persisted_failures_and_duration(self, db_path):
        mgr, cache = _manager(db_path)
        start = datetime(2026, 1, 1, 10, 0, 0)
        cache.connection.execute(
            "INSERT INTO migrations (job_id, playlist_name, playlist_id, status, total_tracks, "
            "created_at, completed_at) VALUES ('a','Mix','p','completed',10,?,?)",
            (start, start + timedelta(hours=2)))
        cache.connection.commit()
        cache.record_failed_track('p', {'id': 'x', 'name': 'Lost Song', 'artists': ['Band']},
                                  'No match found above threshold')
        page = Mock(spec=ft.Page)
        page.overlay = []
        state = {
            'migration_manager': mgr,
            'migration_job_ids': ['a'],
            'migration_results': {'total_tracks': 10, 'matched_count': 9, 'failed_count': 1,
                                  'duration': 5},
            'playlist_results': [{'name': 'Mix', 'total_tracks': 10, 'matched_tracks': 9,
                                  'failed_count': 1, 'failed_tracks': []}],
        }
        screen = ResultsScreen(page, state)
        failed = screen.results[0]['failed_tracks']
        assert failed[0]['name'] == 'Lost Song'
        assert failed[0]['artist'] == 'Band'
        assert failed[0]['failure_reason'] == 'No match found above threshold'
        assert screen.duration == pytest.approx(2 * 3600)
        screen.build()  # renders the "View 1 failed" button without error
