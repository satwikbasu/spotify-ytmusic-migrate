"""Native-messaging host manifest registration (user-level, no admin).

Pure functions compute manifests and install locations per browser x OS and
are unit-tested as data. ``register_all`` / ``unregister_all`` perform the
writes against an injectable ``home`` / registry shim. Snap and Flatpak
browsers are detected and reported as unsupported in v1 (never registered).
"""

import json
import logging
import os
import shutil
import stat
import sys
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence

from . import paths
from .constants import (CHROMIUM_ALLOWED_EXTENSION_IDS, FIREFOX_ALLOWED_EXTENSIONS,
                        HOST_DESCRIPTION, HOST_NAME)

logger = logging.getLogger(__name__)

MANIFEST_FILE = f"{HOST_NAME}.json"

# key -> (family, display name)
BROWSERS: Dict[str, tuple] = {
    "chrome": ("chromium", "Google Chrome"),
    "chromium": ("chromium", "Chromium"),
    "edge": ("chromium", "Microsoft Edge"),
    "brave": ("chromium", "Brave"),
    "vivaldi": ("chromium", "Vivaldi"),
    "firefox": ("firefox", "Mozilla Firefox"),
}

# Per-OS target data. posix: dirs relative to home. windows: HKCU subkeys.
_LINUX_DIRS = {
    "chrome": [".config/google-chrome", ".config/google-chrome-beta", ".config/google-chrome-unstable"],
    "chromium": [".config/chromium"],
    "edge": [".config/microsoft-edge"],
    "brave": [".config/BraveSoftware/Brave-Browser"],
    "vivaldi": [".config/vivaldi"],
}
_MAC_DIRS = {
    "chrome": ["Library/Application Support/Google/Chrome"],
    "chromium": ["Library/Application Support/Chromium"],
    "edge": ["Library/Application Support/Microsoft Edge"],
    "brave": ["Library/Application Support/BraveSoftware/Brave-Browser"],
    "vivaldi": ["Library/Application Support/Vivaldi"],
}
_WIN_KEYS = {
    "chrome": r"Software\Google\Chrome\NativeMessagingHosts",
    "chromium": r"Software\Chromium\NativeMessagingHosts",
    "edge": r"Software\Microsoft\Edge\NativeMessagingHosts",
    "brave": r"Software\BraveSoftware\Brave-Browser\NativeMessagingHosts",
    "vivaldi": r"Software\Vivaldi\NativeMessagingHosts",
    "firefox": r"Software\Mozilla\NativeMessagingHosts",
}
# Windows: always write these (an unused HKCU key is harmless).
WINDOWS_ALWAYS = ("chrome", "edge", "firefox")

_BINARIES = {
    "chrome": ["google-chrome", "google-chrome-stable"],
    "chromium": ["chromium", "chromium-browser"],
    "edge": ["microsoft-edge", "microsoft-edge-stable"],
    "brave": ["brave-browser", "brave"],
    "vivaldi": ["vivaldi", "vivaldi-stable"],
    "firefox": ["firefox"],
}
_MAC_APPS = {
    "chrome": "Google Chrome.app", "chromium": "Chromium.app", "edge": "Microsoft Edge.app",
    "brave": "Brave Browser.app", "vivaldi": "Vivaldi.app", "firefox": "Firefox.app",
}
_FLATPAK_IDS = {
    "chrome": "com.google.Chrome", "chromium": "org.chromium.Chromium",
    "edge": "com.microsoft.Edge", "brave": "com.brave.Browser",
    "vivaldi": "com.vivaldi.Vivaldi", "firefox": "org.mozilla.firefox",
}
_SNAP_NAMES = {"chromium": "chromium", "firefox": "firefox", "brave": "brave"}

UNSUPPORTED_NOTE = "not yet supported (v1)"


def os_name() -> str:
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    return "linux"


# --- pure computation -------------------------------------------------------

