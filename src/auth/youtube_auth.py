"""YouTube Music OAuth 2.0 Authentication Module.

This module provides authentication functionality for the YouTube Music API using
Google's OAuth 2.0 flow with the ytmusicapi library.
"""

import os
import json
from typing import Optional, Dict, Any
from datetime import datetime, timedelta, timezone

from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from ytmusicapi import YTMusic
import requests.exceptions


class YouTubeAuthenticator:
    """Handles YouTube Music OAuth 2.0 authentication and token management.
    
    This class manages the OAuth 2.0 flow for YouTube Music API authentication,
    including token storage, validation, and automatic refresh.
    
    The authentication process:
    1. Creates OAuth 2.0 flow with client credentials
    2. Launches local server to handle OAuth callback
    3. User authorizes in browser
    4. Receives authorization code and exchanges for tokens
    5. Stores tokens in JSON file for future use
    
    Attributes:
        client_id (str): Google OAuth client ID.
        client_secret (str): Google OAuth client secret.
        scope (str): YouTube API scope for full access.
        credentials_path (str): Path to the token cache file.
        oauth_port (int): Port for local OAuth callback server.
    """
    
    REQUIRED_SCOPE = "https://www.googleapis.com/auth/youtube.force-ssl"
    OAUTH_PORT = 8080
    CREDENTIALS_FILENAME = "youtube_oauth.json"
    
    def __init__(self, client_id: str, client_secret: str):
        """Initialize the YouTube Music authenticator.
        
        Args:
            client_id (str): Google OAuth client ID from Google Cloud Console.
            client_secret (str): Google OAuth client secret from Google Cloud Console.
            
        Raises:
            ValueError: If client_id or client_secret is empty or None.
        """
        if not client_id or not client_secret:
            raise ValueError("Client ID and Client Secret are required")
        
        self.client_id = client_id
        self.client_secret = client_secret
        self.scope = self.REQUIRED_SCOPE
        self.credentials_path = os.path.expanduser(f"~/{self.CREDENTIALS_FILENAME}")
        self.oauth_port = self.OAUTH_PORT
    
    def _create_client_config(self) -> Dict[str, Any]:
        """Create the OAuth client configuration dictionary.
        
        Returns:
            Dict[str, Any]: Client configuration in the format required by InstalledAppFlow.
        """
        return {
            "installed": {
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "redirect_uris": [
                    f"http://localhost:{self.oauth_port}/",
                    "urn:ietf:wg:oauth:2.0:oob"
                ],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs"
            }
        }
    
    def _credentials_to_dict(self, credentials: Credentials) -> Dict[str, Any]:
        """Convert Google OAuth credentials to ytmusicapi format.
        
        Args:
            credentials (Credentials): Google OAuth2 credentials object.
            
        Returns:
            Dict[str, Any]: Credentials dictionary in ytmusicapi format.
        """
        creds_dict = {
            "access_token": credentials.token,
            "refresh_token": credentials.refresh_token,
            "token_uri": credentials.token_uri,
            "client_id": credentials.client_id,
            "client_secret": credentials.client_secret,
            "scopes": credentials.scopes,
        }
        
        # Add expiry timestamp if available
        if credentials.expiry:
            creds_dict["expiry"] = credentials.expiry.isoformat()
        
        return creds_dict
    
    def _load_credentials(self) -> Optional[Dict[str, Any]]:
        """Load credentials from the cache file.
        
        Returns:
            Optional[Dict[str, Any]]: Credentials dictionary if file exists and is valid,
                None otherwise.
        """
        try:
            if not os.path.exists(self.credentials_path):
                return None
            
            with open(self.credentials_path, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"Warning: Failed to load credentials: {str(e)}")
            return None
    
    def _save_credentials(self, creds_dict: Dict[str, Any]) -> None:
        """Save credentials to the cache file.
        
        Args:
            creds_dict (Dict[str, Any]): Credentials dictionary to save.
            
        Raises:
            IOError: If unable to write to the credentials file.
        """
        try:
            with open(self.credentials_path, 'w') as f:
                json.dump(creds_dict, f, indent=2)
            print(f"Credentials saved to: {self.credentials_path}")
        except IOError as e:
            raise IOError(f"Failed to save credentials: {str(e)}") from e
    
    def _refresh_token_if_needed(self, creds_dict: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Refresh the access token if it's expired or about to expire.
        
        Args:
            creds_dict (Dict[str, Any]): Current credentials dictionary.
            
        Returns:
            Optional[Dict[str, Any]]: Updated credentials dictionary if refresh was successful,
                None if refresh failed or wasn't needed.
        """
        try:
            # Check if token has expiry information
            if "expiry" not in creds_dict:
                return None
            
            # Parse expiry timestamp
            expiry = datetime.fromisoformat(creds_dict["expiry"])
            
            # Refresh if token expires within 5 minutes
            if expiry > datetime.now(timezone.utc) + timedelta(minutes=5):
                return None  # Token is still valid
            
            print("Access token expired or expiring soon. Refreshing...")
            
            # Create credentials object from dict
            credentials = Credentials(
                token=creds_dict.get("access_token"),
                refresh_token=creds_dict.get("refresh_token"),
                token_uri=creds_dict.get("token_uri"),
                client_id=creds_dict.get("client_id"),
                client_secret=creds_dict.get("client_secret"),
                scopes=creds_dict.get("scopes")
            )
            
            # Refresh the token
            credentials.refresh(Request())
            
            # Convert back to dictionary and save
            updated_creds = self._credentials_to_dict(credentials)
            self._save_credentials(updated_creds)
            
            print("Access token refreshed successfully")
            return updated_creds
            
        except Exception as e:
            print(f"Warning: Failed to refresh token: {str(e)}")
            return None
    
    def authenticate(self) -> YTMusic:
        """Authenticate with YouTube Music and return an authenticated client.
        
        This method implements the full OAuth 2.0 flow:
        
        1. Check for cached credentials and refresh if needed
        2. If no valid credentials, initiate OAuth flow:
           a. Create OAuth client configuration
           b. Initialize InstalledAppFlow with client config and scopes
           c. Launch local web server on port 8080
           d. Open browser for user authorization
           e. Receive authorization code via callback
           f. Exchange code for access and refresh tokens
        3. Convert credentials to ytmusicapi format
        4. Save credentials to JSON file for future use
        5. Create and return authenticated YTMusic client
        
        Returns:
            YTMusic: An authenticated YouTube Music API client instance.
            
        Raises:
            RuntimeError: If user denies authorization or OAuth flow fails.
            requests.exceptions.RequestException: If network errors occur.
            ValueError: If credentials are invalid or malformed.
        """
        try:
            # Step 1: Check for existing credentials
            creds_dict = self._load_credentials()
            
            if creds_dict:
                # Try to refresh token if needed
                refreshed_creds = self._refresh_token_if_needed(creds_dict)
                if refreshed_creds:
                    creds_dict = refreshed_creds
                
                # Attempt to create YTMusic client with cached credentials
                try:
                    yt = YTMusic(auth=self.credentials_path)
                    # Test the connection with a simple API call
                    yt.get_account_info()
                    print("Using cached YouTube Music credentials")
                    return yt
                except Exception as e:
                    print(f"Cached credentials invalid: {str(e)}. Re-authenticating...")
                    # Fall through to new OAuth flow
            
            # Step 2: No valid cached credentials - initiate OAuth flow
            print("Starting YouTube Music OAuth flow...")
            print(f"A browser window will open for authorization.")
            
            # Create client configuration
            client_config = self._create_client_config()
            
            # Step 3: Initialize OAuth flow
            flow = InstalledAppFlow.from_client_config(
                client_config=client_config,
                scopes=[self.scope]
            )
            
            # Step 4: Run local server to handle OAuth callback
            # This will:
            # - Start a local web server on localhost:8080
            # - Open the user's browser to Google's authorization page
            # - Wait for the user to authorize the application
            # - Receive the authorization code via HTTP callback
            # - Exchange the code for access and refresh tokens
            try:
                credentials = flow.run_local_server(
                    port=self.oauth_port,
                    success_message="Authentication successful! You can close this window.",
                    open_browser=True
                )
            except Exception as e:
                if "access_denied" in str(e).lower():
                    raise RuntimeError(
                        "User denied authorization. Please grant access to continue."
                    ) from e
                raise RuntimeError(
                    f"OAuth flow failed: {str(e)}. Please check your network connection "
                    f"and ensure port {self.oauth_port} is available."
                ) from e
            
            if not credentials:
                raise RuntimeError("Failed to obtain credentials from OAuth flow")
            
            # Step 5: Convert credentials to ytmusicapi format
            creds_dict = self._credentials_to_dict(credentials)
            
            # Step 6: Save credentials to file
            self._save_credentials(creds_dict)
            
            # Step 7: Create and return authenticated YTMusic client
            yt = YTMusic(auth=self.credentials_path)
            
            # Verify authentication with a test API call
            try:
                yt.get_account_info()
                print("YouTube Music authentication successful!")
            except Exception as e:
                raise RuntimeError(
                    f"Authentication succeeded but API test failed: {str(e)}"
                ) from e
            
            return yt
            
        except requests.exceptions.RequestException as e:
            raise requests.exceptions.RequestException(
                f"Network error during YouTube Music authentication: {str(e)}"
            ) from e
        except ValueError as e:
            raise ValueError(
                f"Invalid credentials or configuration: {str(e)}"
            ) from e
        except RuntimeError:
            # Re-raise RuntimeError as-is
            raise
        except Exception as e:
            raise RuntimeError(
                f"Unexpected error during YouTube Music authentication: {str(e)}"
            ) from e
    
    def is_authenticated(self) -> bool:
        """Check if valid YouTube Music credentials exist.
        
        This method verifies:
        1. Credentials file exists
        2. File contains valid JSON
        3. Required fields are present
        4. Token is not expired (if expiry field exists)
        
        Returns:
            bool: True if valid credentials exist, False otherwise.
        """
        try:
            creds_dict = self._load_credentials()
            
            if not creds_dict:
                return False
            
            # Check for required fields
            required_fields = ["access_token", "refresh_token", "token_uri", 
                             "client_id", "client_secret"]
            if not all(field in creds_dict for field in required_fields):
                return False
            
            # Check token expiry if available
            if "expiry" in creds_dict:
                try:
                    expiry = datetime.fromisoformat(creds_dict["expiry"])
                    # Consider expired if less than 1 minute remaining
                    if expiry <= datetime.now(timezone.utc) + timedelta(minutes=1):
                        # Token expired, but we have refresh token
                        # Authentication method will handle refresh
                        return True  # Refresh token allows re-authentication
                except (ValueError, TypeError):
                    pass  # Invalid expiry format, but other fields may be valid
            
            return True
            
        except Exception:
            return False
    
    def clear_cache(self) -> None:
        """Remove cached YouTube Music credentials from disk.
        
        This method deletes the credentials file, requiring the user to
        re-authenticate on the next authentication attempt.
        
        Note:
            This method does not raise an error if the credentials file doesn't exist.
        """
        try:
            if os.path.exists(self.credentials_path):
                os.remove(self.credentials_path)
                print(f"YouTube Music cache cleared: {self.credentials_path}")
            else:
                print("No YouTube Music cache found to clear")
        except OSError as e:
            print(f"Warning: Failed to clear YouTube Music cache: {str(e)}")
