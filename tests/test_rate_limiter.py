"""
Tests for RateLimiter.

This module contains comprehensive tests for the rate limiting functionality,
including daily limits, per-minute limits, backoff strategies, and date handling.
"""

import time
from datetime import date, timedelta
from unittest.mock import patch, Mock

import pytest

from src.utils.rate_limiter import RateLimiter


@pytest.fixture
def rate_limiter():
    """Create a RateLimiter instance with small limits for testing."""
    return RateLimiter(daily_limit=10, per_minute_limit=5)


@pytest.fixture
def default_rate_limiter():
    """Create a RateLimiter instance with default limits."""
    return RateLimiter()


class TestRateLimiterInitialization:
    """Tests for RateLimiter initialization."""

    def test_init_with_custom_limits(self):
        """Test initialization with custom limits."""
        limiter = RateLimiter(daily_limit=100, per_minute_limit=10)
        
        assert limiter.daily_limit == 100
        assert limiter.per_minute_limit == 10
        assert limiter.daily_operations == 0
        assert limiter.last_reset == date.today()
        assert len(limiter.request_times) == 0
        assert limiter.backoff_seconds == RateLimiter.MIN_BACKOFF_SECONDS

    def test_init_with_default_limits(self):
        """Test initialization with default limits."""
        limiter = RateLimiter()
        
        assert limiter.daily_limit == RateLimiter.DEFAULT_DAILY_LIMIT
        assert limiter.per_minute_limit == RateLimiter.DEFAULT_PER_MINUTE_LIMIT

    def test_init_with_invalid_daily_limit(self):
        """Test initialization with invalid daily limit."""
        with pytest.raises(ValueError, match="Rate limits must be positive integers"):
            RateLimiter(daily_limit=0, per_minute_limit=10)

    def test_init_with_invalid_per_minute_limit(self):
        """Test initialization with invalid per-minute limit."""
        with pytest.raises(ValueError, match="Rate limits must be positive integers"):
            RateLimiter(daily_limit=10, per_minute_limit=-5)


class TestRecordRequest:
    """Tests for recording requests."""

    def test_record_request_increments_daily_operations(self, rate_limiter):
        """Test that recording a request increments daily operations counter."""
        assert rate_limiter.daily_operations == 0
        
        rate_limiter.record_request()
        assert rate_limiter.daily_operations == 1
        
        rate_limiter.record_request()
        assert rate_limiter.daily_operations == 2

    def test_record_request_adds_timestamp(self, rate_limiter):
        """Test that recording a request adds timestamp to deque."""
        assert len(rate_limiter.request_times) == 0
        
        with patch('time.time', return_value=1000.0):
            rate_limiter.record_request()
        
        assert len(rate_limiter.request_times) == 1
        assert rate_limiter.request_times[0] == 1000.0

    def test_record_request_deque_maxlen(self, rate_limiter):
        """Test that request_times deque respects maxlen."""
        # Record more requests than per_minute_limit
        for i in range(10):
            with patch('time.time', return_value=float(i)):
                rate_limiter.record_request()
        
        # Should only keep the most recent per_minute_limit (5) requests
        assert len(rate_limiter.request_times) == 5
        assert list(rate_limiter.request_times) == [5.0, 6.0, 7.0, 8.0, 9.0]


