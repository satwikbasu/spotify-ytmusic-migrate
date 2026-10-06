"""Spotify OAuth 2.0 Authentication Module.

This module authenticates against the Spotify Web API using the
Authorization Code flow **with PKCE** (RFC 7636). PKCE is a public-client
flow: it needs only a Client ID, never a client secret, so the user can bring
their own Spotify app (CONTEXT_CONTRACT.md §4.2, Option A) without ever
handling a secret.

Redirect URI handling (CONTEXT_CONTRACT.md §4.2):
    The user registers the **port-less** loopback URI
    ``http://127.0.0.1/callback`` in the Spotify dashboard. Spotify's loopback
    rule matches that registration against any port, so at authentication
    time we bind a free loopback port and hand spotipy the concrete
    ``http://127.0.0.1:<port>/callback``. A port mismatch is therefore
    impossible, and nothing has to be typed or pasted by the user.
    ``localhost`` is forbidden by Spotify (Nov 2025); only the IP literal is
    used.
"""

import os
import socket
import time
from typing import Optional
from urllib.parse import urlsplit, urlunsplit

import spotipy
from spotipy.oauth2 import SpotifyPKCE
import requests.exceptions


LOOPBACK_HOST = "127.0.0.1"
PORTLESS_REDIRECT_URI = f"http://{LOOPBACK_HOST}/callback"
FALLBACK_REDIRECT_PORT = 8888


