"""OS sleep inhibition for long-running migrations.

A 50k-track migration runs for a day or more. If the user walks away and the
machine goes to sleep, the job stalls (and the YouTube Music session may
expire while it waits). This module asks the OS not to sleep while a job is
active, using the native mechanism on each desktop platform:

- Windows: ``SetThreadExecutionState`` via ``ctypes`` (no subprocess).
- macOS:   ``caffeinate -i -w <pid>`` subprocess (dies with us automatically).
- Linux:   ``systemd-inhibit --what=sleep:idle ... sleep infinity`` subprocess.

Everything is best-effort. On an unknown platform, when the native tool is
missing, or when the OS call fails, the inhibitor degrades to a logged no-op
and never raises -- a missing ``caffeinate`` must never take the migration down
with it.

Public API::

    handle = inhibit_sleep("Migrating playlists")
    ...
    release_sleep(handle)

    with keep_awake("Migrating playlists"):
        ...

Note for Windows: ``SetThreadExecutionState`` with ``ES_CONTINUOUS`` is bound
to the *calling thread*. Acquire and release from the same long-lived thread
(the ``main.py`` sleep guard does this).

Local-only: nothing here talks to the network or touches credentials.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from contextlib import contextmanager
from typing import Iterator, Optional

logger = logging.getLogger(__name__)

# Windows execution-state flags (winbase.h)
ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
ES_AWAYMODE_REQUIRED = 0x00000040

BACKEND_NOOP = "noop"
BACKEND_WINDOWS = "windows"
BACKEND_MACOS = "macos"
BACKEND_LINUX = "linux"


class SleepInhibitor:
    """Handle returned by :func:`inhibit_sleep`.

    Attributes:
        reason: Human-readable reason passed to the OS where supported.
        backend: One of the ``BACKEND_*`` constants describing what was used.
        active: ``True`` while the OS inhibition is believed to be in force.
                ``False`` for a no-op handle or after :meth:`release`.
    """

    def __init__(self, reason: str, backend: str = BACKEND_NOOP,
                 process: Optional[subprocess.Popen] = None,
                 active: bool = False) -> None:
        self.reason = reason
        self.backend = backend
        self._process = process
        self.active = active

    def release(self) -> None:
        """Release the inhibition. Idempotent and never raises."""
        if not self.active:
            return
        try:
            if self.backend == BACKEND_WINDOWS:
                _windows_release()
            elif self._process is not None:
                _terminate(self._process)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Failed to release sleep inhibition (%s): %s", self.backend, exc)
        finally:
            self.active = False
            self._process = None
            logger.info("Sleep inhibition released (%s)", self.backend)

    def __enter__(self) -> "SleepInhibitor":
        return self

    def __exit__(self, *exc_info) -> None:
        self.release()

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"SleepInhibitor(backend={self.backend!r}, active={self.active})"


def inhibit_sleep(reason: str = "Playlist migration in progress") -> SleepInhibitor:
    """Ask the OS not to sleep. Always returns a handle; never raises.

    Args:
        reason: Why the machine should stay awake (shown by some OSes).

    Returns:
        SleepInhibitor: ``active`` is ``True`` if the OS accepted the request,
        ``False`` if this platform is unsupported or the attempt failed.
    """
    platform = sys.platform
    try:
        if platform.startswith("win"):
            return _inhibit_windows(reason)
        if platform == "darwin":
            return _inhibit_macos(reason)
        if platform.startswith("linux"):
            return _inhibit_linux(reason)
        logger.info("Sleep inhibition not supported on platform %r; continuing without it", platform)
    except Exception as exc:
        logger.warning("Sleep inhibition unavailable on %s (%s); continuing without it", platform, exc)
    return SleepInhibitor(reason, BACKEND_NOOP)


def release_sleep(handle: Optional[SleepInhibitor]) -> None:
    """Release a handle from :func:`inhibit_sleep`. Accepts ``None``; never raises."""
    if handle is None:
        return
    try:
        handle.release()
    except Exception as exc:  # pragma: no cover - release() already guards
        logger.warning("release_sleep failed: %s", exc)


@contextmanager
def keep_awake(reason: str = "Playlist migration in progress") -> Iterator[SleepInhibitor]:
    """Context manager: inhibit sleep for the duration of the block."""
    handle = inhibit_sleep(reason)
    try:
        yield handle
    finally:
        release_sleep(handle)


# ---------------------------------------------------------------------------
# Per-OS backends
# ---------------------------------------------------------------------------

def _inhibit_windows(reason: str) -> SleepInhibitor:
    import ctypes  # local import: only meaningful on Windows

    kernel32 = getattr(getattr(ctypes, "windll", None), "kernel32", None)
    if kernel32 is None:
        raise RuntimeError("ctypes.windll.kernel32 unavailable")
    previous = kernel32.SetThreadExecutionState(
        ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_AWAYMODE_REQUIRED
    )
    if not previous:
        raise RuntimeError("SetThreadExecutionState returned NULL")
    logger.info("Sleep inhibition active via SetThreadExecutionState: %s", reason)
    return SleepInhibitor(reason, BACKEND_WINDOWS, active=True)


def _windows_release() -> None:
    import ctypes

    kernel32 = getattr(getattr(ctypes, "windll", None), "kernel32", None)
    if kernel32 is not None:
        kernel32.SetThreadExecutionState(ES_CONTINUOUS)


def _inhibit_macos(reason: str) -> SleepInhibitor:
    exe = shutil.which("caffeinate")
    if not exe:
        raise FileNotFoundError("caffeinate not found")
    # -i: prevent idle sleep; -w <pid>: exit when this process exits, so a
    # crash can never leave the Mac permanently awake.
    proc = _spawn([exe, "-i", "-w", str(os.getpid())])
    logger.info("Sleep inhibition active via caffeinate (pid %s): %s", proc.pid, reason)
    return SleepInhibitor(reason, BACKEND_MACOS, process=proc, active=True)


def _inhibit_linux(reason: str) -> SleepInhibitor:
    exe = shutil.which("systemd-inhibit")
    if not exe:
        raise FileNotFoundError("systemd-inhibit not found")
    proc = _spawn([
        exe,
        "--what=sleep:idle",
        "--who=Playlist Migrator",
        f"--why={reason}",
        "--mode=block",
        "sleep", "infinity",
    ])
    logger.info("Sleep inhibition active via systemd-inhibit (pid %s): %s", proc.pid, reason)
    return SleepInhibitor(reason, BACKEND_LINUX, process=proc, active=True)


def _spawn(argv: list) -> subprocess.Popen:
    return subprocess.Popen(
        argv,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _terminate(proc: subprocess.Popen, timeout: float = 3.0) -> None:
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=timeout)
    except Exception:
        try:
            proc.kill()
        except Exception:  # pragma: no cover - defensive
            pass
