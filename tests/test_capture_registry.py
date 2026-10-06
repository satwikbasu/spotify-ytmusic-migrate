"""Native-host registration: pure manifest/location data + injected-home writes."""

import json
import os

import pytest

from src.capture import constants as C
from src.capture import registry as R

HOME = "/home/u"


def test_dev_chromium_id_derives_from_public_key():
    import base64
    import hashlib
    der = base64.b64decode(C.DEV_CHROMIUM_EXTENSION_KEY)
    derived = "".join(chr(ord("a") + int(c, 16)) for c in hashlib.sha256(der).hexdigest()[:32])
    assert derived == C.DEV_CHROMIUM_EXTENSION_ID


def test_chromium_manifest():
    m = R.manifest_for("chromium", "/x/capture-host.sh")
    assert m["name"] == "com.playlist_migrator.capture" and m["type"] == "stdio"
    assert m["path"] == "/x/capture-host.sh"
    assert m["allowed_origins"] == [f"chrome-extension://{i}/" for i in C.CHROMIUM_ALLOWED_EXTENSION_IDS]
    assert C.DEV_CHROMIUM_EXTENSION_ID in m["allowed_origins"][2]
    assert "allowed_extensions" not in m


def test_firefox_manifest():
    m = R.manifest_for("firefox", "/x/h")
    assert m["allowed_extensions"] == ["capture@playlist-migrator.app"]
    assert "allowed_origins" not in m
    with pytest.raises(ValueError):
        R.manifest_for("safari", "/x")


NAME = "com.playlist_migrator.capture.json"
LINUX = {
    "chrome": [f"{HOME}/.config/{d}/NativeMessagingHosts/{NAME}"
               for d in ("google-chrome", "google-chrome-beta", "google-chrome-unstable")],
    "chromium": [f"{HOME}/.config/chromium/NativeMessagingHosts/{NAME}"],
    "edge": [f"{HOME}/.config/microsoft-edge/NativeMessagingHosts/{NAME}"],
    "brave": [f"{HOME}/.config/BraveSoftware/Brave-Browser/NativeMessagingHosts/{NAME}"],
    "vivaldi": [f"{HOME}/.config/vivaldi/NativeMessagingHosts/{NAME}"],
    "firefox": [f"{HOME}/.mozilla/native-messaging-hosts/{NAME}"],
}
MAC = {
    "chrome": "Library/Application Support/Google/Chrome/NativeMessagingHosts",
    "chromium": "Library/Application Support/Chromium/NativeMessagingHosts",
    "edge": "Library/Application Support/Microsoft Edge/NativeMessagingHosts",
    "brave": "Library/Application Support/BraveSoftware/Brave-Browser/NativeMessagingHosts",
    "vivaldi": "Library/Application Support/Vivaldi/NativeMessagingHosts",
    "firefox": "Library/Application Support/Mozilla/NativeMessagingHosts",
}
WIN = {
    "chrome": r"Software\Google\Chrome\NativeMessagingHosts",
    "chromium": r"Software\Chromium\NativeMessagingHosts",
    "edge": r"Software\Microsoft\Edge\NativeMessagingHosts",
    "brave": r"Software\BraveSoftware\Brave-Browser\NativeMessagingHosts",
    "vivaldi": r"Software\Vivaldi\NativeMessagingHosts",
    "firefox": r"Software\Mozilla\NativeMessagingHosts",
}


@pytest.mark.parametrize("browser", list(R.BROWSERS))
def test_locations_per_browser_and_os(browser):
    assert [l.target for l in R.locations_for("linux", browser, HOME)] == [p for p in LINUX[browser]]
    mac = R.locations_for("macos", browser, HOME)
    assert [l.target for l in mac] == [os.path.join(HOME, *MAC[browser].split("/"), NAME)]
    win = R.locations_for("windows", browser, HOME)
    assert [(l.kind, l.target) for l in win] == [("registry", WIN[browser] + "\\com.playlist_migrator.capture")]
    assert all(l.kind == "file" for l in mac)


def test_launcher_content():
    sh = R.launcher_content("linux", ["/usr/bin/python3", "/my app/main.py"])
    assert sh.startswith("#!/bin/sh\n") and "--native-host" in sh and "'/my app/main.py'" in sh
    bat = R.launcher_content("windows", [r"C:\Program Files\PM\PlaylistMigrator.exe"])
    assert bat == '@echo off\r\n"C:\\Program Files\\PM\\PlaylistMigrator.exe" --native-host %*\r\n'


def _fs(existing):
    return lambda p: p in existing


