"""Spotify OAuth 2.0 Authentication Module.

This module provides authentication functionality for the Spotify API using
the Authorization Code Flow with PKCE support.
"""

import os
import time
from typing import Optional

import spotipy
from spotipy.oauth2 import SpotifyOAuth
import requests.exceptions


class SpotifyAuthenticator:
    """Handles Spotify OAuth 2.0 authentication and token management.
    
    This class manages the OAuth 2.0 Authorization Code Flow for Spotify API
    authentication, including token caching, validation, and refresh.
    
    Attributes:
        client_id (str): Spotify application client ID.
        client_secret (str): Spotify application client secret.
        redirect_uri (str): OAuth callback URL (default: http://127.0.0.1:8888/callback).
        scope (str): Space-separated list of Spotify API scopes.
        cache_path (str): Path to the token cache file.
    
    Note:
        As of November 2025, Spotify forbids 'localhost' in redirect URIs.
        Use loopback IP literals: 127.0.0.1 (IPv4) or [::1] (IPv6).
    """
    
    REQUIRED_SCOPES = "playlist-read-private,playlist-read-collaborative,user-library-read"
    DEFAULT_REDIRECT_URI = "http://127.0.0.1:8888/callback"  # Changed from localhost (Nov 2025 requirement)
    MAX_RETRIES = 4
    
    def __init__(self, client_id: str, client_secret: str):
        """Initialize the Spotify authenticator.
        
        Args:
            client_id (str): Spotify application client ID from the Spotify Developer Dashboard.
            client_secret (str): Spotify application client secret from the Spotify Developer Dashboard.
            
        Raises:
            ValueError: If client_id or client_secret is empty or None.
        """
        if not client_id or not client_secret:
            raise ValueError("Client ID and Client Secret are required")
        
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = self.DEFAULT_REDIRECT_URI
        self.scope = self.REQUIRED_SCOPES
        self.cache_path = os.path.expanduser("~/.spotify_cache")
        
        self._sp_oauth: Optional[SpotifyOAuth] = None
    
    def _get_oauth_manager(self) -> SpotifyOAuth:
        """Get or create the SpotifyOAuth manager instance.
        
        Returns:
            SpotifyOAuth: Configured OAuth manager instance.
        """
        if self._sp_oauth is None:
            self._sp_oauth = SpotifyOAuth(
                client_id=self.client_id,
                client_secret=self.client_secret,
                redirect_uri=self.redirect_uri,
                scope=self.scope,
                cache_path=self.cache_path,
                open_browser=True
            )
        return self._sp_oauth
    
    def authenticate(self) -> spotipy.Spotify:
        """Authenticate with Spotify and return an authenticated client.
        
        This method attempts to authenticate with Spotify using OAuth 2.0.
        It will try to use cached credentials if available, otherwise it will
        initiate the OAuth flow in the user's browser.
        
        The method implements exponential backoff retry logic for network failures:
        - Retry delays: 1s, 2s, 4s, 8s (max 4 attempts)
        
        Returns:
            spotipy.Spotify: An authenticated Spotify client instance.
            
        Raises:
            spotipy.SpotifyException: If authentication fails due to invalid credentials
                or if the user denies authorization.
            requests.exceptions.RequestException: If network errors persist after all retries.
            RuntimeError: If authentication fails after maximum retry attempts.
        """
        retry_count = 0
        last_exception = None
        
        while retry_count < self.MAX_RETRIES:
            try:
                oauth_manager = self._get_oauth_manager()
                
                # Attempt to get cached token or initiate OAuth flow
                token_info = oauth_manager.get_cached_token()
                
                if not token_info:
                    # No cached token, initiate OAuth flow
                    auth_url = oauth_manager.get_authorize_url()
                    print(f"Please navigate to: {auth_url}")
                    
                    # Wait for callback (spotipy handles this internally)
                    token_info = oauth_manager.get_access_token(as_dict=True)
                
                if not token_info:
                    raise spotipy.SpotifyException(
                        http_status=401,
                        code=-1,
                        msg="User denied authorization or authentication failed"
                    )
                
                # Create and return authenticated Spotify client
                sp = spotipy.Spotify(auth_manager=oauth_manager)
                
                # Verify authentication by making a test API call
                sp.current_user()
                
                return sp
                
            except spotipy.SpotifyException as e:
                # Don't retry on authorization errors (user denied, invalid credentials)
                if e.http_status in [401, 403]:
                    raise spotipy.SpotifyException(
                        http_status=e.http_status,
                        code=e.code,
                        msg=f"Spotify authentication failed: {e.msg}. "
                            f"Please check your credentials or grant authorization."
                    ) from e
                
                # For other Spotify exceptions, retry
                last_exception = e
                retry_count += 1
                
            except requests.exceptions.RequestException as e:
                # Network error - retry with exponential backoff
                last_exception = e
                retry_count += 1
                
            except Exception as e:
                # Unexpected error - don't retry
                raise RuntimeError(f"Unexpected error during Spotify authentication: {str(e)}") from e
            
            # Exponential backoff: 1s, 2s, 4s, 8s
            if retry_count < self.MAX_RETRIES:
                delay = 2 ** (retry_count - 1)
                print(f"Authentication attempt {retry_count} failed. Retrying in {delay}s...")
                time.sleep(delay)
        
        # All retries exhausted
        raise RuntimeError(
            f"Spotify authentication failed after {self.MAX_RETRIES} attempts. "
            f"Last error: {str(last_exception)}"
        ) from last_exception
    
    def is_authenticated(self) -> bool:
        """Check if a valid cached authentication token exists.
        
        This method verifies whether there is a valid, non-expired token
        in the cache that can be used for API requests.
        
        Returns:
            bool: True if a valid cached token exists, False otherwise.
        """
        try:
            oauth_manager = self._get_oauth_manager()
            token_info = oauth_manager.get_cached_token()
            
            if token_info is None:
                return False
            
            # Check if token is expired
            # SpotifyOAuth automatically handles token refresh if needed
            return oauth_manager.validate_token(token_info) is not None
            
        except Exception:
            # If any error occurs during validation, consider not authenticated
            return False
    
    def clear_cache(self) -> None:
        """Remove cached Spotify credentials from disk.
        
        This method deletes the token cache file, requiring the user to
        re-authenticate on the next authentication attempt.
        
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
        
        # Reset the OAuth manager to force re-initialization
        self._sp_oauth = None
