"""
Tests for RateLimiter.

Covers the sustained-rate policy (min interval + jitter, per-minute ceiling),
the absence of any silent hour-long sleep, persistence of counters across
limiter instances sharing a database, the observable throttle state, 429
backoff honouring Retry-After, and QUOTA_EXCEEDED surfacing as reason 'quota'.

All tests mock time.time / time.sleep -- nothing here actually waits.
"""

import os
import sqlite3
from datetime import date, datetime, timedelta
from unittest.mock import patch, Mock

import pytest

from src.utils.rate_limiter import RateLimiter


# ---------------------------------------------------------------------------
# Fake clock: time.sleep advances time.time, so sliced waits terminate.
# ---------------------------------------------------------------------------
class FakeClock:
    def __init__(self, start: float = 1_700_000_000.0):
        self.now = start
        self.sleeps = []

    def time(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds

    @property
    def total_slept(self):
        return sum(self.sleeps)


@pytest.fixture
def clock():
    c = FakeClock()
    with patch('time.time', side_effect=c.time), patch('time.sleep', side_effect=c.sleep):
        yield c


@pytest.fixture
def no_jitter():
    """Make random.uniform deterministic (always the upper bound)."""
    with patch('src.utils.rate_limiter.random.uniform', side_effect=lambda a, b: b):
        yield


@pytest.fixture
def limiter(clock, no_jitter):
    """In-memory limiter with small, deterministic policy."""
    return RateLimiter(per_minute_limit=5, min_interval=1.0, jitter=0.5)


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / 'cache.db')


# ---------------------------------------------------------------------------
# Initialization / public surface
# ---------------------------------------------------------------------------
class TestInitialization:
    def test_defaults_are_sustained_rate_not_data_api_quota(self):
        limiter = RateLimiter()
        assert limiter.daily_limit is None            # no Data-API daily cap
        assert limiter.per_minute_limit == RateLimiter.DEFAULT_PER_MINUTE_LIMIT
        assert limiter.min_interval == RateLimiter.DEFAULT_MIN_INTERVAL_SECONDS
        assert limiter.jitter == RateLimiter.DEFAULT_JITTER_SECONDS
        assert limiter.backoff_seconds == RateLimiter.MIN_BACKOFF_SECONDS
        assert len(limiter.request_times) == 0
        assert limiter.daily_operations == 0
        assert limiter.last_reset == date.today()
        assert not hasattr(RateLimiter, 'PAUSE_ON_DAILY_LIMIT_HOURS')

    def test_legacy_kwargs_still_accepted(self):
        limiter = RateLimiter(daily_limit=100, per_minute_limit=10)
        assert limiter.daily_limit == 100
        assert limiter.per_minute_limit == 10

    def test_public_surface_preserved(self):
        limiter = RateLimiter()
        for name in ('check_limit', 'record_request', 'handle_429', 'reset_backoff',
                     'reset', 'get_current_stats', 'get_remaining_daily_operations',
                     'get_throttle_state', 'close'):
            assert callable(getattr(limiter, name))

    @pytest.mark.parametrize('kwargs', [
        dict(daily_limit=0), dict(daily_limit=-1),
        dict(per_minute_limit=0), dict(per_minute_limit=-5),
    ])
    def test_invalid_limits_rejected(self, kwargs):
        with pytest.raises(ValueError, match="Rate limits must be positive integers"):
            RateLimiter(**kwargs)

    def test_negative_interval_rejected(self):
        with pytest.raises(ValueError):
            RateLimiter(min_interval=-1)
        with pytest.raises(ValueError):
            RateLimiter(jitter=-0.1)


# ---------------------------------------------------------------------------
# Sustained-rate pacing
# ---------------------------------------------------------------------------
class TestPacing:
    def test_first_request_is_not_delayed(self, limiter, clock):
        limiter.check_limit()
        assert clock.sleeps == []

    def test_min_interval_plus_jitter_enforced(self, limiter, clock):
        limiter.check_limit()
        limiter.record_request()
        # Immediately ask again: must wait min_interval + jitter (1.0 + 0.5).
        limiter.check_limit()
        assert clock.total_slept == pytest.approx(1.5)

    def test_no_wait_when_interval_already_elapsed(self, limiter, clock):
        limiter.record_request()
        clock.now += 2.0
        limiter.check_limit()
        assert clock.sleeps == []

    def test_partial_interval_waits_only_remainder(self, limiter, clock):
        limiter.record_request()
        clock.now += 1.0
        limiter.check_limit()
        assert clock.total_slept == pytest.approx(0.5)

    def test_jitter_is_random_within_bounds(self, clock):
        limiter = RateLimiter(per_minute_limit=100, min_interval=1.0, jitter=0.5)
        waits = set()
        for _ in range(20):
            limiter.record_request()
            before = clock.total_slept
            limiter.check_limit()
            waits.add(round(clock.total_slept - before, 4))
        assert all(1.0 <= w <= 1.5 for w in waits)
        assert len(waits) > 1  # jitter actually varies

    def test_zero_interval_and_jitter_means_no_pacing(self, clock):
        limiter = RateLimiter(per_minute_limit=100, min_interval=0, jitter=0)
        for _ in range(10):
            limiter.check_limit()
            limiter.record_request()
        assert clock.sleeps == []

    def test_pacing_wait_does_not_flip_visible_throttle(self, limiter, clock):
        limiter.record_request()
        limiter.check_limit()
        assert limiter.get_throttle_state()['throttled'] is False


