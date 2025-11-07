"""Rate Limiting Module.

This module provides rate limiting functionality to comply with API rate limits
and handle HTTP 429 (Too Many Requests) responses gracefully.
"""

import time
import logging
from collections import deque
from datetime import datetime, date, timedelta
from typing import Optional, Deque


# Configure logging
logger = logging.getLogger(__name__)


class RateLimiter:
    """API rate limiter with daily and per-minute limits.
    
    This class tracks and enforces rate limits to prevent exceeding API quotas.
    It supports both daily operation limits and per-minute request rates, with
    automatic counter resets and exponential backoff for rate limit errors.
    
    Features:
    - Daily operation limit tracking (default: 15,000/day)
    - Per-minute rate limiting (default: 100 requests/minute)
    - Automatic daily counter reset at midnight
    - Exponential backoff for HTTP 429 responses
    - Configurable limits for different APIs
    
    Attributes:
        daily_limit (int): Maximum operations allowed per day.
        per_minute_limit (int): Maximum requests allowed per minute.
        daily_operations (int): Current count of operations today.
        last_reset (date): Date of last daily counter reset.
        request_times (Deque[float]): Timestamps of recent requests (for rate tracking).
        backoff_seconds (int): Current backoff duration for 429 responses.
    """
    
    DEFAULT_DAILY_LIMIT = 15000
    DEFAULT_PER_MINUTE_LIMIT = 100
    MIN_BACKOFF_SECONDS = 60
    MAX_BACKOFF_SECONDS = 300
    PAUSE_ON_DAILY_LIMIT_HOURS = 1
    
    def __init__(self, daily_limit: int = DEFAULT_DAILY_LIMIT, per_minute_limit: int = DEFAULT_PER_MINUTE_LIMIT):
        """Initialize the rate limiter with specified limits.
        
        Args:
            daily_limit (int): Maximum number of operations allowed per day.
                Defaults to 15,000.
            per_minute_limit (int): Maximum number of requests allowed per minute.
                Defaults to 100.
                
        Raises:
            ValueError: If limits are not positive integers.
        """
        if daily_limit <= 0 or per_minute_limit <= 0:
            raise ValueError("Rate limits must be positive integers")
        
        self.daily_limit = daily_limit
        self.per_minute_limit = per_minute_limit
        
        # Daily operation tracking
        self.daily_operations = 0
        self.last_reset = date.today()
        
        # Per-minute rate tracking using a deque with fixed size
        # Only keeps the most recent per_minute_limit timestamps
        self.request_times: Deque[float] = deque(maxlen=per_minute_limit)
        
        # Backoff tracking for 429 responses
        self.backoff_seconds = self.MIN_BACKOFF_SECONDS
        
        logger.info(
            f"RateLimiter initialized: {daily_limit} ops/day, "
            f"{per_minute_limit} requests/minute"
        )
    
    def _reset_daily_counter(self) -> None:
        """Reset the daily operations counter if it's a new day.
        
        Checks if the current date is different from last_reset, and if so,
        resets the daily_operations counter to 0 and updates last_reset.
        """
        today = date.today()
        if today > self.last_reset:
            logger.info(
                f"Daily counter reset: {self.daily_operations} operations "
                f"on {self.last_reset}"
            )
            self.daily_operations = 0
            self.last_reset = today
    
    def _check_daily_limit(self) -> None:
        """Check if daily operation limit has been reached.
        
        If the daily limit is reached or exceeded, pauses execution for
        1 hour to avoid further quota violations.
        
        Raises:
            None, but sleeps for PAUSE_ON_DAILY_LIMIT_HOURS if limit reached.
        """
        if self.daily_operations >= self.daily_limit:
            pause_seconds = self.PAUSE_ON_DAILY_LIMIT_HOURS * 3600
            logger.warning(
                f"Daily limit reached ({self.daily_operations}/{self.daily_limit}). "
                f"Pausing for {self.PAUSE_ON_DAILY_LIMIT_HOURS} hour(s)."
            )
            time.sleep(pause_seconds)
            
            # Check if we've crossed into a new day during the pause
            self._reset_daily_counter()
    
    def _check_per_minute_rate(self) -> None:
        """Check if per-minute request rate is being exceeded.
        
        Examines the timestamps in request_times to determine if we're
        exceeding the per-minute rate limit. If so, calculates the required
        wait time and pauses execution.
        
        The deque automatically maintains only the most recent per_minute_limit
        requests, making rate calculation efficient.
        """
        if len(self.request_times) < self.per_minute_limit:
            # Haven't reached the limit yet, no need to wait
            return
        
        # The deque is full, check if all requests are within the last minute
        current_time = time.time()
        oldest_request = self.request_times[0]
        time_since_oldest = current_time - oldest_request
        
        # If the oldest request in our window is less than 60 seconds old,
        # we need to wait before making another request
        if time_since_oldest < 60:
            wait_time = 60 - time_since_oldest
            logger.info(
                f"Per-minute rate limit approaching ({self.per_minute_limit} requests/min). "
                f"Waiting {wait_time:.2f} seconds."
            )
            time.sleep(wait_time)
    
    def check_limit(self) -> None:
        """Check rate limits before making an API request.
        
        This method should be called before each API request to ensure
        compliance with rate limits. It performs the following checks:
        
        1. Resets daily counter if it's a new day
        2. Checks if daily limit has been reached (pauses if so)
        3. Checks if per-minute rate is being exceeded (waits if so)
        
        The method will block (sleep) if necessary to comply with limits.
        
        Example:
            >>> limiter = RateLimiter()
            >>> limiter.check_limit()  # Checks limits
            >>> # Make API request here
            >>> limiter.record_request()  # Record the request
        """
        # Reset daily counter if needed
        self._reset_daily_counter()
        
        # Check daily limit
        self._check_daily_limit()
        
        # Check per-minute rate
        self._check_per_minute_rate()
    
    def record_request(self) -> None:
        """Record that an API request was made.
        
        Updates tracking counters after a successful API request:
        - Appends current timestamp to request_times deque
        - Increments daily_operations counter
        
        This method should be called immediately after making an API request.
        
        Example:
            >>> limiter = RateLimiter()
            >>> limiter.check_limit()
            >>> response = api.make_request()  # Your API call
            >>> limiter.record_request()
        """
        current_time = time.time()
        self.request_times.append(current_time)
        self.daily_operations += 1
        
        logger.debug(
            f"Request recorded: {self.daily_operations}/{self.daily_limit} daily, "
            f"{len(self.request_times)} requests in current window"
        )
    
    def handle_429(self, retry_after: Optional[int] = None) -> None:
        """Handle HTTP 429 (Too Many Requests) response.
        
        Implements intelligent backoff when receiving rate limit errors:
        
        1. If Retry-After header is provided, uses that value
        2. Otherwise, uses exponential backoff starting at 60 seconds,
           doubling with each 429, up to a maximum of 300 seconds
        3. Sleeps for the calculated duration
        4. Resets backoff on successful requests (call reset_backoff())
        
        Args:
            retry_after (Optional[int]): Value from Retry-After header in seconds.
                If None, uses exponential backoff.
                
        Example:
            >>> limiter = RateLimiter()
            >>> try:
            ...     response = api.make_request()
            ...     if response.status_code == 429:
            ...         retry_after = response.headers.get('Retry-After')
            ...         limiter.handle_429(int(retry_after) if retry_after else None)
            ... except Exception as e:
            ...     pass
        """
        if retry_after is not None:
            # Use Retry-After header value
            wait_seconds = retry_after
            logger.warning(
                f"HTTP 429 received with Retry-After: {retry_after}s. "
                f"Waiting {wait_seconds} seconds."
            )
        else:
            # Use exponential backoff
            wait_seconds = min(self.backoff_seconds, self.MAX_BACKOFF_SECONDS)
            logger.warning(
                f"HTTP 429 received. Using exponential backoff: {wait_seconds}s. "
                f"(Next backoff will be {min(self.backoff_seconds * 2, self.MAX_BACKOFF_SECONDS)}s)"
            )
            
            # Increase backoff for next time (exponential)
            self.backoff_seconds = min(self.backoff_seconds * 2, self.MAX_BACKOFF_SECONDS)
        
        time.sleep(wait_seconds)
    
    def reset_backoff(self) -> None:
        """Reset the exponential backoff to its initial value.
        
        Call this method after successful API requests to reset the backoff
        counter. This ensures that temporary rate limit issues don't cause
        permanent slowdowns.
        
        Example:
            >>> limiter = RateLimiter()
            >>> response = api.make_request()
            >>> if response.status_code == 200:
            ...     limiter.reset_backoff()
            >>> elif response.status_code == 429:
            ...     limiter.handle_429()
        """
        if self.backoff_seconds > self.MIN_BACKOFF_SECONDS:
            logger.debug(f"Resetting backoff from {self.backoff_seconds}s to {self.MIN_BACKOFF_SECONDS}s")
        self.backoff_seconds = self.MIN_BACKOFF_SECONDS
    
    def reset(self) -> None:
        """Reset all rate limiting counters and state.
        
        Clears all tracking data:
        - Resets daily operations to 0
        - Updates last_reset to today
        - Clears request_times deque
        - Resets backoff to initial value
        
        This is primarily useful for testing or when switching API contexts.
        
        Warning:
            Resetting counters may cause quota violations if called carelessly.
            Use only when you're certain the slate should be wiped clean.
        """
        logger.info("Resetting all rate limiting counters")
        self.daily_operations = 0
        self.last_reset = date.today()
        self.request_times.clear()
        self.backoff_seconds = self.MIN_BACKOFF_SECONDS
    
    def get_remaining_daily_operations(self) -> int:
        """Get the number of remaining operations for today.
        
        Returns:
            int: Number of operations remaining before hitting daily limit.
        """
        self._reset_daily_counter()
        return max(0, self.daily_limit - self.daily_operations)
    
    def get_current_stats(self) -> dict:
        """Get current rate limiting statistics.
        
        Returns:
            dict: Dictionary containing current rate limiting stats:
                - daily_operations: Current operation count
                - daily_limit: Maximum daily operations
                - remaining_operations: Operations remaining today
                - requests_in_window: Number of requests in current minute window
                - per_minute_limit: Maximum requests per minute
                - backoff_seconds: Current backoff duration
                - last_reset: Date of last daily counter reset
        """
        self._reset_daily_counter()
        return {
            "daily_operations": self.daily_operations,
            "daily_limit": self.daily_limit,
            "remaining_operations": self.get_remaining_daily_operations(),
            "requests_in_window": len(self.request_times),
            "per_minute_limit": self.per_minute_limit,
            "backoff_seconds": self.backoff_seconds,
            "last_reset": self.last_reset.isoformat()
        }
    
    def __repr__(self) -> str:
        """Return string representation of the RateLimiter.
        
        Returns:
            str: String representation with current stats.
        """
        return (
            f"RateLimiter(daily={self.daily_operations}/{self.daily_limit}, "
            f"window={len(self.request_times)}/{self.per_minute_limit}, "
            f"backoff={self.backoff_seconds}s)"
        )
