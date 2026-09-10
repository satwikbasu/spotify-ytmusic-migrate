"""YouTube Music Authentication Module.

This module provides authentication functionality for YouTube Music API using
ytmusicapi's browser-based authentication (recommended) or OAuth fallback.

RECOMMENDED: Browser Authentication
    - More reliable than OAuth
    - Uses your actual browser session cookies
    - See BROWSER_AUTH_INSTRUCTIONS.md for setup

OAuth Authentication (Fallback)
    - May not work due to YouTube Music's internal API
    - Requires OAuth Client ID type "TVs and Limited Input devices"
    - See BROWSER_AUTH_INSTRUCTIONS.md for why browser auth is better

Authentication Flow:
    1. Check for browser headers file (headers.json or browser.json)
    2. If exists, use browser authentication
    3. Otherwise, fall back to OAuth:
       a. Check for existing token file (~/youtube_oauth.json)
       b. If exists and valid, load cached token
       c. If not, start device code flow
    4. Create YTMusic client with authenticated credentials

Example:
    >>> auth = YouTubeAuthenticator()
    >>> yt = auth.authenticate()
    >>> playlists = yt.get_library_playlists()
"""

from pathlib import Path
from typing import Optional
import logging

from ytmusicapi import YTMusic
from ytmusicapi.auth.oauth import OAuthCredentials, RefreshingToken


logger = logging.getLogger(__name__)