class TestPerMinuteCeiling:
    def test_ceiling_enforced_with_wait_for_window(self, clock, no_jitter):
        limiter = RateLimiter(per_minute_limit=5, min_interval=0, jitter=0)
        for _ in range(5):
            limiter.check_limit()
            limiter.record_request()
        assert clock.sleeps == []
        clock.now += 10
        limiter.check_limit()
        # Oldest request was 10 s ago -> wait the remaining 50 s.
        assert clock.total_slept == pytest.approx(50.0)

    def test_old_requests_fall_out_of_window(self, clock, no_jitter):
        limiter = RateLimiter(per_minute_limit=5, min_interval=0, jitter=0)
        for _ in range(5):
            limiter.record_request()
        clock.now += 61
        limiter.check_limit()
        assert clock.sleeps == []

    def test_long_window_wait_is_visible_as_rate_throttle(self, clock, no_jitter):
        seen = []
        limiter = RateLimiter(per_minute_limit=3, min_interval=0, jitter=0,
                              on_throttle=seen.append, max_wait_slice=10)
        for _ in range(3):
            limiter.record_request()
        limiter.check_limit()  # must wait ~60 s
        # Became throttled with reason 'rate' and an 'until' ~60 s ahead...
        assert seen[0]['throttled'] is True
        assert seen[0]['reason'] == 'rate'
        assert seen[0]['until'] == pytest.approx(clock.now)  # clock advanced to 'until'
        assert 'throttled until' in seen[0]['message']
        # ...and the wait was sliced, never one monolithic sleep.
        assert max(clock.sleeps) <= 10
        assert clock.total_slept == pytest.approx(60.0)
        # ...and cleared afterwards.
        assert seen[-1]['throttled'] is False
        assert limiter.get_throttle_state()['throttled'] is False

    def test_deque_keeps_only_per_minute_limit_entries(self, clock):
        limiter = RateLimiter(per_minute_limit=5, min_interval=0, jitter=0)
        for i in range(10):
            clock.now = 1000.0 + i
            limiter.record_request()
        assert len(limiter.request_times) == 5
        assert list(limiter.request_times) == [1005.0, 1006.0, 1007.0, 1008.0, 1009.0]


