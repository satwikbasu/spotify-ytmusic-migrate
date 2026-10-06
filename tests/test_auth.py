"""Unit tests for the authentication system.

This module contains comprehensive tests for:
- SpotifyAuthenticator
- YouTubeAuthenticator
- Token encryption utilities
- TokenManager

All tests use mocking to avoid hitting real APIs.
"""

import os
import json
import tempfile
import shutil
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta

import pytest
import spotipy
from ytmusicapi import YTMusic
from cryptography.fernet import Fernet

from src.auth.spotify_auth import SpotifyAuthenticator
from src.auth.youtube_auth import YouTubeAuthenticator
from src.auth.token_manager import TokenManager
from src.utils.encryption import (
    generate_key,
    save_key,
    load_key,
    encrypt_data,
    decrypt_data,
    encrypt_json_file,
    decrypt_json_file
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files.
    
    Yields:
        str: Path to temporary directory.
        
    Cleanup:
        Removes the temporary directory after test completion.
    """
    temp_path = tempfile.mkdtemp()
    yield temp_path
    # Cleanup
    if os.path.exists(temp_path):
        shutil.rmtree(temp_path)


@pytest.fixture
def encryption_key():
    """Generate a test encryption key.
    
    Returns:
        bytes: A Fernet encryption key for testing.
    """
    return generate_key()


@pytest.fixture
def mock_spotify_credentials():
    """Provide mock Spotify API credentials.
    
    Returns:
        dict: Dictionary with client_id and client_secret.
    """
    return {
        "client_id": "test_spotify_client_id",
        "client_secret": "test_spotify_client_secret"
    }


@pytest.fixture
def mock_youtube_credentials():
    """Provide mock YouTube API credentials.
    
    Returns:
        dict: Dictionary with client_id and client_secret.
    """
    return {
        "client_id": "test_youtube_client_id",
        "client_secret": "test_youtube_client_secret"
    }


@pytest.fixture
def mock_spotify_token():
    """Create a mock Spotify token cache.
    
    Returns:
        dict: Mock Spotify token data.
    """
    return {
        "access_token": "mock_spotify_access_token",
        "token_type": "Bearer",
        "expires_in": 3600,
        "refresh_token": "mock_spotify_refresh_token",
        "scope": "playlist-read-private,playlist-read-collaborative,user-library-read",
        "expires_at": int((datetime.now() + timedelta(hours=1)).timestamp())
    }


@pytest.fixture
def mock_youtube_token():
    """Create a mock YouTube OAuth token.
    
    Returns:
        dict: Mock YouTube token data.
    """
    return {
        "access_token": "mock_youtube_access_token",
        "refresh_token": "mock_youtube_refresh_token",
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": "test_youtube_client_id",
        "client_secret": "test_youtube_client_secret",
        "scopes": ["https://www.googleapis.com/auth/youtube.force-ssl"],
        "expiry": (datetime.now() + timedelta(hours=1)).isoformat()
    }


# ============================================================================
# Spotify Authentication Tests
# ============================================================================

def test_spotify_auth_new_user(temp_dir, mock_spotify_credentials, mock_spotify_token):
    """Test Spotify authentication for a new user (no cached token).
    
    This test validates that:
    1. SpotifyAuthenticator can perform OAuth flow for new users
    2. The authenticate() method returns a valid Spotify client
    3. Token is properly cached after authentication
    """
    cache_path = os.path.join(temp_dir, ".spotify_cache")
    
    # Create authenticator
    auth = SpotifyAuthenticator(
        client_id=mock_spotify_credentials["client_id"],
        client_secret=mock_spotify_credentials["client_secret"]
    )
    auth.cache_path = cache_path
    
    # Mock the OAuth flow
    with patch('src.auth.spotify_auth.SpotifyPKCE') as mock_oauth:
        # Mock OAuth manager
        mock_oauth_instance = MagicMock()
        mock_oauth.return_value = mock_oauth_instance
        
        # Mock token retrieval
        mock_oauth_instance.get_cached_token.return_value = None
        mock_oauth_instance.get_authorize_url.return_value = "http://mock.url"
        mock_oauth_instance.get_access_token.return_value = mock_spotify_token
        mock_oauth_instance.validate_token.return_value = mock_spotify_token
        
        # Mock Spotify client
        with patch('src.auth.spotify_auth.spotipy.Spotify') as mock_spotify:
            mock_client = MagicMock()
            mock_client.current_user.return_value = {"id": "test_user"}
            mock_spotify.return_value = mock_client
            
            # Perform authentication
            sp_client = auth.authenticate()
            
            # Assertions
            assert sp_client is not None
            assert isinstance(sp_client, MagicMock)
            mock_oauth_instance.get_access_token.assert_called_once()
            mock_client.current_user.assert_called_once()


def test_spotify_auth_cached_token(temp_dir, mock_spotify_credentials, mock_spotify_token):
    """Test Spotify authentication with cached token.
    
    This test validates that:
    1. is_authenticated() returns True when valid cached token exists
    2. Authenticator reuses cached token without re-authenticating
    3. No OAuth flow is triggered when valid token exists
    """
    cache_path = os.path.join(temp_dir, ".spotify_cache")
    
    # Create cache file with mock token
    with open(cache_path, 'w') as f:
        json.dump(mock_spotify_token, f)
    
    # Create authenticator
    auth = SpotifyAuthenticator(
        client_id=mock_spotify_credentials["client_id"],
        client_secret=mock_spotify_credentials["client_secret"]
    )
    auth.cache_path = cache_path
    
    # Mock OAuth to return cached token
    with patch('src.auth.spotify_auth.SpotifyPKCE') as mock_oauth:
        mock_oauth_instance = MagicMock()
        mock_oauth.return_value = mock_oauth_instance
        
        # Mock cached token validation
        mock_oauth_instance.get_cached_token.return_value = mock_spotify_token
        mock_oauth_instance.validate_token.return_value = mock_spotify_token
        
        # Test is_authenticated
        is_auth = auth.is_authenticated()
        assert is_auth is True
        
        # Mock Spotify client for authentication
        with patch('src.auth.spotify_auth.spotipy.Spotify') as mock_spotify:
            mock_client = MagicMock()
            mock_client.current_user.return_value = {"id": "test_user"}
            mock_spotify.return_value = mock_client
            
            # Authenticate with cached token
            sp_client = auth.authenticate()
            
            # Assertions
            assert sp_client is not None
            # Should use cached token, not call get_access_token
            mock_oauth_instance.get_access_token.assert_not_called()


def test_spotify_clear_cache(temp_dir, mock_spotify_credentials):
    """Test clearing Spotify cached credentials.
    
    This test validates that:
    1. clear_cache() removes the cached token file
    2. is_authenticated() returns False after clearing cache
    """
    cache_path = os.path.join(temp_dir, ".spotify_cache")
    
    # Create a dummy cache file
    with open(cache_path, 'w') as f:
        json.dump({"token": "dummy"}, f)
    
    # Create authenticator
    auth = SpotifyAuthenticator(
        client_id=mock_spotify_credentials["client_id"],
        client_secret=mock_spotify_credentials["client_secret"]
    )
    auth.cache_path = cache_path
    
    # Verify cache exists
    assert os.path.exists(cache_path)
    
    # Clear cache
    auth.clear_cache()
    
    # Verify cache is removed
    assert not os.path.exists(cache_path)


# ============================================================================
# YouTube Authentication Tests
# ============================================================================






def test_token_encryption(temp_dir, encryption_key):
    """Test token encryption and decryption workflow.
    
    This test validates that:
    1. JSON files can be encrypted
    2. Encrypted files can be decrypted
    3. Decrypted content matches original content
    4. Original file is deleted after encryption
    """
    # Create test token file
    test_token = {
        "access_token": "test_access_token_12345",
        "refresh_token": "test_refresh_token_67890",
        "expires_in": 3600,
        "token_type": "Bearer"
    }
    
    token_path = os.path.join(temp_dir, "test_token.json")
    
    with open(token_path, 'w') as f:
        json.dump(test_token, f, indent=2)
    
    # Verify original file exists
    assert os.path.exists(token_path)
    
    # Encrypt the file
    encrypt_json_file(token_path, encryption_key)
    
    # Verify original is deleted and encrypted file exists
    assert not os.path.exists(token_path)
    encrypted_path = f"{token_path}.enc"
    assert os.path.exists(encrypted_path)
    
    # Decrypt the file
    decrypted_data = decrypt_json_file(encrypted_path, encryption_key)
    
    # Verify decrypted content matches original
    assert decrypted_data == test_token
    assert decrypted_data["access_token"] == test_token["access_token"]
    assert decrypted_data["refresh_token"] == test_token["refresh_token"]


def test_encryption_key_save_load(temp_dir):
    """Test encryption key saving and loading.
    
    This test validates that:
    1. Encryption keys can be saved to disk
    2. Keys can be loaded from disk
    3. Loaded key matches saved key
    """
    key_path = os.path.join(temp_dir, "test_master.key")
    
    # Generate key
    original_key = generate_key()
    
    # Save key
    save_key(original_key, key_path)
    
    # Verify file exists
    assert os.path.exists(key_path)
    
    # Load key
    loaded_key = load_key(key_path)
    
    # Verify keys match
    assert loaded_key == original_key


def test_encrypt_decrypt_data(encryption_key):
    """Test string encryption and decryption.
    
    This test validates that:
    1. String data can be encrypted to bytes
    2. Encrypted bytes can be decrypted back to string
    3. Decrypted string matches original
    """
    original_data = "This is sensitive token data with special chars: !@#$%^&*()"
    
    # Encrypt
    encrypted = encrypt_data(original_data, encryption_key)
    
    # Verify it's bytes and different from original
    assert isinstance(encrypted, bytes)
    assert encrypted != original_data.encode()
    
    # Decrypt
    decrypted = decrypt_data(encrypted, encryption_key)
    
    # Verify decrypted matches original
    assert decrypted == original_data


# ============================================================================
# TokenManager Integration Tests
# ============================================================================

def test_token_manager_initialization(mock_spotify_credentials, mock_youtube_credentials, temp_dir):
    """Test TokenManager initialization.
    
    This test validates that:
    1. TokenManager initializes with valid credentials
    2. Encryption key is loaded or generated
    3. Tokens directory is created
    """
    # Mock the ensure_master_key to use temp directory
    with patch('src.auth.token_manager.ensure_master_key') as mock_ensure_key:
        test_key = generate_key()
        mock_ensure_key.return_value = test_key
        
        # Patch the tokens directory to use temp
        with patch.object(TokenManager, 'TOKENS_DIR', temp_dir):
            # Create TokenManager
            manager = TokenManager(
                spotify_client_id=mock_spotify_credentials["client_id"],
                spotify_client_secret=mock_spotify_credentials["client_secret"],
                youtube_client_id=mock_youtube_credentials["client_id"],
                youtube_client_secret=mock_youtube_credentials["client_secret"]
            )
            
            # Assertions
            assert manager.encryption_key == test_key
            assert manager.spotify_auth is not None
            assert manager.youtube_auth is not None
            assert os.path.exists(temp_dir)




def test_token_manager_invalid_credentials():
    """TokenManager requires exactly one credential: the Spotify Client ID.

    CONTEXT_CONTRACT.md §4.2: Spotify uses PKCE (no secret) and YouTube Music
    uses browser cookies (no Google client at all). Only a missing Spotify
    Client ID may raise.
    """
    with pytest.raises(ValueError, match="Spotify Client ID is required"):
        TokenManager(
            spotify_client_id="",
            spotify_client_secret="secret",
            youtube_client_id="id",
            youtube_client_secret="secret"
        )

    with pytest.raises(ValueError, match="Spotify Client ID is required"):
        TokenManager(spotify_client_id="   ")


# ============================================================================
# CONTEXT_CONTRACT §4.2: PKCE, no secrets, port-less loopback redirect
# ============================================================================

def _manager_without_google_creds(temp_dir):
    with patch('src.auth.token_manager.ensure_master_key', return_value=generate_key()):
        with patch.object(TokenManager, 'TOKENS_DIR', temp_dir):
            return TokenManager(spotify_client_id="0123456789abcdef0123456789abcdef")


def test_token_manager_needs_no_youtube_or_spotify_secret(temp_dir):
    """A non-technical user has no Google Cloud project and no Spotify secret."""
    manager = _manager_without_google_creds(temp_dir)

    assert manager.spotify_auth.client_id == "0123456789abcdef0123456789abcdef"
    assert manager.spotify_auth.client_secret is None
    assert manager.youtube_auth.client_id is None
    assert manager.youtube_auth.client_secret is None


def test_token_manager_treats_empty_youtube_creds_as_absent(temp_dir):
    """Empty env strings (the .env default) must behave like 'not provided'."""
    with patch('src.auth.token_manager.ensure_master_key', return_value=generate_key()):
        with patch.object(TokenManager, 'TOKENS_DIR', temp_dir):
            manager = TokenManager(
                spotify_client_id="id",
                spotify_client_secret="",
                youtube_client_id="",
                youtube_client_secret="",
            )
    assert manager.youtube_auth.client_id is None
    assert manager.youtube_auth.client_secret is None


def test_token_manager_loads_captured_session_without_google_creds(temp_dir, tmp_path):
    """The encrypted captured session yields a client with no Google creds and
    no headers.json anywhere."""
    from src.capture.session_store import SessionStore
    manager = _manager_without_google_creds(temp_dir)
    manager.youtube_session_store = SessionStore(
        path=str(tmp_path / "youtube_session.enc"), key=manager.encryption_key)
    manager.youtube_session_store.save({"cookie": "x", "authorization": "SAPISIDHASH y"}, "Tester")
    assert manager.is_youtube_authenticated()

    signed_in = MagicMock()
    signed_in.get_account_info.return_value = {"accountName": "Tester"}
    limiter = MagicMock()
    with patch("src.auth.token_manager.YTMusic", return_value=signed_in) as ctor:
        client = manager.authenticate_youtube(rate_limiter=limiter)

    assert client is signed_in
    assert ctor.call_args.kwargs["auth"]["cookie"] == "x"
    limiter.check_limit.assert_called_once()  # identity call goes through RateLimiter
    manager.clear_youtube_token()
    assert not manager.is_youtube_authenticated()


def test_token_manager_without_google_creds_still_refuses_oauth(temp_dir, tmp_path):
    """Dropping the requirement must not revive the dead OAuth path."""
    manager = _manager_without_google_creds(temp_dir)
    from src.capture.session_store import SessionStore
    manager.youtube_session_store = SessionStore(
        path=str(tmp_path / "absent.enc"), key=manager.encryption_key)

    with pytest.raises(RuntimeError, match="(?i)extension"):
        manager.authenticate_youtube()


def test_youtube_oauth_method_always_raises_explanation():
    """_authenticate_oauth() is a settled dead end and must keep raising."""
    auth = YouTubeAuthenticator(client_id="cid", client_secret="secret")
    with pytest.raises(RuntimeError, match="(?i)OAuth cannot authenticate"):
        auth._authenticate_oauth()


def test_spotify_authenticator_requires_only_client_id():
    auth = SpotifyAuthenticator(client_id="abc")
    assert auth.client_id == "abc"
    assert auth.client_secret is None

    auth_empty_secret = SpotifyAuthenticator(client_id="abc", client_secret="")
    assert auth_empty_secret.client_secret == ""

    with pytest.raises(ValueError, match="Client ID"):
        SpotifyAuthenticator(client_id="")
    with pytest.raises(ValueError, match="Client ID"):
        SpotifyAuthenticator(client_id=None)


def test_spotify_authenticator_strips_pasted_client_id():
    """The wizard will hand over whatever the user pasted; whitespace is noise."""
    auth = SpotifyAuthenticator(client_id="  abc123  ")
    assert auth.client_id == "abc123"


def test_spotify_default_redirect_uri_is_portless_loopback():
    auth = SpotifyAuthenticator(client_id="abc")
    assert auth.registered_redirect_uri == "http://127.0.0.1/callback"
    assert "localhost" not in auth.registered_redirect_uri
    assert SpotifyAuthenticator.DEFAULT_REDIRECT_URI == "http://127.0.0.1/callback"


def test_spotify_pkce_constructed_with_client_id_and_no_secret(temp_dir):
    """The auth manager is SpotifyPKCE, given a client id, scopes, the cache
    path and a concrete loopback redirect with a dynamically bound port."""
    auth = SpotifyAuthenticator(client_id="abc")
    auth.cache_path = os.path.join(temp_dir, ".spotify_cache")

    with patch('src.auth.spotify_auth.SpotifyPKCE') as mock_pkce, \
         patch('src.auth.spotify_auth.find_free_loopback_port', return_value=43210):
        manager = auth._get_oauth_manager()

    assert manager is mock_pkce.return_value
    mock_pkce.assert_called_once()
    kwargs = mock_pkce.call_args.kwargs
    assert kwargs["client_id"] == "abc"
    assert "client_secret" not in kwargs
    assert kwargs["redirect_uri"] == "http://127.0.0.1:43210/callback"
    assert kwargs["scope"] == SpotifyAuthenticator.REQUIRED_SCOPES
    assert kwargs["cache_path"] == auth.cache_path
    assert kwargs["open_browser"] is True
    assert auth.redirect_uri == "http://127.0.0.1:43210/callback"


def test_spotify_pkce_scopes_unchanged():
    scopes = set(SpotifyAuthenticator.REQUIRED_SCOPES.split(","))
    assert scopes == {"playlist-read-private", "playlist-read-collaborative", "user-library-read"}


def test_spotify_redirect_port_falls_back_when_binding_fails():
    from src.auth.spotify_auth import resolve_redirect_uri, FALLBACK_REDIRECT_PORT

    with patch('src.auth.spotify_auth.find_free_loopback_port', side_effect=OSError("no ports")):
        uri = resolve_redirect_uri("http://127.0.0.1/callback")

    assert uri == f"http://127.0.0.1:{FALLBACK_REDIRECT_PORT}/callback"


def test_spotify_redirect_with_explicit_port_is_left_alone():
    from src.auth.spotify_auth import resolve_redirect_uri

    with patch('src.auth.spotify_auth.find_free_loopback_port') as binder:
        uri = resolve_redirect_uri("http://127.0.0.1:9999/callback")

    assert uri == "http://127.0.0.1:9999/callback"
    binder.assert_not_called()


def test_find_free_loopback_port_binds_127_0_0_1():
    """The dynamic port comes from binding 127.0.0.1:0, never localhost."""
    from src.auth.spotify_auth import find_free_loopback_port
    import socket as real_socket

    with patch('src.auth.spotify_auth.socket.socket') as mock_socket_cls:
        sock = mock_socket_cls.return_value.__enter__.return_value
        sock.getsockname.return_value = ("127.0.0.1", 50505)

        assert find_free_loopback_port() == 50505
        sock.bind.assert_called_once_with(("127.0.0.1", 0))


def test_spotify_authenticate_with_only_client_id_runs_pkce_flow(temp_dir, mock_spotify_token):
    """End to end (mocked): client id only -> PKCE -> token -> client."""
    auth = SpotifyAuthenticator(client_id="abc")
    auth.cache_path = os.path.join(temp_dir, ".spotify_cache")

    with patch('src.auth.spotify_auth.SpotifyPKCE') as mock_pkce, \
         patch('src.auth.spotify_auth.find_free_loopback_port', return_value=43210), \
         patch('src.auth.spotify_auth.spotipy.Spotify') as mock_spotify:
        pkce = mock_pkce.return_value
        pkce.get_cached_token.return_value = None
        pkce.get_access_token.return_value = mock_spotify_token
        mock_spotify.return_value.current_user.return_value = {"id": "u"}

        client = auth.authenticate()

    assert client is mock_spotify.return_value
    pkce.get_access_token.assert_called_once_with()
    mock_spotify.assert_called_once_with(auth_manager=pkce)


def test_token_manager_spotify_cache_still_encrypted_at_rest(temp_dir, mock_spotify_token):
    """After a PKCE login the plaintext cache is encrypted into TOKENS_DIR."""
    manager = _manager_without_google_creds(temp_dir)
    cache_path = os.path.join(temp_dir, ".spotify_cache_plain")
    manager.spotify_auth.cache_path = cache_path
    with open(cache_path, "w") as f:
        json.dump(mock_spotify_token, f)

    with patch.object(manager.spotify_auth, 'authenticate', return_value=MagicMock()):
        manager.authenticate_spotify()

    assert not os.path.exists(cache_path)
    enc_path = manager._get_encrypted_path(TokenManager.SPOTIFY_CACHE_NAME)
    assert os.path.exists(enc_path)
    assert decrypt_json_file(enc_path, manager.encryption_key) == mock_spotify_token


def test_token_manager_passes_registered_redirect_uri_through(temp_dir):
    with patch('src.auth.token_manager.ensure_master_key', return_value=generate_key()):
        with patch.object(TokenManager, 'TOKENS_DIR', temp_dir):
            manager = TokenManager(
                spotify_client_id="id",
                spotify_redirect_uri="http://127.0.0.1/callback",
            )
    assert manager.spotify_auth.registered_redirect_uri == "http://127.0.0.1/callback"


# ---------------------------------------------------------------------------
# Regression: browser auth must reject a signed-out session (B10)
# ---------------------------------------------------------------------------

def _authenticator_with_headers(tmp_path):
    """Build a YouTubeAuthenticator pointed at a throwaway headers file."""
    from src.auth.youtube_auth import YouTubeAuthenticator
    headers = tmp_path / "headers.json"
    headers.write_text('{"cookie": "x", "authorization": "SAPISIDHASH y"}', encoding="utf-8")
    auth = YouTubeAuthenticator()
    auth.browser_headers_path = headers
    return auth


def test_browser_auth_raises_when_session_is_signed_out(tmp_path):
    """An empty library must not be read as a successful login.

    A signed-out session returns [] from get_library_playlists rather than
    raising, so the old connection test printed a success banner and returned
    the client. The failure only surfaced later as HTTP 401 on the first write.
    """
    import pytest
    from unittest.mock import patch, MagicMock

    signed_out = MagicMock()
    signed_out.get_library_playlists.return_value = []
    signed_out.get_account_info.side_effect = KeyError("header")

    auth = _authenticator_with_headers(tmp_path)
    with patch("src.auth.youtube_auth.YTMusic", return_value=signed_out):
        with pytest.raises(RuntimeError, match="(?i)sign|auth"):
            auth.authenticate()


def test_browser_auth_accepts_a_signed_in_session_with_an_empty_library(tmp_path):
    """A genuinely signed-in account with no playlists must still authenticate."""
    from unittest.mock import patch, MagicMock

    signed_in = MagicMock()
    signed_in.get_library_playlists.return_value = []
    signed_in.get_account_info.return_value = {"accountName": "Tester"}

    auth = _authenticator_with_headers(tmp_path)
    with patch("src.auth.youtube_auth.YTMusic", return_value=signed_in):
        client = auth.authenticate()

    assert client is signed_in


def test_oauth_path_fails_with_a_clear_explanation(tmp_path):
    """OAuth cannot work against YouTube Music, so it must say so up front.

    The device flow completes and returns a valid token, but every subsequent
    call returns HTTP 400 because YouTube Music's internal API does not accept
    tokens from custom Google Cloud clients. Failing at authenticate() time with
    an explanation beats failing later with 'invalid argument'.
    """
    import pytest
    from src.auth.youtube_auth import YouTubeAuthenticator

    auth = YouTubeAuthenticator(client_id="cid", client_secret="secret")
    auth.browser_headers_path = tmp_path / "absent.json"
    auth.browser_alt_path = tmp_path / "also-absent.json"

    with pytest.raises(RuntimeError, match="(?i)browser"):
        auth.authenticate()


# Removed: test_youtube_auth_new_user, test_youtube_auth_cached_credentials,
# test_youtube_clear_cache and test_token_manager_full_flow exercised the old
# google-auth-oauthlib InstalledAppFlow implementation, which no longer exists.
# Current OAuth behaviour is covered by test_oauth_path_fails_with_a_clear_explanation.

