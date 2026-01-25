"""
Intuit OAuth token management with automatic refresh.
Provides transparent token handling for QuickBooks Payments API.
"""

import os
import time
import base64
import json
from dataclasses import dataclass
from typing import Optional

import keychain_storage

# Token refresh happens 5 minutes before expiry
REFRESH_BUFFER_SECONDS = 300

# Intuit OAuth endpoint
OAUTH_TOKEN_URL = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"

# Path to embedded initial tokens (created at build time)
EMBEDDED_TOKENS_PATH = os.path.join(os.path.dirname(__file__), "Resources", "initial_tokens.enc")


@dataclass
class IntuitTokens:
    """Container for Intuit OAuth tokens."""
    access_token: str
    refresh_token: str
    expires_at: float  # Unix timestamp when access token expires
    refresh_expires_at: float  # Unix timestamp when refresh token expires


class RefreshTokenExpiredError(Exception):
    """Raised when the refresh token has expired and cannot be renewed."""
    pass


class IntuitTokenManager:
    """
    Manages Intuit OAuth tokens with automatic refresh.

    Tokens are stored securely in iOS Keychain. On first launch,
    tokens are loaded from an encrypted bundle embedded at build time.
    """

    def __init__(self):
        self.client_id = os.environ.get('INTUIT_CLIENT_ID', '')
        self.client_secret = os.environ.get('INTUIT_CLIENT_SECRET', '')
        self._cached_tokens: Optional[IntuitTokens] = None

    def get_valid_access_token(self) -> Optional[str]:
        """
        Get a valid access token, refreshing if necessary.

        Returns:
            Access token string, or None if tokens are unavailable/expired
        """
        tokens = self._load_tokens()

        if tokens is None:
            return None

        # Check if refresh token has expired
        if time.time() >= tokens.refresh_expires_at:
            # Cannot refresh - refresh token expired
            return None

        # Check if access token needs refresh
        if self._is_refresh_needed(tokens):
            try:
                tokens = self._refresh_access_token(tokens.refresh_token)
                self._save_tokens(tokens)
            except Exception as e:
                print(f"Token refresh failed: {e}")
                # Return existing token if refresh fails but it's not yet expired
                if time.time() < tokens.expires_at:
                    return tokens.access_token
                return None

        return tokens.access_token

    def _load_tokens(self) -> Optional[IntuitTokens]:
        """
        Load tokens from Keychain, falling back to embedded bundle.

        Returns:
            IntuitTokens if available, None otherwise
        """
        # Return cached tokens if available
        if self._cached_tokens is not None:
            return self._cached_tokens

        # Try to load from Keychain
        stored = keychain_storage.load_from_keychain()
        if stored:
            self._cached_tokens = IntuitTokens(
                access_token=stored['access_token'],
                refresh_token=stored['refresh_token'],
                expires_at=stored['expires_at'],
                refresh_expires_at=stored['refresh_expires_at']
            )
            return self._cached_tokens

        # First launch - try to load from embedded bundle
        embedded = self._load_embedded_tokens()
        if embedded:
            self._save_tokens(embedded)
            return embedded

        # No tokens available - check environment variables as last resort
        env_access = os.environ.get('INTUIT_ACCESS_TOKEN', '')
        env_refresh = os.environ.get('INTUIT_REFRESH_TOKEN', '')
        if env_access and env_refresh:
            tokens = IntuitTokens(
                access_token=env_access,
                refresh_token=env_refresh,
                expires_at=time.time() + 3600,  # Assume 1 hour validity
                refresh_expires_at=time.time() + (100 * 24 * 60 * 60)  # 100 days
            )
            self._save_tokens(tokens)
            return tokens

        return None

    def _load_embedded_tokens(self) -> Optional[IntuitTokens]:
        """
        Load and decrypt tokens from embedded bundle.

        Returns:
            IntuitTokens if successful, None otherwise
        """
        if not os.path.exists(EMBEDDED_TOKENS_PATH):
            return None

        try:
            from cryptography.fernet import Fernet

            # Encryption key from environment (set at build time)
            key = os.environ.get('TOKEN_ENCRYPTION_KEY', '')
            if not key:
                return None

            with open(EMBEDDED_TOKENS_PATH, 'rb') as f:
                encrypted = f.read()

            fernet = Fernet(key.encode() if isinstance(key, str) else key)
            decrypted = fernet.decrypt(encrypted)
            data = json.loads(decrypted.decode('utf-8'))

            return IntuitTokens(
                access_token=data['access_token'],
                refresh_token=data['refresh_token'],
                expires_at=data.get('expires_at', time.time() + 3600),
                refresh_expires_at=data.get('refresh_expires_at', time.time() + (100 * 24 * 60 * 60))
            )
        except Exception as e:
            print(f"Failed to load embedded tokens: {e}")
            return None

    def _refresh_access_token(self, refresh_token: str) -> IntuitTokens:
        """
        Refresh the access token using Intuit OAuth API.

        Args:
            refresh_token: Current refresh token

        Returns:
            New IntuitTokens with refreshed values

        Raises:
            RefreshTokenExpiredError: If refresh token is invalid/expired
            Exception: On network or API errors
        """
        import requests

        # Create Basic auth header
        credentials = f"{self.client_id}:{self.client_secret}"
        auth_header = base64.b64encode(credentials.encode()).decode()

        response = requests.post(
            OAUTH_TOKEN_URL,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Authorization": f"Basic {auth_header}"
            },
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token
            },
            timeout=30
        )

        if response.status_code == 400:
            error_data = response.json()
            if error_data.get('error') == 'invalid_grant':
                raise RefreshTokenExpiredError("Refresh token has expired")
            raise Exception(f"Token refresh failed: {error_data}")

        response.raise_for_status()
        data = response.json()

        now = time.time()
        return IntuitTokens(
            access_token=data['access_token'],
            refresh_token=data.get('refresh_token', refresh_token),
            expires_at=now + data.get('expires_in', 3600),
            refresh_expires_at=now + data.get('x_refresh_token_expires_in', 100 * 24 * 60 * 60)
        )

    def _save_tokens(self, tokens: IntuitTokens) -> None:
        """Save tokens to Keychain."""
        data = {
            'access_token': tokens.access_token,
            'refresh_token': tokens.refresh_token,
            'expires_at': tokens.expires_at,
            'refresh_expires_at': tokens.refresh_expires_at
        }
        keychain_storage.save_to_keychain(data)
        self._cached_tokens = tokens

    def _is_refresh_needed(self, tokens: IntuitTokens) -> bool:
        """Check if token refresh is needed (expiring within buffer time)."""
        return time.time() >= (tokens.expires_at - REFRESH_BUFFER_SECONDS)

    def clear_tokens(self) -> None:
        """Clear all stored tokens (for logout/reset)."""
        keychain_storage.delete_from_keychain()
        self._cached_tokens = None


# Global singleton instance
_token_manager: Optional[IntuitTokenManager] = None


def get_token_manager() -> IntuitTokenManager:
    """Get or create the global token manager instance."""
    global _token_manager
    if _token_manager is None:
        _token_manager = IntuitTokenManager()
    return _token_manager