# ---------------------------------------------------------------------------
# No silent hour-long sleep on a daily ceiling
# ---------------------------------------------------------------------------
class TestDailyCeilingIsVisibleNotSilent:
    def test_default_has_no_daily_ceiling(self, clock):
        limiter = RateLimiter(min_interval=0, jitter=0, per_minute_limit=100000)
        for _ in range(20000):
            limiter.record_request()
        limiter.check_limit()
        assert clock.sleeps == []
        assert limiter.get_remaining_daily_operations() is None

    def test_hitting_ceiling_sets_quota_throttle_until_midnight_and_slices_wait(self, no_jitter):
        # Start at 23:00 local so midnight is one hour away.
        start = datetime.combine(date(2026, 3, 10), datetime.min.time()) + timedelta(hours=23)
        clock = FakeClock(start.timestamp())
        seen = []
        with patch('time.time', side_effect=clock.time), patch('time.sleep', side_effect=clock.sleep):
            limiter = RateLimiter(daily_limit=3, per_minute_limit=100, min_interval=0, jitter=0,
                                  on_throttle=seen.append, max_wait_slice=30)
            for _ in range(3):
                limiter.record_request()

            limiter.check_limit()

            # Visible: reason 'quota', until == next local midnight, message has HH:MM.
            first = seen[0]
            assert first['throttled'] is True
            assert first['reason'] == 'quota'
            midnight = datetime.combine(date(2026, 3, 11), datetime.min.time()).timestamp()
            assert first['until'] == pytest.approx(midnight)
            assert '00:00' in first['message']
            # Not silent: never a single 3600 s sleep; sliced into <= 30 s pieces.
            assert 3600 not in clock.sleeps
            assert max(clock.sleeps) <= 30
            assert clock.total_slept == pytest.approx(3600.0)
            # Day rolled over: counter reset, throttle cleared, caller may proceed.
            assert limiter.daily_operations == 0
            assert limiter.last_reset == date(2026, 3, 11)
            assert limiter.get_throttle_state()['throttled'] is False

    def test_interrupt_event_ends_daily_wait_early(self, no_jitter):
        import threading
        start = datetime.combine(date(2026, 3, 10), datetime.min.time()) + timedelta(hours=23)
        clock = FakeClock(start.timestamp())
        stop = threading.Event()

        def sleep_then_stop(seconds):
            clock.sleep(seconds)
            stop.set()

        with patch('time.time', side_effect=clock.time), patch('time.sleep', side_effect=sleep_then_stop):
            limiter = RateLimiter(daily_limit=1, per_minute_limit=100, min_interval=0, jitter=0,
                                  interrupt_event=stop, max_wait_slice=30)
            limiter.record_request()
            limiter.check_limit()
            assert len(clock.sleeps) == 1       # one slice, then interrupted
            assert limiter.get_throttle_state()['throttled'] is True  # still visible

    def test_daily_counter_rolls_over_on_date_change(self, clock):
        limiter = RateLimiter(daily_limit=10, per_minute_limit=100, min_interval=0, jitter=0)
        for _ in range(9):
            limiter.record_request()
        assert limiter.daily_operations == 9
        clock.now += 86400
        limiter.check_limit()
        limiter.record_request()
        assert limiter.daily_operations == 1
        assert limiter.last_reset == datetime.fromtimestamp(clock.now).date()

    def test_remaining_daily_operations(self, clock):
        limiter = RateLimiter(daily_limit=10, per_minute_limit=100, min_interval=0, jitter=0)
        assert limiter.get_remaining_daily_operations() == 10
        for _ in range(15):
            limiter.record_request()
        assert limiter.get_remaining_daily_operations() == 0


# ---------------------------------------------------------------------------
# Throttle state
# ---------------------------------------------------------------------------
class TestThrottleState:
    def test_initial_state_shape(self, limiter):
        state = limiter.get_throttle_state()
        assert state == {'throttled': False, 'reason': None, 'until': None, 'message': ''}

    def test_state_during_and_after_backoff(self, clock, no_jitter):
        limiter = RateLimiter(min_interval=0, jitter=0, max_wait_slice=10)
        states = []

        def sleep_and_sample(seconds):
            states.append(limiter.get_throttle_state())
            clock.sleep(seconds)

        with patch('time.sleep', side_effect=sleep_and_sample):
            limiter.handle_429(retry_after=25)
        assert len(states) == 3                      # 10 + 10 + 5
        assert all(s['throttled'] for s in states)
        assert all(s['reason'] == 'rate' for s in states)
        assert states[0]['until'] == pytest.approx(clock.now)
        assert limiter.get_throttle_state()['throttled'] is False

    def test_expired_throttle_reads_as_clear(self, clock, no_jitter):
        limiter = RateLimiter(min_interval=0, jitter=0)
        limiter._set_throttle('rate', clock.now + 30)
        assert limiter.get_throttle_state()['throttled'] is True
        clock.now += 31
        assert limiter.get_throttle_state() == {
            'throttled': False, 'reason': None, 'until': None, 'message': ''
        }

    def test_callback_errors_do_not_propagate(self, clock, no_jitter):
        limiter = RateLimiter(min_interval=0, jitter=0, on_throttle=Mock(side_effect=RuntimeError('ui')))
        limiter.handle_429(retry_after=1)  # must not raise

    def test_stats_include_throttle_and_policy(self, limiter):
        stats = limiter.get_current_stats()
        for key in ('daily_operations', 'daily_limit', 'remaining_operations',
                    'requests_in_window', 'per_minute_limit', 'min_interval', 'jitter',
                    'backoff_seconds', 'last_reset', 'persistent', 'throttled',
                    'throttle_reason', 'throttled_until', 'throttle_message'):
            assert key in stats
        assert stats['persistent'] is False
        assert stats['throttled'] is False

    def test_repr(self, limiter):
        limiter.record_request()
        r = repr(limiter)
        assert 'RateLimiter' in r and '1/-' in r and '1/5' in r and '60s' in r


