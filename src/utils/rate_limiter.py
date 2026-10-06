"""Rate Limiting Module.

Sustained-rate pacing for the internal web APIs this app drives (ytmusicapi and
Spotify Web API), with persistent counters and a *visible* throttle state.

Policy (why it looks like this)
-------------------------------
The app talks to YouTube Music through ytmusicapi -- the same internal endpoints
the web player uses -- not the YouTube Data API v3. There is no published quota
to count against; what matters is to look like a steady, human-paced client and
never burst. So the policy is:

* a minimum interval between requests, with random jitter, so throughput is
  *paced* rather than cliff-stopped;
* a per-minute ceiling as a safety net against accidental bursts;
* an *optional* daily ceiling (off by default) for callers that want one;
* HTTP 429 handling with exponential backoff that honours ``Retry-After``, and a
  distinct ``'quota'`` reason for Spotify dev-mode ``QUOTA_EXCEEDED`` responses.

Every wait is bounded and observable: long waits are taken in slices of at most
``max_wait_slice`` seconds, the current throttle state is readable at any time
via :meth:`RateLimiter.get_throttle_state`, and an optional ``on_throttle``
callback is invoked whenever that state changes. There is no silent hour-long
sleep anywhere in this module.

Counters survive restarts: when a ``db_path`` is given, the limiter keeps its
state in its own ``rate_limit_state`` table inside the app's SQLite database
(the same file ``CacheManager`` uses, but a separate connection and table). If
the database is unavailable the limiter degrades to in-memory operation.

Typical use (unchanged from the previous API)::

    limiter.check_limit()           # paces / blocks as needed
    response = api.call()
    limiter.record_request()
    limiter.reset_backoff()

    # on HTTP 429:
    limiter.handle_429(retry_after)                     # transient rate limit
    limiter.handle_429(retry_after, reason='quota')     # QUOTA_EXCEEDED
"""

import json
import logging
import random
import sqlite3
import threading
import time
from collections import deque
from datetime import date, datetime, timedelta
from typing import Any, Callable, Deque, Dict, Optional


logger = logging.getLogger(__name__)


ThrottleCallback = Callable[[Dict[str, Any]], None]