class TestDailyLimitEnforcement:
    """Tests for daily limit enforcement."""

    @patch('time.time')
    @patch('time.sleep')
    def test_daily_limit_enforcement(self, mock_sleep, mock_time, rate_limiter):
        """Test that daily limit causes pause when exceeded."""
        # Mock time to prevent per-minute rate limiting
        mock_time.return_value = 1000.0
        
        # Make 10 requests (at the limit)
        for i in range(10):
            mock_time.return_value = 1000.0 + (i * 100)  # Space out requests
            rate_limiter.record_request()
        
        assert rate_limiter.daily_operations == 10
        
        # 11th request should trigger a pause
        rate_limiter.check_limit()
        
        # Should have slept for 1 hour (3600 seconds)
        assert any(call[0][0] == 3600 for call in mock_sleep.call_args_list)

    @patch('time.time')
    @patch('time.sleep')
    def test_daily_limit_no_pause_below_limit(self, mock_sleep, mock_time, rate_limiter):
        """Test that no pause occurs when below daily limit."""
        # Mock time to prevent per-minute rate limiting
        mock_time.return_value = 1000.0
        
        # Make 9 requests (below limit of 10)
        for i in range(9):
            mock_time.return_value = 1000.0 + (i * 100)  # Space out requests
            rate_limiter.record_request()
        
        rate_limiter.check_limit()
        
        # Should not have slept for daily limit (3600 seconds)
        assert not any(call[0][0] == 3600 for call in mock_sleep.call_args_list)

    @patch('time.time')
    @patch('time.sleep')
    def test_daily_limit_at_exact_limit(self, mock_sleep, mock_time, rate_limiter):
        """Test behavior at exact daily limit."""
        # Mock time to prevent per-minute rate limiting
        mock_time.return_value = 1000.0
        
        # Make exactly 10 requests
        for i in range(10):
            mock_time.return_value = 1000.0 + (i * 100)  # Space out requests
            rate_limiter.record_request()
        
        # Next check should trigger pause
        rate_limiter.check_limit()
        
        # Should have slept for 3600 seconds (daily limit)
        assert any(call[0][0] == 3600 for call in mock_sleep.call_args_list)


class TestDailyLimitReset:
    """Tests for daily limit reset at midnight."""

    @patch('time.time')
    @patch('src.utils.rate_limiter.date')
    @patch('time.sleep')
    def test_daily_limit_reset_at_midnight(self, mock_sleep, mock_date, mock_time, rate_limiter):
        """Test that daily counter resets on date change."""
        # Mock time to prevent per-minute rate limiting
        mock_time.return_value = 1000.0
        
        # Set initial date
        today = date(2024, 1, 1)
        tomorrow = date(2024, 1, 2)
        mock_date.today.return_value = today
        
        # Manually set the rate limiter's last_reset to today
        rate_limiter.last_reset = today
        
        # Make 9 requests (just below limit)
        for i in range(9):
            mock_time.return_value = 1000.0 + (i * 100)  # Space out requests
            rate_limiter.record_request()
        
        assert rate_limiter.daily_operations == 9
        
        # Change to next day
        mock_date.today.return_value = tomorrow

        # Make one more request on the new day
        # check_limit() will detect date change and reset counter to 0
        rate_limiter.check_limit()
        # record_request() will increment to 1
        rate_limiter.record_request()

        # Counter should show 1 request on new day
        assert rate_limiter.daily_operations == 1
        # Verify last_reset was updated to new day
        assert rate_limiter.last_reset == tomorrow
        assert rate_limiter.last_reset == tomorrow
        
        # Should not have slept for daily limit (3600) since we're under limit after reset
        assert not any(call[0][0] == 3600 for call in mock_sleep.call_args_list)

    @patch('src.utils.rate_limiter.date')
    def test_daily_limit_reset_updates_last_reset_date(self, mock_date, rate_limiter):
        """Test that last_reset is updated on date change."""
        day1 = date(2024, 1, 1)
        day2 = date(2024, 1, 2)
        
        mock_date.today.return_value = day1
        rate_limiter.last_reset = day1
        rate_limiter.daily_operations = 5
        
        # Change to next day
        mock_date.today.return_value = day2
        
        # Trigger reset by checking limits
        rate_limiter._reset_daily_counter()
        
        assert rate_limiter.last_reset == day2
        assert rate_limiter.daily_operations == 0