def manifest_for(family: str, launcher_path: str,
                 chromium_ids: Sequence[str] = CHROMIUM_ALLOWED_EXTENSION_IDS,
                 firefox_ids: Sequence[str] = FIREFOX_ALLOWED_EXTENSIONS) -> dict:
    manifest = {
        "name": HOST_NAME,
        "description": HOST_DESCRIPTION,
        "path": launcher_path,
        "type": "stdio",
    }
    if family == "firefox":
        manifest["allowed_extensions"] = list(firefox_ids)
    elif family == "chromium":
        manifest["allowed_origins"] = [f"chrome-extension://{i}/" for i in chromium_ids]
    else:
        raise ValueError(f"unknown browser family {family!r}")
    return manifest


@dataclass(frozen=True)
class Location:
    kind: str  # "file" | "registry"
    target: str  # file path of the manifest copy, or HKCU subkey (full key path)


def locations_for(os_: str, browser: str, home: str) -> List[Location]:
    """Where a browser looks for the manifest (copy on posix, HKCU key on Windows)."""
    if browser not in BROWSERS:
        raise ValueError(f"unknown browser {browser!r}")
    if os_ == "windows":
        return [Location("registry", _WIN_KEYS[browser] + "\\" + HOST_NAME)]
    if browser == "firefox":
        base = (os.path.join(home, "Library", "Application Support", "Mozilla", "NativeMessagingHosts")
                if os_ == "macos" else os.path.join(home, ".mozilla", "native-messaging-hosts"))
        return [Location("file", os.path.join(base, MANIFEST_FILE))]
    table = _MAC_DIRS if os_ == "macos" else _LINUX_DIRS
    return [Location("file", os.path.join(home, *d.split("/"), "NativeMessagingHosts", MANIFEST_FILE))
            for d in table[browser]]


def manifest_store_path(browser: str, home: str) -> str:
    return os.path.join(paths.native_hosts_dir(home), browser, MANIFEST_FILE)


def launcher_path(os_: str, home: str) -> str:
    name = "capture-host.bat" if os_ == "windows" else "capture-host.sh"
    return os.path.join(paths.native_hosts_dir(home), name)


def launcher_content(os_: str, command: Sequence[str]) -> str:
    if os_ == "windows":
        cmd = " ".join(f'"{c}"' for c in command)
        return f"@echo off\r\n{cmd} --native-host %*\r\n"
    cmd = " ".join("'" + c.replace("'", "'\\''") + "'" for c in command)
    return f"#!/bin/sh\nexec {cmd} --native-host \"$@\"\n"


def host_command() -> List[str]:
    """Command that starts this app: packaged binary, or dev python + main.py."""
    if getattr(sys, "frozen", False):
        return [sys.executable]
    main_py = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "main.py"))
    return [sys.executable, main_py]


# --- detection --------------------------------------------------------------

@dataclass
class DetectedBrowser:
    browser: str
    display: str
    family: str
    via: str  # binary | profile | snap | flatpak | default
    supported: bool = True
    note: str = ""


def detect_browsers(os_: str, home: str, which: Callable = shutil.which,
                    exists: Callable = os.path.exists) -> List[DetectedBrowser]:
    found: List[DetectedBrowser] = []
    for key, (family, display) in BROWSERS.items():
        via = None
        if os_ == "linux":
            bin_path = next((p for n in _BINARIES[key] if (p := which(n))), None)
            snap = (bin_path and bin_path.startswith("/snap/")) or (
                key in _SNAP_NAMES and exists(os.path.join(home, "snap", _SNAP_NAMES[key])))
            flatpak = exists(os.path.join(home, ".var", "app", _FLATPAK_IDS[key]))
            native_profile = any(exists(os.path.join(home, *d.split("/"))) for d in _LINUX_DIRS.get(key, [])) \
                or (key == "firefox" and exists(os.path.join(home, ".mozilla")))
            if bin_path and not bin_path.startswith("/snap/"):
                via = "binary"
            elif native_profile:
                via = "profile"
            elif snap:
                via = "snap"
            elif flatpak:
                via = "flatpak"
        elif os_ == "macos":
            if any(exists(os.path.join(root, _MAC_APPS[key])) for root in ("/Applications", os.path.join(home, "Applications"))):
                via = "binary"
            elif any(exists(os.path.dirname(os.path.dirname(l.target))) for l in locations_for(os_, key, home)
                     if key != "firefox"):
                via = "profile"
            elif key == "firefox" and exists(os.path.join(home, "Library", "Application Support", "Firefox")):
                via = "profile"
        else:  # windows: write the always-set; others only if their binary is on PATH
            if key in WINDOWS_ALWAYS:
                via = "default"
            elif any(which(n) for n in _BINARIES[key]):
                via = "binary"
        if via is None:
            continue
        unsupported = via in ("snap", "flatpak")
        found.append(DetectedBrowser(key, display, family, via, not unsupported,
                                     UNSUPPORTED_NOTE if unsupported else ""))
    return found


