"""Token Manager Module.

This module provides a unified token management system that combines authentication
and encryption for both Spotify and YouTube Music services.
"""

import os
import logging
from typing import Optional
import shutil

import spotipy
from ytmusicapi import YTMusic

from ..auth.spotify_auth import SpotifyAuthenticator
from ..auth.youtube_auth import YouTubeAuthenticator
from ..capture.session_store import SessionStore
from ..utils.encryption import (
    ensure_master_key,
    encrypt_json_file,
    decrypt_json_file,
    load_key
)


# Configure logging
logger = logging.getLogger(__name__)


class TokenManager:
    """Unified token management system with authentication and encryption.
    
    This class manages OAuth tokens for both Spotify and YouTube Music,
    providing encrypted storage and automatic token lifecycle management.
    
    Token Storage:
    - Encrypted tokens are stored in ~/.playlist_migrator/tokens/
    - Spotify: .spotify_cache.enc
    - YouTube Music: youtube_oauth.json.enc
    - Encryption key: ~/.playlist_migrator/master.key
    
    Attributes:
        spotify_auth (SpotifyAuthenticator): Spotify authentication handler.
        youtube_auth (YouTubeAuthenticator): YouTube Music authentication handler.
        encryption_key (bytes): Master encryption key for token storage.
        tokens_dir (str): Directory where encrypted tokens are stored.
    """
    
    TOKENS_DIR = os.path.expanduser("~/.playlist_migrator/tokens")
    MASTER_KEY_PATH = os.path.expanduser("~/.playlist_migrator/master.key")
    
    SPOTIFY_CACHE_NAME = ".spotify_cache"
    YOUTUBE_CACHE_NAME = "youtube_oauth.json"
    
    def __init__(
        self,
        spotify_client_id: str,
        spotify_client_secret: Optional[str] = None,
        youtube_client_id: Optional[str] = None,
        youtube_client_secret: Optional[str] = None,
        spotify_redirect_uri: Optional[str] = None,
    ):
        """Initialize the Token Manager with client credentials.

        Sets up authenticators for both services and ensures the encryption
        infrastructure is in place.

        The only required credential is the Spotify Client ID
        (CONTEXT_CONTRACT.md §4.2: BYO Client ID + PKCE, no secret). The
        YouTube/Google client id and secret are accepted for backward
        compatibility but are NOT required: YouTube Music is authenticated with
        captured browser cookies, and Google OAuth cannot work against it at
        all (see YouTubeAuthenticator._authenticate_oauth). Demanding them only
        blocked users who have no reason to own Google Cloud credentials.

        Args:
            spotify_client_id (str): Spotify application client ID.
            spotify_client_secret (Optional[str]): Ignored (PKCE uses no secret).
            youtube_client_id (Optional[str]): Ignored unless the dead OAuth path
                is ever revived; browser-cookie auth needs no client.
            youtube_client_secret (Optional[str]): Same as above.
            spotify_redirect_uri (Optional[str]): Registered Spotify redirect
                URI; defaults to the port-less ``http://127.0.0.1/callback``.

        Raises:
            ValueError: If the Spotify Client ID is empty or None.
            OSError: If token directory cannot be created.
        """
        if not spotify_client_id or not str(spotify_client_id).strip():
            raise ValueError("Spotify Client ID is required")

        logger.info("Initializing TokenManager")

        # Initialize authenticators
        self.spotify_auth = SpotifyAuthenticator(
            client_id=spotify_client_id,
            client_secret=spotify_client_secret,
            redirect_uri=spotify_redirect_uri,
        )

        self.youtube_auth = YouTubeAuthenticator(
            client_id=youtube_client_id or None,
            client_secret=youtube_client_secret or None
        )
        
        # Ensure tokens directory exists
        try:
            if not os.path.exists(self.TOKENS_DIR):
                os.makedirs(self.TOKENS_DIR, mode=0o700)
                logger.info(f"Created tokens directory: {self.TOKENS_DIR}")
        except OSError as e:
            logger.error(f"Failed to create tokens directory: {str(e)}")
            raise OSError(f"Cannot create tokens directory: {str(e)}") from e
        
        # Load or generate encryption key
        try:
            self.encryption_key = ensure_master_key(self.MASTER_KEY_PATH)
            logger.info("Encryption key loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load encryption key: {str(e)}")
            raise RuntimeError(f"Encryption key initialization failed: {str(e)}") from e
        
        self.tokens_dir = self.TOKENS_DIR

        # Captured YouTube Music session (extension -> Native Messaging),
        # Fernet-encrypted under ~/.playlist_migrator/credentials/.
        self.youtube_session_store = SessionStore(key=self.encryption_key)
    
    def _get_encrypted_path(self, cache_name: str) -> str:
        """Get the path for an encrypted token file.
        
        Args:
            cache_name (str): Name of the cache file.
            
        Returns:
            str: Full path to the encrypted token file.
        """
        return os.path.join(self.tokens_dir, f"{cache_name}.enc")
    
    def _encrypt_token_file(self, source_path: str, cache_name: str) -> None:
        """Encrypt a token file and move it to the tokens directory.
        
        Args:
            source_path (str): Path to the original unencrypted token file.
            cache_name (str): Base name for the encrypted cache file.
            
        Raises:
            FileNotFoundError: If source file doesn't exist.
            IOError: If encryption or file operations fail.
        """
        expanded_source = os.path.expanduser(source_path)
        
        if not os.path.exists(expanded_source):
            raise FileNotFoundError(f"Token file not found: {expanded_source}")
        
        try:
            # Encrypt the file (this also deletes the original)
            encrypt_json_file(expanded_source, self.encryption_key)
            
            # Move encrypted file to tokens directory
            encrypted_source = f"{expanded_source}.enc"
            encrypted_dest = self._get_encrypted_path(cache_name)
            
            # Only move if source and destination are different
            if encrypted_source != encrypted_dest:
                if os.path.exists(encrypted_dest):
                    os.remove(encrypted_dest)
                
                shutil.move(encrypted_source, encrypted_dest)
                logger.info(f"Token encrypted and moved to: {encrypted_dest}")
            else:
                logger.info(f"Token encrypted: {encrypted_dest}")
            
        except Exception as e:
            logger.error(f"Failed to encrypt token file: {str(e)}")
            raise IOError(f"Token encryption failed: {str(e)}") from e
    
    def _decrypt_to_temp(self, cache_name: str) -> str:
        """Decrypt a token file to a temporary location.
        
        Args:
            cache_name (str): Base name of the cache file.
            
        Returns:
            str: Path to the decrypted temporary file.
            
        Raises:
            FileNotFoundError: If encrypted file doesn't exist.
            IOError: If decryption fails.
        """
        encrypted_path = self._get_encrypted_path(cache_name)
        
        if not os.path.exists(encrypted_path):
            raise FileNotFoundError(f"Encrypted token not found: {encrypted_path}")
        
        try:
            # Decrypt the JSON data
            decrypted_data = decrypt_json_file(encrypted_path, self.encryption_key)
            
            # Write to temporary file in home directory
            temp_path = os.path.expanduser(f"~/{cache_name}")
            
            import json
            with open(temp_path, 'w') as f:
                json.dump(decrypted_data, f, indent=2)
            
            logger.debug(f"Token decrypted to temporary file: {temp_path}")
            return temp_path
            
        except Exception as e:
            logger.error(f"Failed to decrypt token file: {str(e)}")
            raise IOError(f"Token decryption failed: {str(e)}") from e
    
    def authenticate_spotify(self) -> spotipy.Spotify:
        """Authenticate with Spotify and encrypt the token.
        
        Performs the OAuth flow for Spotify authentication, then encrypts
        the resulting token file for secure storage.
        
        Returns:
            spotipy.Spotify: Authenticated Spotify client.
            
        Raises:
            RuntimeError: If authentication fails.
            IOError: If token encryption fails.
        """
        logger.info("Starting Spotify authentication")
        
        try:
            # Perform authentication
            sp_client = self.spotify_auth.authenticate()
            logger.info("Spotify authentication successful")
            
            # Encrypt the cache file
            cache_path = self.spotify_auth.cache_path
            
            if os.path.exists(cache_path):
                self._encrypt_token_file(cache_path, self.SPOTIFY_CACHE_NAME)
                logger.info("Spotify token encrypted and stored")
            else:
                logger.warning("Spotify cache file not found after authentication")
            
            return sp_client
            
        except Exception as e:
            logger.error(f"Spotify authentication failed: {str(e)}")
            raise RuntimeError(f"Spotify authentication failed: {str(e)}") from e
    
    def authenticate_youtube(self, rate_limiter=None) -> YTMusic:
        """Return a client for the captured YouTube Music session.

        There is no login flow here: the session arrives from the browser
        extension via the capture hub. This only reloads a stored one.

        Raises:
            RuntimeError: If no valid captured session exists yet.
        """
        client = self.get_youtube_client(rate_limiter=rate_limiter)
        if client is None:
            raise RuntimeError(
                "No YouTube Music session captured yet. Install the browser "
                "extension and click Connect YouTube Music."
            )
        return client

    def get_spotify_client(self) -> Optional[spotipy.Spotify]:
        """Get an authenticated Spotify client from cached encrypted credentials.
        
        Attempts to load and decrypt cached Spotify credentials, then creates
        an authenticated client. Returns None if no valid credentials exist.
        
        Returns:
            Optional[spotipy.Spotify]: Authenticated Spotify client, or None if
                no valid cached credentials exist.
        """
        logger.debug("Attempting to load cached Spotify credentials")
        
        try:
            # Check if encrypted token exists
            if not self.is_spotify_authenticated():
                logger.debug("No cached Spotify credentials found")
                return None
            
            # Decrypt token to temporary location
            temp_cache = self._decrypt_to_temp(self.SPOTIFY_CACHE_NAME)
            
            try:
                # Update the authenticator's cache path to use decrypted file.
                # Drop any previously built auth manager so the new path (and a
                # freshly resolved loopback port) is actually picked up.
                original_cache_path = self.spotify_auth.cache_path
                self.spotify_auth.cache_path = temp_cache
                self.spotify_auth._sp_oauth = None

                # Create authenticated client
                sp_client = spotipy.Spotify(auth_manager=self.spotify_auth._get_oauth_manager())
                
                # Test the connection
                sp_client.current_user()
                logger.info("Spotify client created from cached credentials")
                
                return sp_client
                
            finally:
                # Restore original cache path
                self.spotify_auth.cache_path = original_cache_path
                
                # Clean up temporary file
                if os.path.exists(temp_cache):
                    os.remove(temp_cache)
                    logger.debug("Temporary Spotify cache file removed")
            
        except Exception as e:
            logger.error(f"Failed to load cached Spotify credentials: {str(e)}")
            return None
    
    def get_youtube_client(self, rate_limiter=None, verify: bool = True) -> Optional[YTMusic]:
        """Build a YTMusic client from the encrypted captured session.

        Needs no Google credentials and no headers.json. With ``verify`` the
        identity is confirmed with ``get_account_info()`` through the
        ``RateLimiter`` (a signed-out session does not raise on library
        calls). Returns None when nothing is stored or the session is dead.
        """
        loaded = self.youtube_session_store.load()
        if loaded is None:
            logger.debug("No captured YouTube Music session stored")
            return None
        headers, _account = loaded
        try:
            client = YTMusic(auth=headers)
            if verify:
                from ..capture.verify import verify_identity
                result = verify_identity(client, rate_limiter)
                if not result.ok:
                    logger.info(f"Stored YouTube session not usable ({result.code})")
                    return None
            logger.info("YouTube Music client created from captured session")
            return client
        except Exception as e:
            logger.error(f"Failed to load captured YouTube session: {type(e).__name__}")
            return None

    def is_spotify_authenticated(self) -> bool:
        """Check if encrypted Spotify credentials exist.
        
        Returns:
            bool: True if encrypted Spotify credentials exist, False otherwise.
        """
        encrypted_path = self._get_encrypted_path(self.SPOTIFY_CACHE_NAME)
        exists = os.path.exists(encrypted_path)
        logger.debug(f"Spotify authenticated: {exists}")
        return exists
    
    def is_youtube_authenticated(self) -> bool:
        """True if an encrypted captured YouTube Music session exists."""
        return self.youtube_session_store.exists()
    
    def clear_all_tokens(self) -> None:
        """Remove all cached tokens and encrypted files.
        
        Deletes all encrypted token files and clears the authentication cache
        for both Spotify and YouTube Music. This requires users to re-authenticate
        on their next use.
        
        Note:
            This method does not delete the master encryption key.
        """
        logger.info("Clearing all cached tokens")
        
        # Clear Spotify tokens
        try:
            spotify_enc = self._get_encrypted_path(self.SPOTIFY_CACHE_NAME)
            if os.path.exists(spotify_enc):
                os.remove(spotify_enc)
                logger.info(f"Removed encrypted Spotify token: {spotify_enc}")
            
            # Also clear any unencrypted cache
            self.spotify_auth.clear_cache()
            
        except Exception as e:
            logger.warning(f"Failed to clear Spotify tokens: {str(e)}")
        
        # Clear YouTube Music tokens
        try:
            self.youtube_session_store.clear()
            
        except Exception as e:
            logger.warning(f"Failed to clear YouTube Music tokens: {str(e)}")
        
        logger.info("All tokens cleared successfully")
    
    def clear_spotify_token(self) -> None:
        """Remove only Spotify cached tokens.
        
        Deletes the encrypted Spotify token file and clears the authentication cache.
        """
        logger.info("Clearing Spotify token")
        
        try:
            spotify_enc = self._get_encrypted_path(self.SPOTIFY_CACHE_NAME)
            if os.path.exists(spotify_enc):
                os.remove(spotify_enc)
                logger.info("Spotify token cleared")
            
            self.spotify_auth.clear_cache()
            
        except Exception as e:
            logger.error(f"Failed to clear Spotify token: {str(e)}")
            raise IOError(f"Failed to clear Spotify token: {str(e)}") from e
    
    def clear_youtube_token(self) -> None:
        """Remove only YouTube Music cached tokens.
        
        Deletes the encrypted YouTube Music token file and clears the authentication cache.
        """
        logger.info("Clearing YouTube Music token")
        
        try:
            self.youtube_session_store.clear()
            logger.info("YouTube Music session cleared")
            
        except Exception as e:
            logger.error(f"Failed to clear YouTube Music token: {str(e)}")
            raise IOError(f"Failed to clear YouTube Music token: {str(e)}") from e