class YouTubeAuthenticator:
    """Handles YouTube Music OAuth 2.0 authentication with device code flow.

    Uses ytmusicapi's native OAuth implementation for TV/Limited Input devices.
    This flow displays a URL and code for the user to enter in their browser.

    Attributes:
        client_id: OAuth 2.0 client ID from Google Cloud Console
        client_secret: OAuth 2.0 client secret from Google Cloud Console
        credentials_path: Path to store OAuth token (default: ~/youtube_oauth.json)

    Raises:
        ValueError: If client_id or client_secret is empty
        RuntimeError: If authentication fails or API test fails
    """

    def __init__(self, client_id: Optional[str] = None, client_secret: Optional[str] = None):
        """Initialize the YouTubeAuthenticator.

        Args:
            client_id: OAuth 2.0 client ID from Google Cloud Console (optional if using browser auth)
            client_secret: OAuth 2.0 client secret from Google Cloud Console (optional if using browser auth)

        Note:
            If both client_id and client_secret are None, only browser authentication will be available.
        """
        self.client_id = client_id
        self.client_secret = client_secret
        
        # Use pathlib for cross-platform path handling
        self.credentials_path = Path.home() / "youtube_oauth.json"
        self.browser_headers_path = Path("headers.json")
        self.browser_alt_path = Path("browser.json")
        
        logger.info(f"YouTubeAuthenticator initialized")
        logger.info(f"OAuth credentials path: {self.credentials_path}")
        logger.info(f"Browser headers path: {self.browser_headers_path}")

    def authenticate(self) -> YTMusic:
        """Authenticate with YouTube Music using browser headers or OAuth.

        Authentication priority:
        1. Browser authentication (headers.json or browser.json) - RECOMMENDED
        2. OAuth authentication (cached token or device code flow) - FALLBACK

        Browser Authentication:
            - Most reliable method
            - Uses actual browser session cookies
            - See BROWSER_AUTH_INSTRUCTIONS.md for setup

        OAuth Authentication:
            - May not work due to YouTube Music's internal API
            - Falls back to device code flow if no cached token

        Returns:
            YTMusic: Authenticated YouTube Music API client

        Raises:
            RuntimeError: If authentication fails or API test fails
        """
        # Try browser authentication first (recommended)
        if self.browser_headers_path.exists():
            logger.info(f"Found browser headers file: {self.browser_headers_path}")
            return self._authenticate_browser(self.browser_headers_path)
        elif self.browser_alt_path.exists():
            logger.info(f"Found browser headers file: {self.browser_alt_path}")
            return self._authenticate_browser(self.browser_alt_path)
        
        # Fall back to OAuth
        logger.info("No browser headers found, trying OAuth authentication")
        if not self.client_id or not self.client_secret:
            raise RuntimeError(
                "No browser authentication file found and OAuth credentials not provided.\n"
                "Please run 'ytmusicapi browser' to set up browser authentication.\n"
                "See BROWSER_AUTH_INSTRUCTIONS.md for details."
            )
        
        return self._authenticate_oauth()

    def _authenticate_browser(self, headers_path: Path) -> YTMusic:
        """Authenticate using browser headers.

        Args:
            headers_path: Path to browser headers JSON file

        Returns:
            YTMusic: Authenticated YouTube Music API client

        Raises:
            RuntimeError: If authentication fails
        """
        try:
            print(f"Loading YouTube Music credentials from {headers_path}")
            print("Using browser authentication (recommended method)")
            
            # Create YTMusic client with browser headers
            yt = YTMusic(str(headers_path))
            logger.info("YTMusic client created with browser authentication")
            
            # Verify the session is genuinely signed in.
            #
            # get_library_playlists() is not a usable check: a signed-out session
            # returns an empty list rather than raising, so an expired cookie was
            # indistinguishable from an account with no playlists. get_account_info()
            # needs a real identity and fails without one.
            print("Testing YouTube Music API connection...")
            try:
                account = yt.get_account_info()
            except Exception as e:
                logger.warning(f"Account check failed: {e}")
                raise RuntimeError(
                    "YouTube Music rejected these credentials - the session is not "
                    "signed in.\n"
                    "Your cookies have most likely expired. Run 'ytmusicapi browser' "
                    "to capture a fresh headers.json while logged in to "
                    "music.youtube.com.\n"
                    "See BROWSER_AUTH_INSTRUCTIONS.md for details."
                ) from e

            if not account:
                raise RuntimeError(
                    "YouTube Music returned no account for these credentials - the "
                    "session is not signed in. Run 'ytmusicapi browser' to refresh."
                )

            account_name = account.get("accountName") if isinstance(account, dict) else None
            print(f"✅ Signed in to YouTube Music as {account_name or 'your account'}")
            logger.info("Account check successful")
            
            return yt
            
        except Exception as e:
            logger.error(f"Browser authentication failed: {e}")
            raise RuntimeError(
                f"Failed to authenticate with browser headers from {headers_path}\n"
                f"Error: {e}\n"
                "Your session may have expired. Run 'ytmusicapi browser' to refresh.\n"
                "See BROWSER_AUTH_INSTRUCTIONS.md for details."
            ) from e

    def _authenticate_oauth(self) -> YTMusic:
        """Refuse the OAuth path, which cannot work against YouTube Music.

        The device-code flow itself succeeds and returns a valid token with a
        refresh token, and ytmusicapi applies it correctly. Every authenticated
        call then returns HTTP 400 "Request contains an invalid argument",
        because YouTube Music's internal API does not accept tokens issued to
        custom Google Cloud clients - regardless of the client type. Browser
        cookies are the only authentication it honours.

        Raises:
            RuntimeError: Always, explaining how to authenticate instead.
        """
        raise RuntimeError(
            "OAuth cannot authenticate against YouTube Music.\n"
            "The token is issued correctly, but every API call is rejected with "
            "HTTP 400 because YouTube Music's internal API ignores tokens from "
            "custom Google Cloud clients.\n"
            "Use browser authentication instead: run 'ytmusicapi browser' while "
            "signed in to music.youtube.com to create headers.json.\n"
            "See BROWSER_AUTH_INSTRUCTIONS.md for details."
        )

    def _authenticate_oauth_unused(self) -> YTMusic:
        """Retained for reference only; see _authenticate_oauth above."""
        try:
            # Create OAuth credentials object
            credentials = OAuthCredentials(
                client_id=self.client_id,
                client_secret=self.client_secret
            )
            logger.info("Created OAuthCredentials object")

            # Check for existing token file
            if self.credentials_path.exists():
                logger.info(f"Found existing token file: {self.credentials_path}")
                print(f"Loading cached YouTube Music credentials from {self.credentials_path}")
                
                try:
                    # Load and refresh existing token
                    # Note: parameter is file_path not filepath
                    token = RefreshingToken.from_json(
                        file_path=str(self.credentials_path),
                        client_id=self.client_id,
                        client_secret=self.client_secret
                    )
                    logger.info("Successfully loaded existing token")
                    
                    # Create YTMusic client with cached token
                    # IMPORTANT: Must pass BOTH auth (file path) AND oauth_credentials (object)
                    yt = YTMusic(auth=str(self.credentials_path), oauth_credentials=credentials)
                    
                    # Test the connection
                    yt.get_library_playlists(limit=1)
                    print("YouTube Music authentication successful (using cached credentials)")
                    logger.info("Authentication successful with cached credentials")
                    return yt
                    
                except Exception as e:
                    logger.warning(f"Cached credentials invalid: {e}")
                    print(f"Cached credentials invalid: {e}")
                    print("Starting new authentication flow...")
                    # Fall through to new authentication

            # No valid cached token - start device code flow
            print("\n" + "="*70)
            print("YouTube Music Authentication - Device Code Flow")
            print("="*70)
            print("\nIMPORTANT: This requires OAuth Client ID type 'TVs and Limited Input devices'")
            print("If you see errors, verify your OAuth client type in Google Cloud Console.\n")
            logger.info("Starting device code flow authentication")

            # Prompt for token with device code flow
            # This will:
            # 1. Display a URL and code
            # 2. Open browser automatically (if possible)
            # 3. Wait for user to authorize
            # 4. Save token to file automatically
            try:
                token = RefreshingToken.prompt_for_token(
                    credentials=credentials,
                    open_browser=True,
                    to_file=str(self.credentials_path)
                )
                logger.info(f"Device code flow completed, token saved to {self.credentials_path}")
                print(f"\nCredentials saved to: {self.credentials_path}")
            except TypeError as e:
                error_msg = str(e)
                if "unexpected keyword argument 'error'" in error_msg:
                    logger.error(f"OAuth server returned an error: {e}")
                    raise RuntimeError(
                        "YouTube OAuth configuration error.\n\n"
                        "This usually means your OAuth Client ID type is incorrect.\n\n"
                        "Required: 'TVs and Limited Input devices'\n"
                        "NOT: 'Desktop app' or 'Web application'\n\n"
                        "Steps to fix:\n"
                        "1. Go to: https://console.cloud.google.com/apis/credentials\n"
                        "2. Delete your current OAuth Client ID\n"
                        "3. Create NEW OAuth Client ID\n"
                        "4. Select type: 'TVs and Limited Input devices'\n"
                        "5. Update your .env file with the new credentials\n"
                        "6. Run the app again"
                    ) from e
                raise

            # Create YTMusic client with new token
            # IMPORTANT: Must pass BOTH auth (file path) AND oauth_credentials (object)
            yt = YTMusic(auth=str(self.credentials_path), oauth_credentials=credentials)
            
            # Test the connection
            print("\nTesting YouTube Music API connection...")
            yt.get_library_playlists(limit=1)
            
            print("\n" + "="*70)
            print("YouTube Music authentication successful!")
            print("="*70 + "\n")
            logger.info("Authentication successful with new credentials")
            
            return yt
            
        except ValueError as e:
            logger.error(f"Invalid credentials: {e}")
            raise ValueError(
                f"Invalid client credentials: {e}\n"
                "Please verify YOUTUBE_CLIENT_ID and YOUTUBE_CLIENT_SECRET in .env file.\n"
                "Ensure you're using OAuth Client ID type 'TVs and Limited Input devices'."
            ) from e
        except RuntimeError as e:
            logger.error(f"Authentication runtime error: {e}", exc_info=True)
            raise RuntimeError(f"YouTube Music authentication failed: {e}") from e
        except Exception as e:
            logger.error(f"Unexpected authentication error: {e}", exc_info=True)
            # Get more specific error message
            error_str = str(e).lower()
            if "quota" in error_str or "rate" in error_str:
                raise RuntimeError(
                    f"YouTube API quota exceeded or rate limit reached: {e}\n"
                    "Please wait a few minutes and try again."
                ) from e
            elif "permission" in error_str or "access" in error_str:
                raise RuntimeError(
                    f"Permission denied: {e}\n"
                    "Please ensure your Google account is added as a test user in OAuth consent screen."
                ) from e
            else:
                raise RuntimeError(
                    f"Unexpected error during YouTube Music authentication: {e}\n"
                    "Please ensure:\n"
                    "1. OAuth Client ID type is 'TVs and Limited Input devices'\n"
                    "2. YouTube Data API v3 is enabled in Google Cloud Console\n"
                    "3. Your Google account is added as a test user in OAuth consent screen"
                ) from e
    
    def is_authenticated(self) -> bool:
        """Check if valid YouTube Music credentials exist.

        Returns:
            bool: True if token file exists and is valid, False otherwise
        """
        if not self.credentials_path.exists():
            return False
            
        try:
            # Try to load token - if this succeeds, credentials are valid
            # Note: parameter is file_path not filepath
            credentials = OAuthCredentials(
                client_id=self.client_id,
                client_secret=self.client_secret
            )
            RefreshingToken.from_json(
                file_path=str(self.credentials_path),
                client_id=self.client_id,
                client_secret=self.client_secret
            )
            return True
        except Exception:
            return False

    def clear_cache(self) -> None:
        """Remove cached YouTube Music credentials from disk.

        Deletes the token file, requiring re-authentication on next use.
        """
        try:
            if self.credentials_path.exists():
                self.credentials_path.unlink()
                print(f"YouTube Music cache cleared: {self.credentials_path}")
                logger.info(f"Cleared credentials cache: {self.credentials_path}")
            else:
                print("No YouTube Music cache found to clear")
        except OSError as e:
            logger.warning(f"Failed to clear cache: {e}")
            print(f"Warning: Failed to clear YouTube Music cache: {e}")