# --- writes -----------------------------------------------------------------

class WinRegistry:
    """Thin real-winreg shim (HKCU); tests inject a fake with the same methods."""

    def get(self, key: str) -> Optional[str]:
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as k:
                return winreg.QueryValue(k, None)
        except OSError:
            return None

    def set(self, key: str, value: str) -> None:
        import winreg
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key) as k:
            winreg.SetValue(k, None, winreg.REG_SZ, value)

    def delete(self, key: str) -> None:
        import winreg
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key)
        except OSError:
            pass


@dataclass
class RegisteredBrowser:
    browser: str
    display: str
    family: str
    via: str
    supported: bool
    changed: bool = False
    locations: List[str] = field(default_factory=list)
    note: str = ""


def _write_if_changed(path: str, content: str, mode: Optional[int] = None) -> bool:
    try:
        with open(path, "r", encoding="utf-8", newline="") as fh:
            if fh.read() == content:
                return False
    except OSError:
        pass
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(content)
    if mode is not None:
        os.chmod(path, mode)
    return True


def register_all(home: Optional[str] = None, os_: Optional[str] = None,
                 command: Optional[Sequence[str]] = None, winreg=None,
                 which: Callable = shutil.which, exists: Callable = os.path.exists
                 ) -> List[RegisteredBrowser]:
    """Idempotently register the host for every detected, supported browser.

    Safe when no browser is installed (returns []); never raises for a single
    browser failing. Call on every app launch (browser may be installed later).
    """
    home = home or os.path.expanduser("~")
    os_ = os_ or os_name()
    command = list(command or host_command())
    results: List[RegisteredBrowser] = []
    detected = detect_browsers(os_, home, which, exists)
    supported = [d for d in detected if d.supported]
    if supported:
        try:
            lp = launcher_path(os_, home)
            _write_if_changed(lp, launcher_content(os_, command),
                              None if os_ == "windows" else 0o755)
        except OSError:
            logger.exception("could not write native host launcher")
            return [RegisteredBrowser(d.browser, d.display, d.family, d.via, False,
                                      note="launcher write failed") for d in detected]
    lp = launcher_path(os_, home)
    if os_ == "windows" and winreg is None and supported:
        winreg = WinRegistry()
    for d in detected:
        rb = RegisteredBrowser(d.browser, d.display, d.family, d.via, d.supported, note=d.note)
        results.append(rb)
        if not d.supported:
            continue
        try:
            text = json.dumps(manifest_for(d.family, lp), indent=2) + "\n"
            store = manifest_store_path(d.browser, home)
            rb.changed |= _write_if_changed(store, text)
            for loc in locations_for(os_, d.browser, home):
                rb.locations.append(loc.target)
                if loc.kind == "registry":
                    if winreg.get(loc.target) != store:
                        winreg.set(loc.target, store)
                        rb.changed = True
                else:
                    rb.changed |= _write_if_changed(loc.target, text)  # copy, not symlink
        except Exception:
            logger.exception("registration failed for %s", d.browser)
            rb.supported, rb.note = False, "registration failed"
    return results


def unregister_all(home: Optional[str] = None, os_: Optional[str] = None, winreg=None) -> None:
    home = home or os.path.expanduser("~")
    os_ = os_ or os_name()
    if os_ == "windows" and winreg is None:
        winreg = WinRegistry()
    for browser in BROWSERS:
        for loc in locations_for(os_, browser, home):
            if loc.kind == "registry":
                winreg.delete(loc.target)
            else:
                try:
                    os.remove(loc.target)
                except OSError:
                    pass
    shutil.rmtree(paths.native_hosts_dir(home), ignore_errors=True)