# ---------------------------------------------------------------------------
# 429 handling
# ---------------------------------------------------------------------------
class TestHandle429:
    def test_retry_after_honoured_exactly(self, limiter, clock):
        limiter.handle_429(retry_after=120)
        assert clock.total_slept == pytest.approx(120)
        assert max(clock.sleeps) <= RateLimiter.DEFAULT_MAX_WAIT_SLICE_SECONDS

    def test_exponential_backoff_progression(self, limiter, clock):
        totals = []
        for _ in range(5):
            before = clock.total_slept
            limiter.handle_429()
            totals.append(clock.total_slept - before)
        assert totals == pytest.approx([60, 120, 240, 300, 300])
        assert limiter.backoff_seconds == RateLimiter.MAX_BACKOFF_SECONDS

    def test_backoff_escalates_even_when_retry_after_given(self, limiter, clock):
        limiter.handle_429(retry_after=5)
        assert limiter.backoff_seconds == 120

    def test_reset_backoff(self, limiter):
        limiter.backoff_seconds = 240
        limiter.reset_backoff()
        assert limiter.backoff_seconds == RateLimiter.MIN_BACKOFF_SECONDS
        limiter.reset_backoff()  # idempotent
        assert limiter.backoff_seconds == RateLimiter.MIN_BACKOFF_SECONDS

    def test_zero_retry_after(self, limiter, clock):
        limiter.handle_429(retry_after=0)
        assert clock.total_slept == 0
        assert limiter.get_throttle_state()['throttled'] is False

    def test_transient_429_surfaces_reason_rate(self, limiter, clock):
        seen = []
        limiter.on_throttle = seen.append
        limiter.handle_429(retry_after=30)
        assert seen[0]['reason'] == 'rate'
        assert seen[-1]['throttled'] is False

    def test_quota_exceeded_surfaces_reason_quota(self, limiter, clock):
        seen = []
        limiter.on_throttle = seen.append
        limiter.handle_429(retry_after=3600, reason='QUOTA_EXCEEDED')
        assert seen[0]['throttled'] is True
        assert seen[0]['reason'] == 'quota'
        assert seen[0]['message'].startswith('Quota exhausted')
        assert clock.total_slept == pytest.approx(3600)
        assert max(clock.sleeps) <= RateLimiter.DEFAULT_MAX_WAIT_SLICE_SECONDS

    def test_quota_reason_accepts_short_form_and_helper(self, limiter, clock):
        seen = []
        limiter.on_throttle = seen.append
        limiter.handle_429(retry_after=10, reason='quota')
        limiter.handle_quota_exceeded(retry_after=10)
        assert [s['reason'] for s in seen if s['throttled']] == ['quota', 'quota']

    def test_quota_without_retry_after_waits_max_backoff(self, limiter, clock):
        # Quota exhaustion will not clear on a short retry: never shorter than max backoff.
        limiter.handle_429(reason='quota')
        assert clock.total_slept == pytest.approx(RateLimiter.MAX_BACKOFF_SECONDS)

    def test_429_recovery_flow(self, limiter, clock):
        limiter.handle_429()
        assert limiter.backoff_seconds == 120
        limiter.handle_429()
        assert limiter.backoff_seconds == 240
        limiter.reset_backoff()
        assert limiter.backoff_seconds == RateLimiter.MIN_BACKOFF_SECONDS


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------
class TestPersistence:
    def test_creates_own_table_idempotently(self, db_path, clock):
        RateLimiter(db_path=db_path).close()
        RateLimiter(db_path=db_path).close()  # second construction: no error
        with sqlite3.connect(db_path) as conn:
            tables = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
        assert 'rate_limit_state' in tables

    def test_counters_reload_across_instances(self, db_path, clock, no_jitter):
        a = RateLimiter(daily_limit=100, per_minute_limit=10, min_interval=0, jitter=0, db_path=db_path)
        for i in range(4):
            clock.now += 1
            a.record_request()
        a.handle_429(retry_after=0)      # escalates backoff to 120
        a.close()

        b = RateLimiter(daily_limit=100, per_minute_limit=10, min_interval=0, jitter=0, db_path=db_path)
        assert b.daily_operations == 4
        assert list(b.request_times) == list(a.request_times)
        assert b.last_request_at == a.last_request_at
        assert b.backoff_seconds == 120
        assert b.last_reset == a.last_reset
        assert b.get_current_stats()['persistent'] is True

    def test_reloaded_window_still_enforces_ceiling(self, db_path, clock, no_jitter):
        a = RateLimiter(per_minute_limit=3, min_interval=0, jitter=0, db_path=db_path)
        for _ in range(3):
            a.record_request()
        a.close()
        # "Restart" 10 s later: the three requests are still inside the window.
        clock.now += 10
        b = RateLimiter(per_minute_limit=3, min_interval=0, jitter=0, db_path=db_path)
        b.check_limit()
        assert clock.total_slept == pytest.approx(50.0)

    def test_reloaded_pacing_honours_last_request(self, db_path, clock, no_jitter):
        a = RateLimiter(min_interval=2.0, jitter=0, db_path=db_path)
        a.record_request()
        a.close()
        b = RateLimiter(min_interval=2.0, jitter=0, db_path=db_path)
        b.check_limit()
        assert clock.total_slept == pytest.approx(2.0)

    def test_active_throttle_survives_restart(self, db_path, clock, no_jitter):
        import threading
        stop = threading.Event()

        def sleep_then_stop(seconds):
            clock.sleep(seconds)
            stop.set()

        with patch('time.sleep', side_effect=sleep_then_stop):
            a = RateLimiter(min_interval=0, jitter=0, db_path=db_path,
                            interrupt_event=stop, max_wait_slice=10)
            a.handle_429(retry_after=600, reason='quota')   # interrupted after 10 s
        a.close()
        b = RateLimiter(min_interval=0, jitter=0, db_path=db_path)
        state = b.get_throttle_state()
        assert state['throttled'] is True
        assert state['reason'] == 'quota'
        assert state['until'] == pytest.approx(clock.now + 590)

    def test_expired_throttle_not_restored(self, db_path, clock, no_jitter):
        a = RateLimiter(min_interval=0, jitter=0, db_path=db_path)
        a._set_throttle('rate', clock.now + 5)
        a.close()
        clock.now += 10
        b = RateLimiter(min_interval=0, jitter=0, db_path=db_path)
        assert b.get_throttle_state()['throttled'] is False

    def test_daily_counter_rolls_on_reload_after_midnight(self, db_path, clock):
        a = RateLimiter(daily_limit=10, per_minute_limit=100, min_interval=0, jitter=0, db_path=db_path)
        for _ in range(7):
            a.record_request()
        a.close()
        clock.now += 86400 * 2
        b = RateLimiter(daily_limit=10, per_minute_limit=100, min_interval=0, jitter=0, db_path=db_path)
        assert b.daily_operations == 0

    def test_reset_clears_persisted_state(self, db_path, clock):
        a = RateLimiter(min_interval=0, jitter=0, db_path=db_path)
        a.record_request()
        a.backoff_seconds = 240
        a.reset()
        a.close()
        b = RateLimiter(min_interval=0, jitter=0, db_path=db_path)
        assert b.daily_operations == 0
        assert len(b.request_times) == 0
        assert b.backoff_seconds == RateLimiter.MIN_BACKOFF_SECONDS

    def test_unusable_db_path_degrades_to_in_memory(self, tmp_path, clock):
        bad = str(tmp_path / 'not_a_dir' / 'nested' / 'cache.db')  # parent missing
        limiter = RateLimiter(db_path=bad)
        assert limiter.get_current_stats()['persistent'] is False
        limiter.record_request()      # no exception
        limiter.close()

    def test_corrupt_state_is_ignored(self, db_path, clock):
        RateLimiter(db_path=db_path).close()
        with sqlite3.connect(db_path) as conn:
            conn.execute("INSERT OR REPLACE INTO rate_limit_state VALUES ('request_times', 'garbage')")
            conn.execute("INSERT OR REPLACE INTO rate_limit_state VALUES ('daily_operations', '3')")
        limiter = RateLimiter(db_path=db_path)
        assert len(limiter.request_times) == 0
        limiter.close()

    def test_no_db_path_means_in_memory(self, clock):
        limiter = RateLimiter()
        assert limiter.get_current_stats()['persistent'] is False
        limiter.close()  # harmless

    def test_close_is_idempotent(self, db_path, clock):
        limiter = RateLimiter(db_path=db_path)
        limiter.close()
        limiter.close()


# ---------------------------------------------------------------------------
# Full cycle
# ---------------------------------------------------------------------------
class TestIntegration:
    def test_full_request_cycle_is_paced_not_cliff_stopped(self, clock, no_jitter):
        limiter = RateLimiter(per_minute_limit=1000, min_interval=1.0, jitter=0.5)
        for _ in range(100):
            limiter.check_limit()
            limiter.record_request()
        # 99 gaps of exactly 1.5 s; no gap ever longer than the pacing interval.
        assert clock.total_slept == pytest.approx(99 * 1.5)
        assert max(clock.sleeps) <= 1.5
        assert limiter.get_throttle_state()['throttled'] is False