class RateLimiter:
    """Sustained-rate API limiter with persistent counters and visible state.

    Attributes:
        per_minute_limit (int): Burst ceiling -- max requests in any 60 s window.
        min_interval (float): Minimum seconds between two requests (before jitter).
        jitter (float): Upper bound of the random extra delay added to min_interval.
        daily_limit (Optional[int]): Optional daily ceiling; ``None`` = no ceiling.
        daily_operations (int): Requests recorded today.
        last_reset (date): Day the daily counter belongs to.
        request_times (Deque[float]): Timestamps of the most recent requests.
        backoff_seconds (int): Current exponential backoff for 429 responses.
    """

    # Sustained-rate policy defaults (internal web API, not a Data-API quota).
    DEFAULT_PER_MINUTE_LIMIT = 40
    DEFAULT_MIN_INTERVAL_SECONDS = 1.0
    DEFAULT_JITTER_SECONDS = 0.5
    DEFAULT_DAILY_LIMIT: Optional[int] = None

    # 429 backoff.
    MIN_BACKOFF_SECONDS = 60
    MAX_BACKOFF_SECONDS = 300

    # Longest single sleep. Longer waits are taken in slices so the state
    # stays observable and an interrupt can end them early.
    DEFAULT_MAX_WAIT_SLICE_SECONDS = 30.0

    # Pacing waits shorter than this are ordinary throughput shaping and do not
    # flip the visible "throttled" state.
    THROTTLE_VISIBILITY_THRESHOLD_SECONDS = 5.0

    REASON_RATE = 'rate'
    REASON_QUOTA = 'quota'

    TABLE_NAME = 'rate_limit_state'

    def __init__(
        self,
        daily_limit: Optional[int] = DEFAULT_DAILY_LIMIT,
        per_minute_limit: int = DEFAULT_PER_MINUTE_LIMIT,
        min_interval: float = DEFAULT_MIN_INTERVAL_SECONDS,
        jitter: float = DEFAULT_JITTER_SECONDS,
        db_path: Optional[str] = None,
        on_throttle: Optional[ThrottleCallback] = None,
        max_wait_slice: float = DEFAULT_MAX_WAIT_SLICE_SECONDS,
        interrupt_event: Optional[threading.Event] = None,
    ):
        """Create a limiter.

        Args:
            daily_limit: Optional daily request ceiling. ``None`` (default)
                disables the daily ceiling entirely. Hitting a configured ceiling
                sets a visible ``'quota'`` throttle until local midnight; it never
                sleeps silently.
            per_minute_limit: Maximum requests in any rolling 60 s window.
            min_interval: Minimum seconds between consecutive requests.
            jitter: Random extra delay in ``[0, jitter]`` added to ``min_interval``.
            db_path: SQLite file to persist counters in (own table). ``None``
                keeps everything in memory.
            on_throttle: Called with the throttle-state dict whenever the state
                changes (throttled on/off, reason, until).
            max_wait_slice: Longest single ``time.sleep`` call.
            interrupt_event: Optional event; when set, any in-progress wait ends
                early (used by shutdown).

        Raises:
            ValueError: If a limit is not positive or an interval is negative.
        """
        if daily_limit is not None and daily_limit <= 0:
            raise ValueError("Rate limits must be positive integers")
        if per_minute_limit <= 0:
            raise ValueError("Rate limits must be positive integers")
        if min_interval < 0 or jitter < 0:
            raise ValueError("min_interval and jitter must be non-negative")
        if max_wait_slice <= 0:
            raise ValueError("max_wait_slice must be positive")

        self.daily_limit = daily_limit
        self.per_minute_limit = per_minute_limit
        self.min_interval = float(min_interval)
        self.jitter = float(jitter)
        self.max_wait_slice = float(max_wait_slice)
        self.on_throttle = on_throttle
        self.interrupt_event = interrupt_event

        self._lock = threading.RLock()

        # Counters.
        self.daily_operations = 0
        self.last_reset: date = self._today()
        self.request_times: Deque[float] = deque(maxlen=per_minute_limit)
        self.last_request_at: Optional[float] = None
        self.backoff_seconds = self.MIN_BACKOFF_SECONDS

        # Visible throttle state.
        self._throttled_until: Optional[float] = None
        self._throttle_reason: Optional[str] = None
        self._throttle_message: str = ''

        # Persistence (own connection, own table; never touches CacheManager).
        self.db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None
        self._init_persistence()
        self._load_state()

        logger.info(
            "RateLimiter initialized: min_interval=%.2fs (+%.2fs jitter), "
            "%d requests/min, daily_limit=%s, persistence=%s",
            self.min_interval, self.jitter, self.per_minute_limit,
            self.daily_limit, 'on' if self._conn is not None else 'off',
        )

    # ------------------------------------------------------------------
    # Time helpers (all go through time.time so tests can control the clock)
    # ------------------------------------------------------------------
    @staticmethod
    def _now() -> float:
        return time.time()

    @classmethod
    def _today(cls) -> date:
        return datetime.fromtimestamp(cls._now()).date()

    @classmethod
    def _next_local_midnight(cls) -> float:
        now_dt = datetime.fromtimestamp(cls._now())
        midnight = datetime.combine(now_dt.date() + timedelta(days=1), datetime.min.time())
        return midnight.timestamp()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def _init_persistence(self) -> None:
        if not self.db_path:
            return
        try:
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._conn.execute(
                f"CREATE TABLE IF NOT EXISTS {self.TABLE_NAME} "
                "(key TEXT PRIMARY KEY, value TEXT NOT NULL)"
            )
            self._conn.commit()
        except sqlite3.Error as e:
            logger.warning(
                f"Rate-limit state will not persist (could not open {self.db_path}): {e}"
            )
            self._conn = None

    def _load_state(self) -> None:
        if self._conn is None:
            return
        try:
            rows = self._conn.execute(
                f"SELECT key, value FROM {self.TABLE_NAME}"
            ).fetchall()
        except sqlite3.Error as e:
            logger.warning(f"Could not load rate-limit state: {e}")
            return
        state = {k: v for k, v in rows}
        if not state:
            return
        try:
            if 'last_reset' in state:
                self.last_reset = date.fromisoformat(state['last_reset'])
            self.daily_operations = int(state.get('daily_operations', 0))
            times = json.loads(state.get('request_times', '[]'))
            self.request_times = deque(
                (float(t) for t in times), maxlen=self.per_minute_limit
            )
            last = state.get('last_request_at')
            self.last_request_at = float(last) if last not in (None, '', 'null') else None
            self.backoff_seconds = int(state.get('backoff_seconds', self.MIN_BACKOFF_SECONDS))
            until = state.get('throttled_until')
            if until not in (None, '', 'null'):
                until_f = float(until)
                if until_f > self._now():
                    self._throttled_until = until_f
                    self._throttle_reason = state.get('throttle_reason') or self.REASON_RATE
                    self._throttle_message = state.get('throttle_message') or self._format_message(
                        self._throttle_reason, until_f
                    )
        except (ValueError, TypeError, json.JSONDecodeError) as e:
            logger.warning(f"Ignoring corrupt rate-limit state: {e}")
            return
        self._roll_daily_counter()
        logger.info(
            "Restored rate-limit state: %d requests today, %d in window, backoff=%ds%s",
            self.daily_operations, len(self.request_times), self.backoff_seconds,
            f", throttled until {self._fmt_clock(self._throttled_until)}" if self._throttled_until else '',
        )

    def _save_state(self) -> None:
        if self._conn is None:
            return
        rows = {
            'daily_operations': str(self.daily_operations),
            'last_reset': self.last_reset.isoformat(),
            'request_times': json.dumps(list(self.request_times)),
            'last_request_at': json.dumps(self.last_request_at),
            'backoff_seconds': str(self.backoff_seconds),
            'throttled_until': json.dumps(self._throttled_until),
            'throttle_reason': self._throttle_reason or '',
            'throttle_message': self._throttle_message,
        }
        try:
            self._conn.executemany(
                f"INSERT OR REPLACE INTO {self.TABLE_NAME} (key, value) VALUES (?, ?)",
                list(rows.items()),
            )
            self._conn.commit()
        except sqlite3.Error as e:
            logger.warning(f"Could not persist rate-limit state: {e}")

    def close(self) -> None:
        """Flush state and close the persistence connection (idempotent)."""
        with self._lock:
            if self._conn is None:
                return
            self._save_state()
            try:
                self._conn.close()
            except sqlite3.Error:
                pass
            self._conn = None

    # ------------------------------------------------------------------
    # Throttle state
    # ------------------------------------------------------------------
    @staticmethod
    def _fmt_clock(ts: Optional[float]) -> str:
        if ts is None:
            return ''
        return datetime.fromtimestamp(ts).strftime('%H:%M')

    def _format_message(self, reason: Optional[str], until: Optional[float]) -> str:
        if reason is None or until is None:
            return ''
        clock = self._fmt_clock(until)
        if reason == self.REASON_QUOTA:
            return f"Quota exhausted - throttled until {clock}"
        return f"Rate limited - throttled until {clock}"

    def _set_throttle(self, reason: Optional[str], until: Optional[float], message: str = '') -> None:
        """Update the visible throttle state and notify if it changed."""
        changed = (reason, until) != (self._throttle_reason, self._throttled_until)
        self._throttle_reason = reason
        self._throttled_until = until
        self._throttle_message = message or self._format_message(reason, until)
        if changed:
            self._save_state()
            self._notify()

    def _clear_throttle(self) -> None:
        if self._throttled_until is not None or self._throttle_reason is not None:
            self._set_throttle(None, None, '')

    def _notify(self) -> None:
        if self.on_throttle is None:
            return
        try:
            self.on_throttle(self.get_throttle_state())
        except Exception as e:  # a UI callback must never break the engine
            logger.error(f"Throttle callback raised: {e}")

    def get_throttle_state(self) -> Dict[str, Any]:
        """Return the current throttle state for the UI/CLI.

        Returns:
            dict: ``{'throttled': bool, 'reason': 'rate'|'quota'|None,
            'until': epoch-seconds or None, 'message': str}``. A throttle whose
            ``until`` has passed is reported (and cleared) as not throttled.
        """
        with self._lock:
            if self._throttled_until is not None and self._now() >= self._throttled_until:
                self._clear_throttle()
            throttled = self._throttled_until is not None
            return {
                'throttled': throttled,
                'reason': self._throttle_reason if throttled else None,
                'until': self._throttled_until if throttled else None,
                'message': self._throttle_message if throttled else '',
            }

    # ------------------------------------------------------------------
    # Waiting (bounded, observable, interruptible)
    # ------------------------------------------------------------------
    def _wait(self, seconds: float) -> None:
        """Sleep ``seconds`` in slices of at most ``max_wait_slice``."""
        remaining = float(seconds)
        while remaining > 0:
            if self.interrupt_event is not None and self.interrupt_event.is_set():
                logger.info("Rate-limit wait interrupted")
                return
            step = min(remaining, self.max_wait_slice)
            time.sleep(step)
            remaining -= step

    def _wait_until(self, until: float) -> None:
        """Wait until the clock reaches ``until`` (re-reads the clock each slice)."""
        while True:
            if self.interrupt_event is not None and self.interrupt_event.is_set():
                logger.info("Rate-limit wait interrupted")
                return
            remaining = until - self._now()
            if remaining <= 0:
                return
            time.sleep(min(remaining, self.max_wait_slice))

    # ------------------------------------------------------------------
    # Core checks
    # ------------------------------------------------------------------
    def _roll_daily_counter(self) -> None:
        today = self._today()
        if today > self.last_reset:
            logger.info(
                f"Daily counter reset: {self.daily_operations} operations on {self.last_reset}"
            )
            self.daily_operations = 0
            self.last_reset = today
            if self._throttle_reason == self.REASON_QUOTA and self.daily_limit is not None:
                self._clear_throttle()

    # Backwards-compatible name used by older code/tests.
    _reset_daily_counter = _roll_daily_counter

    def _pacing_wait_seconds(self) -> float:
        """Seconds to wait for the min-interval (+jitter) policy."""
        if self.last_request_at is None or (self.min_interval <= 0 and self.jitter <= 0):
            return 0.0
        target = self.min_interval + (random.uniform(0.0, self.jitter) if self.jitter > 0 else 0.0)
        elapsed = self._now() - self.last_request_at
        return max(0.0, target - elapsed)

    def _window_wait_seconds(self) -> float:
        """Seconds until the rolling 60 s window has room for one more request."""
        now = self._now()
        while self.request_times and now - self.request_times[0] >= 60:
            self.request_times.popleft()
        if len(self.request_times) < self.per_minute_limit:
            return 0.0
        return max(0.0, 60.0 - (now - self.request_times[0]))

    def check_limit(self) -> None:
        """Block as needed so the next request complies with the policy.

        Order: daily ceiling (if configured) -> per-minute window -> pacing.
        Long waits are sliced and the throttle state is visible throughout.
        """
        with self._lock:
            self._roll_daily_counter()

            # 1. Optional daily ceiling: visible 'quota' throttle until midnight.
            if self.daily_limit is not None and self.daily_operations >= self.daily_limit:
                until = self._next_local_midnight()
                logger.warning(
                    f"Daily ceiling reached ({self.daily_operations}/{self.daily_limit}); "
                    f"throttled until {self._fmt_clock(until)}"
                )
                self._set_throttle(self.REASON_QUOTA, until)
                self._wait_until(until)
                self._roll_daily_counter()
                if self.daily_limit is not None and self.daily_operations >= self.daily_limit:
                    # Interrupted before midnight: leave the state visible and return;
                    # the caller is shutting down.
                    return

            # 2. Per-minute ceiling.
            window_wait = self._window_wait_seconds()
            if window_wait > 0:
                until = self._now() + window_wait
                logger.info(
                    f"Per-minute ceiling ({self.per_minute_limit}/min) reached; "
                    f"waiting {window_wait:.1f}s"
                )
                if window_wait >= self.THROTTLE_VISIBILITY_THRESHOLD_SECONDS:
                    self._set_throttle(self.REASON_RATE, until)
                self._wait(window_wait)

            # 3. Steady pacing with jitter.
            pacing_wait = self._pacing_wait_seconds()
            if pacing_wait > 0:
                self._wait(pacing_wait)

            # Any throttle whose deadline has passed is cleared here.
            if self._throttled_until is not None and self._now() >= self._throttled_until:
                self._clear_throttle()

    def record_request(self) -> None:
        """Record that a request was just made (and persist the counters)."""
        with self._lock:
            now = self._now()
            self._roll_daily_counter()
            self.request_times.append(now)
            self.last_request_at = now
            self.daily_operations += 1
            self._save_state()
            logger.debug(
                f"Request recorded: {self.daily_operations} today, "
                f"{len(self.request_times)} in current window"
            )

    def handle_429(self, retry_after: Optional[int] = None, reason: Optional[str] = None) -> None:
        """Back off after an HTTP 429.

        Args:
            retry_after: Seconds from the ``Retry-After`` header, if present.
                Honoured exactly when given.
            reason: ``'quota'`` (or Spotify's literal ``'QUOTA_EXCEEDED'``) marks
                a quota-exhaustion 429, which is surfaced with throttle reason
                ``'quota'``. Anything else is a transient rate limit (``'rate'``).

        Without ``retry_after`` the wait is the current exponential backoff
        (60 s doubling to 300 s). Quota exhaustion will not clear on a short
        retry, so a quota 429 without ``Retry-After`` waits at least the maximum
        backoff. The wait is sliced and visible via :meth:`get_throttle_state`.
        """
        with self._lock:
            is_quota = reason is not None and str(reason).upper() in (
                'QUOTA', 'QUOTA_EXCEEDED'
            )
            throttle_reason = self.REASON_QUOTA if is_quota else self.REASON_RATE

            if retry_after is not None:
                wait_seconds = max(0, int(retry_after))
                logger.warning(
                    f"HTTP 429 ({throttle_reason}) with Retry-After={retry_after}s; "
                    f"waiting {wait_seconds}s"
                )
            else:
                wait_seconds = min(self.backoff_seconds, self.MAX_BACKOFF_SECONDS)
                if is_quota:
                    wait_seconds = self.MAX_BACKOFF_SECONDS
                logger.warning(
                    f"HTTP 429 ({throttle_reason}); exponential backoff {wait_seconds}s "
                    f"(next {min(self.backoff_seconds * 2, self.MAX_BACKOFF_SECONDS)}s)"
                )
            # Escalate for next time regardless of how this wait was sized.
            self.backoff_seconds = min(self.backoff_seconds * 2, self.MAX_BACKOFF_SECONDS)

            until = self._now() + wait_seconds
            self._set_throttle(throttle_reason, until)
            self._wait(wait_seconds)
            if self._now() >= until:
                self._clear_throttle()
            else:
                self._save_state()

    def handle_quota_exceeded(self, retry_after: Optional[int] = None) -> None:
        """Convenience for a Spotify ``QUOTA_EXCEEDED`` 429."""
        self.handle_429(retry_after=retry_after, reason=self.REASON_QUOTA)

    def reset_backoff(self) -> None:
        """Reset exponential backoff after a successful request."""
        with self._lock:
            if self.backoff_seconds != self.MIN_BACKOFF_SECONDS:
                logger.debug(
                    f"Resetting backoff from {self.backoff_seconds}s to {self.MIN_BACKOFF_SECONDS}s"
                )
                self.backoff_seconds = self.MIN_BACKOFF_SECONDS
                self._save_state()

    def reset(self) -> None:
        """Wipe all counters, backoff and throttle state (persisted too)."""
        with self._lock:
            logger.info("Resetting all rate limiting counters")
            self.daily_operations = 0
            self.last_reset = self._today()
            self.request_times.clear()
            self.last_request_at = None
            self.backoff_seconds = self.MIN_BACKOFF_SECONDS
            self._throttled_until = None
            self._throttle_reason = None
            self._throttle_message = ''
            self._save_state()

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------
    def get_remaining_daily_operations(self) -> Optional[int]:
        """Remaining requests under the daily ceiling, or ``None`` if unlimited."""
        with self._lock:
            self._roll_daily_counter()
            if self.daily_limit is None:
                return None
            return max(0, self.daily_limit - self.daily_operations)

    def get_current_stats(self) -> dict:
        """Snapshot of counters, policy and throttle state."""
        with self._lock:
            self._roll_daily_counter()
            throttle = self.get_throttle_state()
            return {
                "daily_operations": self.daily_operations,
                "daily_limit": self.daily_limit,
                "remaining_operations": self.get_remaining_daily_operations(),
                "requests_in_window": len(self.request_times),
                "per_minute_limit": self.per_minute_limit,
                "min_interval": self.min_interval,
                "jitter": self.jitter,
                "backoff_seconds": self.backoff_seconds,
                "last_reset": self.last_reset.isoformat(),
                "last_request_at": self.last_request_at,
                "persistent": self._conn is not None,
                "throttled": throttle['throttled'],
                "throttle_reason": throttle['reason'],
                "throttled_until": throttle['until'],
                "throttle_message": throttle['message'],
            }

    def __repr__(self) -> str:
        daily = (
            f"{self.daily_operations}/{self.daily_limit}"
            if self.daily_limit is not None else f"{self.daily_operations}/-"
        )
        return (
            f"RateLimiter(daily={daily}, "
            f"window={len(self.request_times)}/{self.per_minute_limit}, "
            f"interval={self.min_interval}s+{self.jitter}s, "
            f"backoff={self.backoff_seconds}s)"
        )
