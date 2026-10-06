"""Tests for src/utils/power.py (OS sleep inhibition).

Nothing here touches the real OS: ctypes, subprocess and shutil.which are all
monkeypatched so no inhibitor is ever actually started.
"""

import subprocess
import sys
import types
from unittest.mock import Mock

import pytest

from src.utils import power


@pytest.fixture
def fake_popen(monkeypatch):
    """Replace subprocess.Popen with a recorder returning a fake process."""
    calls = []

    class FakeProc:
        def __init__(self, argv):
            self.argv = argv
            self.pid = 4242
            self.terminated = False
            self.killed = False
            self._returncode = None

        def poll(self):
            return self._returncode

        def terminate(self):
            self.terminated = True
            self._returncode = 0

        def wait(self, timeout=None):
            return self._returncode

        def kill(self):
            self.killed = True

    def popen(argv, **kwargs):
        proc = FakeProc(argv)
        calls.append(proc)
        return proc

    monkeypatch.setattr(power.subprocess, "Popen", popen)
    return calls


class TestUnknownPlatform:
    def test_inhibit_is_noop_and_does_not_raise(self, monkeypatch):
        monkeypatch.setattr(power.sys, "platform", "plan9")
        handle = power.inhibit_sleep("test")
        assert isinstance(handle, power.SleepInhibitor)
        assert handle.active is False
        assert handle.backend == power.BACKEND_NOOP
        # releasing a no-op handle is fine
        power.release_sleep(handle)
        assert handle.active is False

    def test_keep_awake_context_manager_noop(self, monkeypatch):
        monkeypatch.setattr(power.sys, "platform", "plan9")
        with power.keep_awake("test") as handle:
            assert handle.active is False
        assert handle.active is False

    def test_release_none_is_safe(self):
        power.release_sleep(None)


class TestWindows:
    def _install_fake_kernel32(self, monkeypatch, return_value=1):
        kernel32 = Mock()
        kernel32.SetThreadExecutionState = Mock(return_value=return_value)
        fake_windll = types.SimpleNamespace(kernel32=kernel32)
        import ctypes
        monkeypatch.setattr(ctypes, "windll", fake_windll, raising=False)
        monkeypatch.setattr(power.sys, "platform", "win32")
        return kernel32

    def test_inhibit_calls_set_thread_execution_state(self, monkeypatch):
        kernel32 = self._install_fake_kernel32(monkeypatch)
        handle = power.inhibit_sleep("win test")
        assert handle.active is True
        assert handle.backend == power.BACKEND_WINDOWS
        flags = kernel32.SetThreadExecutionState.call_args[0][0]
        assert flags & power.ES_CONTINUOUS
        assert flags & power.ES_SYSTEM_REQUIRED

        handle.release()
        assert handle.active is False
        # Release resets to ES_CONTINUOUS only
        assert kernel32.SetThreadExecutionState.call_args[0][0] == power.ES_CONTINUOUS

    def test_release_is_idempotent(self, monkeypatch):
        kernel32 = self._install_fake_kernel32(monkeypatch)
        handle = power.inhibit_sleep("win test")
        handle.release()
        handle.release()
        assert kernel32.SetThreadExecutionState.call_count == 2

    def test_api_failure_degrades_to_noop(self, monkeypatch):
        self._install_fake_kernel32(monkeypatch, return_value=0)
        handle = power.inhibit_sleep("win test")
        assert handle.active is False
        assert handle.backend == power.BACKEND_NOOP


class TestMacOS:
    def test_uses_caffeinate_bound_to_our_pid(self, monkeypatch, fake_popen):
        monkeypatch.setattr(power.sys, "platform", "darwin")
        monkeypatch.setattr(power.shutil, "which", lambda name: "/usr/bin/caffeinate")
        handle = power.inhibit_sleep("mac test")
        assert handle.active is True
        assert handle.backend == power.BACKEND_MACOS
        argv = fake_popen[0].argv
        assert argv[0] == "/usr/bin/caffeinate"
        assert "-i" in argv
        assert "-w" in argv and str(power.os.getpid()) in argv

        handle.release()
        assert fake_popen[0].terminated is True
        assert handle.active is False

    def test_missing_caffeinate_is_noop(self, monkeypatch, fake_popen):
        monkeypatch.setattr(power.sys, "platform", "darwin")
        monkeypatch.setattr(power.shutil, "which", lambda name: None)
        handle = power.inhibit_sleep("mac test")
        assert handle.active is False
        assert fake_popen == []


class TestLinux:
    def test_uses_systemd_inhibit(self, monkeypatch, fake_popen):
        monkeypatch.setattr(power.sys, "platform", "linux")
        monkeypatch.setattr(power.shutil, "which", lambda name: "/usr/bin/systemd-inhibit")
        with power.keep_awake("linux test") as handle:
            assert handle.active is True
            assert handle.backend == power.BACKEND_LINUX
            argv = fake_popen[0].argv
            assert argv[0] == "/usr/bin/systemd-inhibit"
            assert "--what=sleep:idle" in argv
            assert "--why=linux test" in argv
        assert fake_popen[0].terminated is True
        assert handle.active is False

    def test_missing_systemd_inhibit_is_noop(self, monkeypatch, fake_popen):
        monkeypatch.setattr(power.sys, "platform", "linux")
        monkeypatch.setattr(power.shutil, "which", lambda name: None)
        handle = power.inhibit_sleep("linux test")
        assert handle.active is False
        assert fake_popen == []

    def test_spawn_failure_never_raises(self, monkeypatch):
        monkeypatch.setattr(power.sys, "platform", "linux")
        monkeypatch.setattr(power.shutil, "which", lambda name: "/usr/bin/systemd-inhibit")

        def boom(*a, **k):
            raise OSError("cannot spawn")

        monkeypatch.setattr(power.subprocess, "Popen", boom)
        handle = power.inhibit_sleep("linux test")
        assert handle.active is False
        assert handle.backend == power.BACKEND_NOOP

    def test_release_kills_if_terminate_hangs(self, monkeypatch, fake_popen):
        monkeypatch.setattr(power.sys, "platform", "linux")
        monkeypatch.setattr(power.shutil, "which", lambda name: "/usr/bin/systemd-inhibit")
        handle = power.inhibit_sleep("linux test")
        proc = fake_popen[0]

        def hang(timeout=None):
            raise subprocess.TimeoutExpired("x", timeout)

        proc.wait = hang
        handle.release()
        assert proc.killed is True
        assert handle.active is False