def test_detect_linux_normal_snap_flatpak():
    which = {"google-chrome": "/usr/bin/google-chrome", "firefox": "/snap/bin/firefox"}.get
    existing = {f"{HOME}/snap/firefox", f"{HOME}/.var/app/com.brave.Browser"}
    found = {d.browser: d for d in R.detect_browsers("linux", HOME, which, _fs(existing))}
    assert found["chrome"].via == "binary" and found["chrome"].supported
    assert found["firefox"].via == "snap" and not found["firefox"].supported
    assert "not yet supported (v1)" in found["firefox"].note
    assert found["brave"].via == "flatpak" and not found["brave"].supported
    assert "edge" not in found and "chromium" not in found


def test_detect_windows_always_set():
    found = {d.browser for d in R.detect_browsers("windows", r"C:\Users\u", lambda n: None, lambda p: False)}
    assert found == {"chrome", "edge", "firefox"}


def test_detect_mac_apps_and_profile():
    existing = {"/Applications/Firefox.app", f"{HOME}/Library/Application Support/Microsoft Edge"}
    found = {d.browser: d.via for d in R.detect_browsers("macos", HOME, lambda n: None, _fs(existing))}
    assert found == {"firefox": "binary", "edge": "profile"}


def _linux_register(home, which, existing=None):
    return R.register_all(home=str(home), os_="linux", command=["/py", "/app/main.py"],
                          which=which, exists=existing or os.path.exists)


def test_register_all_writes_and_is_idempotent(tmp_path):
    home = tmp_path
    (home / ".config" / "google-chrome").mkdir(parents=True)
    which = {"firefox": "/usr/bin/firefox"}.get
    first = _linux_register(home, which)
    by = {r.browser: r for r in first}
    assert by["chrome"].changed and by["firefox"].changed
    chrome_copy = home / ".config/google-chrome/NativeMessagingHosts" / NAME
    ff_copy = home / ".mozilla/native-messaging-hosts" / NAME
    launcher = home / ".playlist_migrator/native_hosts/capture-host.sh"
    assert json.loads(chrome_copy.read_text())["allowed_origins"]
    assert json.loads(ff_copy.read_text())["allowed_extensions"]
    assert json.loads(chrome_copy.read_text())["path"] == str(launcher)
    assert os.access(launcher, os.X_OK) and not chrome_copy.is_symlink()
    # beta/unstable dirs are only written when registering (copies for chrome family)
    second = _linux_register(home, which)
    assert not any(r.changed for r in second)
    # a changed command rewrites the launcher
    changed = R.register_all(home=str(home), os_="linux", command=["/other"], which=which, exists=os.path.exists)
    assert "/other" in launcher.read_text()


def test_register_all_no_browser_installed_is_safe(tmp_path):
    assert _linux_register(tmp_path, lambda n: None) == []
    assert not (tmp_path / ".playlist_migrator").exists()


def test_register_all_skips_snap(tmp_path):
    res = _linux_register(tmp_path, {"firefox": "/snap/bin/firefox"}.get)
    assert [(r.browser, r.supported) for r in res] == [("firefox", False)]
    assert not (tmp_path / ".mozilla").exists()


class FakeWinReg:
    def __init__(self):
        self.keys = {}

    def get(self, k):
        return self.keys.get(k)

    def set(self, k, v):
        self.keys[k] = v

    def delete(self, k):
        self.keys.pop(k, None)


def test_register_windows_uses_registry_pointer(tmp_path):
    reg = FakeWinReg()
    res = R.register_all(home=str(tmp_path), os_="windows", command=[r"C:\PM\PM.exe"],
                         winreg=reg, which=lambda n: None, exists=lambda p: False)
    assert {r.browser for r in res} == {"chrome", "edge", "firefox"}
    key = WIN["chrome"] + "\\com.playlist_migrator.capture"
    manifest_path = reg.keys[key]
    assert manifest_path.endswith(NAME) and os.path.exists(manifest_path)
    assert json.load(open(manifest_path))["path"].endswith("capture-host.bat")
    assert len(reg.keys) == 3
    assert not any(r.changed for r in R.register_all(home=str(tmp_path), os_="windows",
                   command=[r"C:\PM\PM.exe"], winreg=reg, which=lambda n: None, exists=lambda p: False))
    R.unregister_all(home=str(tmp_path), os_="windows", winreg=reg)
    assert reg.keys == {}


def test_unregister_all_removes_copies(tmp_path):
    (tmp_path / ".config" / "chromium").mkdir(parents=True)
    _linux_register(tmp_path, lambda n: None)
    copy = tmp_path / ".config/chromium/NativeMessagingHosts" / NAME
    assert copy.exists()
    R.unregister_all(home=str(tmp_path), os_="linux")
    assert not copy.exists() and not (tmp_path / ".playlist_migrator/native_hosts").exists()