def find_free_loopback_port() -> int:
    """Ask the OS for a currently free TCP port on 127.0.0.1.

    The socket is closed immediately; spotipy's one-shot callback server
    re-binds the port moments later. The tiny race this leaves is acceptable
    for a local, single-user desktop app.

    Returns:
        int: A free port number.

    Raises:
        OSError: If no loopback socket can be bound.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((LOOPBACK_HOST, 0))
        return sock.getsockname()[1]


def resolve_redirect_uri(registered_uri: str) -> str:
    """Turn the registered (possibly port-less) redirect URI into a concrete one.

    - ``http://127.0.0.1/callback`` -> ``http://127.0.0.1:<free port>/callback``
    - a URI that already names a port is returned unchanged
    - if the OS refuses to hand out a port, ``FALLBACK_REDIRECT_PORT`` is used

    spotipy only starts its local callback server when the redirect URI has an
    explicit port; without one it would fall back to asking the user to paste
    the redirected URL, which is exactly the manual step §1 forbids.

    Args:
        registered_uri (str): The URI as registered in the Spotify dashboard.

    Returns:
        str: A redirect URI with an explicit port.
    """
    parts = urlsplit(registered_uri)
    if parts.port is not None:
        return registered_uri

    try:
        port = find_free_loopback_port()
    except OSError:
        port = FALLBACK_REDIRECT_PORT

    netloc = f"{parts.hostname}:{port}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


class SpotifyAuthenticator:
    """Handles Spotify Authorization Code + PKCE authentication and token caching.

    Attributes:
        client_id (str): Spotify application client ID (the only credential).
        client_secret (Optional[str]): Accepted for backward compatibility and
            ignored - PKCE never sends a secret.
        registered_redirect_uri (str): The URI registered in the dashboard,
            port-less by default.
        redirect_uri (str): The concrete URI (with port) used for the current
            OAuth manager, resolved lazily when the manager is built.
        scope (str): Comma-separated list of Spotify API scopes.
        cache_path (str): Path to the plaintext token cache. TokenManager
            encrypts this file at rest immediately after authentication.
    """

    # spotipy splits a scope string on commas (normalize_scope); keep that form.
    REQUIRED_SCOPES = "playlist-read-private,playlist-read-collaborative,user-library-read"
    DEFAULT_REDIRECT_URI = PORTLESS_REDIRECT_URI
    MAX_RETRIES = 4

    def __init__(
        self,
        client_id: str,
        client_secret: Optional[str] = None,
        redirect_uri: Optional[str] = None,
    ):
        """Initialize the Spotify authenticator.

        Args:
            client_id (str): Spotify application client ID from the user's own
                app in the Spotify Developer Dashboard.
            client_secret (Optional[str]): Ignored. Kept so existing callers
                that still pass it keep working; PKCE does not use a secret.
            redirect_uri (Optional[str]): Registered redirect URI. Defaults to
                the port-less ``http://127.0.0.1/callback``.

        Raises:
            ValueError: If client_id is empty or None.
        """
        if not client_id or not str(client_id).strip():
            raise ValueError("Spotify Client ID is required")

        self.client_id = str(client_id).strip()
        self.client_secret = client_secret  # unused with PKCE
        self.registered_redirect_uri = redirect_uri or self.DEFAULT_REDIRECT_URI
        self.redirect_uri: str = self.registered_redirect_uri
        self.scope = self.REQUIRED_SCOPES
        self.cache_path = os.path.expanduser("~/.spotify_cache")

        self._sp_oauth: Optional[SpotifyPKCE] = None

    def _get_oauth_manager(self) -> SpotifyPKCE:
        """Get or create the SpotifyPKCE manager instance.

        On first use the port-less registered redirect URI is resolved to a
        concrete loopback URI with a free port.

        Returns:
            SpotifyPKCE: Configured PKCE auth manager.
        """
        if self._sp_oauth is None:
            self.redirect_uri = resolve_redirect_uri(self.registered_redirect_uri)
            self._sp_oauth = SpotifyPKCE(
                client_id=self.client_id,
                redirect_uri=self.redirect_uri,
                scope=self.scope,
                cache_path=self.cache_path,
                open_browser=True,
            )
        return self._sp_oauth

    def authenticate(self) -> spotipy.Spotify:
        """Authenticate with Spotify and return an authenticated client.

        Uses a cached token when one exists, otherwise opens the user's browser
        for the PKCE authorization flow and receives the code on the loopback
        callback server. Network failures are retried with exponential backoff
        (1s, 2s, 4s, 8s; max 4 attempts).

        Returns:
            spotipy.Spotify: An authenticated Spotify client instance.

        Raises:
            spotipy.SpotifyException: If the user denies authorization or the
                Client ID / redirect URI is rejected.
            RuntimeError: If authentication fails after maximum retry attempts
                or an unexpected error occurs.
        """
        retry_count = 0
        last_exception = None

        while retry_count < self.MAX_RETRIES:
            try:
                oauth_manager = self._get_oauth_manager()

                token_info = oauth_manager.get_cached_token()

                if not token_info:
                    # No cached token: run the PKCE flow. spotipy opens the
                    # browser and serves the loopback callback itself.
                    token_info = oauth_manager.get_access_token()

                if not token_info:
                    raise spotipy.SpotifyException(
                        http_status=401,
                        code=-1,
                        msg="User denied authorization or authentication failed"
                    )

                sp = spotipy.Spotify(auth_manager=oauth_manager)

                # Verify authentication by making a test API call
                sp.current_user()

                return sp

            except spotipy.SpotifyException as e:
                # Don't retry on authorization errors (user denied, bad client id)
                if e.http_status in [401, 403]:
                    raise spotipy.SpotifyException(
                        http_status=e.http_status,
                        code=e.code,
                        msg=f"Spotify authentication failed: {e.msg}. "
                            f"Check the Client ID and that http://127.0.0.1/callback "
                            f"is registered as a redirect URI, then grant authorization."
                    ) from e

                last_exception = e
                retry_count += 1

            except requests.exceptions.RequestException as e:
                last_exception = e
                retry_count += 1

            except Exception as e:
                raise RuntimeError(f"Unexpected error during Spotify authentication: {str(e)}") from e

            if retry_count < self.MAX_RETRIES:
                delay = 2 ** (retry_count - 1)
                print(f"Authentication attempt {retry_count} failed. Retrying in {delay}s...")
                time.sleep(delay)

        raise RuntimeError(
            f"Spotify authentication failed after {self.MAX_RETRIES} attempts. "
            f"Last error: {str(last_exception)}"
        ) from last_exception

    def is_authenticated(self) -> bool:
        """Check if a valid cached authentication token exists.

        Returns:
            bool: True if a valid cached token exists, False otherwise.
        """
        try:
            oauth_manager = self._get_oauth_manager()
            token_info = oauth_manager.get_cached_token()

            if token_info is None:
                return False

            # validate_token refreshes an expired token when a refresh token
            # is available and returns None when it cannot.
            return oauth_manager.validate_token(token_info) is not None

        except Exception:
            return False

    def clear_cache(self) -> None:
        """Remove cached Spotify credentials from disk.

        Note:
            This method does not raise an error if the cache file doesn't exist.
        """
        try:
            if os.path.exists(self.cache_path):
                os.remove(self.cache_path)
                print(f"Spotify cache cleared: {self.cache_path}")
            else:
                print("No Spotify cache found to clear")
        except OSError as e:
            print(f"Warning: Failed to clear Spotify cache: {str(e)}")

        # Reset the auth manager so the next use re-resolves the port too
        self._sp_oauth = None