class TestPerMinuteRateLimiting:
    """Tests for per-minute rate limiting."""

    @patch('time.time')
    @patch('time.sleep')
    def test_per_minute_rate_limiting_enforced(self, mock_sleep, mock_time, rate_limiter):
        """Test that per-minute limit causes pause when exceeded."""
        # Set up: 5 requests in the last 30 seconds (per_minute_limit=5)
        current_time = 1000.0
        mock_time.return_value = current_time
        
        # Add 5 requests, all within last 30 seconds
        for i in range(5):
            mock_time.return_value = current_time - 30 + (i * 5)
            rate_limiter.request_times.append(mock_time.return_value)
        
        # Reset to current time
        mock_time.return_value = current_time
        
        # 6th request should trigger a wait
        rate_limiter.check_limit()
        
        # Should have waited for the remaining time in the minute
        # Oldest request is at 970, current is 1000, so 30 seconds have passed
        # Need to wait 60 - 30 = 30 more seconds
        mock_sleep.assert_called_once()
        wait_time = mock_sleep.call_args[0][0]
        assert 29 <= wait_time <= 31  # Allow small float precision differences

    @patch('time.time')
    @patch('time.sleep')
    def test_per_minute_rate_no_pause_below_limit(self, mock_sleep, mock_time, rate_limiter):
        """Test that no pause occurs when below per-minute limit."""
        current_time = 1000.0
        mock_time.return_value = current_time
        
        # Add 4 requests (below limit of 5)
        for i in range(4):
            rate_limiter.request_times.append(current_time - (i * 10))
        
        rate_limiter.check_limit()
        
        # Should not have slept
        mock_sleep.assert_not_called()

    @patch('time.time')
    @patch('time.sleep')
    def test_per_minute_rate_old_requests_ignored(self, mock_sleep, mock_time, rate_limiter):
        """Test that requests older than 60 seconds don't block new requests."""
        current_time = 1000.0
        mock_time.return_value = current_time
        
        # Add 5 requests, but oldest is >60 seconds ago
        for i in range(5):
            rate_limiter.request_times.append(current_time - 70 + (i * 2))
        
        # Oldest request is at 930 (70 seconds ago)
        # Current time is 1000
        # Since >60 seconds have passed, no wait needed
        rate_limiter.check_limit()
        
        # Should not have slept
        mock_sleep.assert_not_called()


class TestHandle429:
    """Tests for handling HTTP 429 responses."""

    @patch('time.sleep')
    def test_handle_429_with_retry_after(self, mock_sleep, rate_limiter):
        """Test that handle_429 respects Retry-After header."""
        rate_limiter.handle_429(retry_after=120)
        
        # Should sleep for exactly the retry_after value
        mock_sleep.assert_called_once_with(120)

    @patch('time.sleep')
    def test_handle_429_exponential_backoff(self, mock_sleep, rate_limiter):
        """Test exponential backoff without Retry-After header."""
        # First 429
        rate_limiter.handle_429()
        mock_sleep.assert_called_with(60)  # MIN_BACKOFF_SECONDS
        
        # Second 429 - should double
        rate_limiter.handle_429()
        mock_sleep.assert_called_with(120)
        
        # Third 429 - should double again
        rate_limiter.handle_429()
        mock_sleep.assert_called_with(240)

    @patch('time.sleep')
    def test_handle_429_backoff_max_cap(self, mock_sleep, rate_limiter):
        """Test that backoff is capped at MAX_BACKOFF_SECONDS."""
        # Set backoff to max
        rate_limiter.backoff_seconds = RateLimiter.MAX_BACKOFF_SECONDS
        
        rate_limiter.handle_429()
        
        # Should not exceed max
        mock_sleep.assert_called_with(RateLimiter.MAX_BACKOFF_SECONDS)
        assert rate_limiter.backoff_seconds == RateLimiter.MAX_BACKOFF_SECONDS

    @patch('time.sleep')
    def test_handle_429_backoff_progression(self, mock_sleep, rate_limiter):
        """Test full backoff progression: 60, 120, 240, 300 (capped)."""
        expected_sleeps = [60, 120, 240, 300, 300]  # Last two capped at 300
        
        for expected in expected_sleeps:
            rate_limiter.handle_429()
            mock_sleep.assert_called_with(expected)


