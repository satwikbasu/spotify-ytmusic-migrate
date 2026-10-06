"""Filesystem locations for the capture bridge (stdlib only, host-safe)."""

import os


def app_dir(home: str = None) -> str:
    return os.path.join(home or os.path.expanduser("~"), ".playlist_migrator")


def credentials_dir(home: str = None) -> str:
    return os.path.join(app_dir(home), "credentials")


def run_dir(home: str = None) -> str:
    return os.path.join(app_dir(home), "run")


def session_path(home: str = None) -> str:
    return os.path.join(credentials_dir(home), "youtube_session.enc")


def master_key_path(home: str = None) -> str:
    return os.path.join(app_dir(home), "master.key")


def native_hosts_dir(home: str = None) -> str:
    return os.path.join(app_dir(home), "native_hosts")


def private_dir(path: str) -> None:
    """Create ``path`` (and parents) and force mode 0700 where supported."""
    os.makedirs(path, mode=0o700, exist_ok=True)
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass


def write_private(path: str, data: bytes) -> None:
    """Atomically write ``data`` with mode 0600 (no world-readable window)."""
    private_dir(os.path.dirname(path))
    tmp = f"{path}.tmp{os.getpid()}"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    os.replace(tmp, path)
