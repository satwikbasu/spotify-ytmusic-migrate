"""MigrationManager seam: auth_required handler + accept_captured_client."""

import threading
import time
from unittest.mock import MagicMock

import pytest
from cryptography.fernet import Fernet

from src.capture.hub import CaptureHub, CaptureResult
from src.capture.session_store import SessionStore


def _fresh_manager(tmp_path):
    from src.migrators.migration_manager import MigrationManager
    from src.utils.cache_manager import CacheManager
    cm = CacheManager(db_path=str(tmp_path / "c.db"))
    m = MigrationManager(MagicMock(), MagicMock(), cm)
    return m, cm


def _wait(pred, t=3):
    end = time.time() + t
    while not pred() and time.time() < end:
        time.sleep(0.01)
    return pred()


def test_handler_handled_suppresses_notification(tmp_path):
    m, cm = _fresh_manager(tmp_path)
    orig = MagicMock()
    m.notifier.notify_auth_required = orig
    m._install_auth_notification_gate()
    seen = []
    m.set_auth_required_handler(lambda name: seen.append(name) or True)
    m.notifier.notify_auth_required(playlist_name="Mix")
    assert _wait(lambda: seen == ["Mix"])
    time.sleep(0.1)
    orig.assert_not_called()
    cm.close()


def test_handler_false_or_raising_falls_back_to_notification(tmp_path):
    for handler in (lambda n: False, MagicMock(side_effect=RuntimeError("x"))):
        m, cm = _fresh_manager(tmp_path)
        orig = MagicMock()
        m.notifier.notify_auth_required = orig
        m._install_auth_notification_gate()
        m.set_auth_required_handler(handler)
        m.notifier.notify_auth_required(playlist_name="Mix")
        assert _wait(lambda: orig.called)
        cm.close()


def test_no_handler_notifies_directly(tmp_path):
    m, cm = _fresh_manager(tmp_path)
    orig = MagicMock()
    m.notifier.notify_auth_required = orig
    m._install_auth_notification_gate()
    m.notifier.notify_auth_required(playlist_name="Mix")
    orig.assert_called_once()
    cm.close()


def test_accept_captured_client_resumes_only_when_parked(tmp_path):
    m, cm = _fresh_manager(tmp_path)
    new = MagicMock()
    m.reauthenticate_youtube = MagicMock(return_value=["j1"])
    m.background_worker.is_auth_required = MagicMock(return_value=False)
    assert m.accept_captured_client(new) == []
    m.reauthenticate_youtube.assert_not_called()
    assert m.ytmusic_client is new
    m.background_worker.is_auth_required.return_value = True
    assert m.accept_captured_client(new) == ["j1"]
    m.reauthenticate_youtube.assert_called_once_with(new)
    with pytest.raises(ValueError):
        m.accept_captured_client(None)
    cm.close()


def test_hub_reauth_flow_swaps_client_via_manager(tmp_path):
    m, cm = _fresh_manager(tmp_path)
    hub = CaptureHub(run_dir=str(tmp_path / "r"), store=SessionStore(path=str(tmp_path / "s.enc"), key=Fernet.generate_key()))
    hub.attach_engine(m)
    assert m._auth_required_handler is not None
    assert hub._rate_limiter is m.rate_limiter
    # no live port: not handled -> caller will notify
    assert hub._on_auth_required("Mix") is False
    # live port answers: handled, and the manager got the verified client
    client = MagicMock()
    client.get_account_info.return_value = {"accountName": "Ann"}
    hub.client_factory = lambda h: client
    m.reauthenticate_youtube = MagicMock(return_value=[])
    m.background_worker.is_auth_required = MagicMock(return_value=True)
    hub.request_capture = lambda purpose, timeout_s=None: hub.process_cookies(
        [{"name": "__Secure-3PAPISID", "value": "a"}], browser="chrome")
    assert hub._on_auth_required("Mix") is True
    m.reauthenticate_youtube.assert_called_once_with(client)
    cm.close()