class TestResetBackoff:
    """Tests for backoff reset functionality."""

    def test_reset_backoff(self, rate_limiter):
        """Test that reset_backoff resets to minimum."""
        # Increase backoff
        rate_limiter.backoff_seconds = 240
        
        rate_limiter.reset_backoff()
        
        assert rate_limiter.backoff_seconds == RateLimiter.MIN_BACKOFF_SECONDS

    def test_reset_backoff_idempotent(self, rate_limiter):
        """Test that resetting already-minimum backoff is safe."""
        assert rate_limiter.backoff_seconds == RateLimiter.MIN_BACKOFF_SECONDS
        
        rate_limiter.reset_backoff()
        
        assert rate_limiter.backoff_seconds == RateLimiter.MIN_BACKOFF_SECONDS


class TestReset:
    """Tests for full rate limiter reset."""

    def test_reset_clears_all_counters(self, rate_limiter):
        """Test that reset() clears all tracking data."""
        # Populate limiter with data
        for _ in range(5):
            rate_limiter.record_request()
        
        rate_limiter.backoff_seconds = 240
        
        assert rate_limiter.daily_operations == 5
        assert len(rate_limiter.request_times) == 5
        assert rate_limiter.backoff_seconds == 240
        
        # Reset everything
        rate_limiter.reset()
        
        assert rate_limiter.daily_operations == 0
        assert len(rate_limiter.request_times) == 0
        assert rate_limiter.backoff_seconds == RateLimiter.MIN_BACKOFF_SECONDS
        assert rate_limiter.last_reset == date.today()

    def test_reset_updates_last_reset_date(self, rate_limiter):
        """Test that reset() updates last_reset to today."""
        # Set to old date
        rate_limiter.last_reset = date(2023, 1, 1)
        
        rate_limiter.reset()
        
        assert rate_limiter.last_reset == date.today()


class TestGetRemainingOperations:
    """Tests for remaining operations calculation."""

    def test_get_remaining_operations(self, rate_limiter):
        """Test calculation of remaining daily operations."""
        assert rate_limiter.get_remaining_daily_operations() == 10
        
        rate_limiter.record_request()
        assert rate_limiter.get_remaining_daily_operations() == 9
        
        for _ in range(5):
            rate_limiter.record_request()
        assert rate_limiter.get_remaining_daily_operations() == 4

    def test_get_remaining_operations_at_limit(self, rate_limiter):
        """Test remaining operations when at limit."""
        for _ in range(10):
            rate_limiter.record_request()
        
        assert rate_limiter.get_remaining_daily_operations() == 0

    def test_get_remaining_operations_over_limit(self, rate_limiter):
        """Test remaining operations when over limit (should return 0)."""
        for _ in range(15):
            rate_limiter.record_request()
        
        # Should not go negative
        assert rate_limiter.get_remaining_daily_operations() == 0


class TestGetCurrentStats:
    """Tests for statistics retrieval."""

    def test_get_current_stats(self, rate_limiter):
        """Test that get_current_stats returns correct data."""
        rate_limiter.record_request()
        rate_limiter.record_request()
        
        stats = rate_limiter.get_current_stats()
        
        assert stats['daily_operations'] == 2
        assert stats['daily_limit'] == 10
        assert stats['remaining_operations'] == 8
        assert stats['requests_in_window'] == 2
        assert stats['per_minute_limit'] == 5
        assert stats['backoff_seconds'] == RateLimiter.MIN_BACKOFF_SECONDS
        assert stats['last_reset'] == date.today().isoformat()

    def test_get_current_stats_structure(self, rate_limiter):
        """Test that stats dict has all expected keys."""
        stats = rate_limiter.get_current_stats()
        
        expected_keys = [
            'daily_operations',
            'daily_limit',
            'remaining_operations',
            'requests_in_window',
            'per_minute_limit',
            'backoff_seconds',
            'last_reset'
        ]
        
        for key in expected_keys:
            assert key in stats


class TestRepr:
    """Tests for string representation."""

    def test_repr(self, rate_limiter):
        """Test string representation of RateLimiter."""
        rate_limiter.record_request()
        rate_limiter.record_request()
        
        repr_str = repr(rate_limiter)
        
        assert 'RateLimiter' in repr_str
        assert '2/10' in repr_str  # daily operations
        assert '2/5' in repr_str   # requests in window
        assert '60s' in repr_str   # backoff


class TestIntegration:
    """Integration tests for RateLimiter."""

    @patch('time.time')
    @patch('time.sleep')
    def test_full_request_cycle(self, mock_sleep, mock_time, rate_limiter):
        """Test complete request cycle: check -> record -> repeat."""
        current_time = 1000.0
        mock_time.return_value = current_time
        
        # Make 5 requests (at per-minute limit)
        for i in range(5):
            mock_time.return_value = current_time + i
            rate_limiter.check_limit()
            rate_limiter.record_request()
        
        # Should not have slept yet
        mock_sleep.assert_not_called()
        
        # 6th request should trigger wait
        mock_time.return_value = current_time + 10
        rate_limiter.check_limit()
        
        # Should have slept to enforce per-minute limit
        mock_sleep.assert_called_once()

    @patch('time.time')
    @patch('src.utils.rate_limiter.date')
    @patch('time.sleep')
    def test_daily_limit_with_date_rollover(self, mock_sleep, mock_date, mock_time, rate_limiter):
        """Test daily limit reset during pause for exceeded limit."""
        # Mock time to prevent per-minute rate limiting
        mock_time.return_value = 1000.0
        
        day1 = date(2024, 1, 1)
        day2 = date(2024, 1, 2)
        
        # Start on day 1
        mock_date.today.return_value = day1
        rate_limiter.last_reset = day1
        
        # Reach daily limit
        for i in range(10):
            mock_time.return_value = 1000.0 + (i * 100)  # Space out requests
            rate_limiter.record_request()
        
        # During the sleep for exceeding limit, date changes
        def sleep_and_change_date(seconds):
            if seconds == 3600:  # Only change date on daily limit sleep
                mock_date.today.return_value = day2
        
        mock_sleep.side_effect = sleep_and_change_date
        
        # This should trigger pause, then reset during pause
        rate_limiter.check_limit()
        
        # Should have slept for daily limit
        assert any(call[0][0] == 3600 for call in mock_sleep.call_args_list)
        
        # Counter should be reset
        assert rate_limiter.daily_operations == 0
        assert rate_limiter.last_reset == day2

    @patch('time.sleep')
    def test_429_recovery_flow(self, mock_sleep, rate_limiter):
        """Test flow of hitting 429, backing off, then recovering."""
        # Hit a 429
        rate_limiter.handle_429()
        assert rate_limiter.backoff_seconds == 120
        
        # Hit another 429
        rate_limiter.handle_429()
        assert rate_limiter.backoff_seconds == 240
        
        # Successful request - reset backoff
        rate_limiter.reset_backoff()
        assert rate_limiter.backoff_seconds == RateLimiter.MIN_BACKOFF_SECONDS


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_zero_per_minute_limit_rejected(self):
        """Test that zero per-minute limit is rejected."""
        with pytest.raises(ValueError):
            RateLimiter(daily_limit=100, per_minute_limit=0)

    def test_negative_limits_rejected(self):
        """Test that negative limits are rejected."""
        with pytest.raises(ValueError):
            RateLimiter(daily_limit=-1, per_minute_limit=10)

    @patch('time.time')
    def test_concurrent_requests_deque_behavior(self, mock_time, rate_limiter):
        """Test deque behavior with rapid concurrent-like requests."""
        # Simulate many rapid requests
        for i in range(20):
            mock_time.return_value = 1000.0 + (i * 0.1)
            rate_limiter.record_request()
        
        # Deque should only keep most recent per_minute_limit (5) requests
        assert len(rate_limiter.request_times) == 5

    def test_handle_429_with_zero_retry_after(self, rate_limiter):
        """Test handling 429 with retry_after=0."""
        with patch('time.sleep') as mock_sleep:
            rate_limiter.handle_429(retry_after=0)
            mock_sleep.assert_called_once_with(0)

    def test_multiple_resets(self, rate_limiter):
        """Test that multiple resets don't cause issues."""
        rate_limiter.reset()
        rate_limiter.reset()
        rate_limiter.reset()
        
        assert rate_limiter.daily_operations == 0
        assert len(rate_limiter.request_times) == 0
