"""Secure storage for credentials using encrypted cookies."""

import json
import logging
from typing import Any, Dict, Optional

import extra_streamlit_components as stx
import streamlit as st
from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)


class SecureCredentialStorage:
    """Handles secure storage of credentials in encrypted cookies."""

    def __init__(self, cookie_name: str = "auth_credentials", expiry_days: int = 30):
        """
        Initialize secure storage.

        Args:
            cookie_name: Name of the cookie to store credentials
            expiry_days: Number of days until cookie expires
        """
        self.cookie_name = cookie_name
        self.expiry_days = expiry_days
        self._cookie_manager = None
        self._cipher = None

    def _get_cookie_manager(self) -> stx.CookieManager:
        """Get or create cookie manager instance."""
        if self._cookie_manager is None:
            self._cookie_manager = stx.CookieManager()
        return self._cookie_manager

    def _get_cipher(self) -> Fernet:
        """Get or create cipher for encryption/decryption."""
        if self._cipher is None:
            # Get encryption key from secrets
            try:
                key = st.secrets.get("cookie_encryption_key")
                if not key:
                    # Generate temporary key for development
                    logger.warning("No cookie_encryption_key in secrets, using temporary key")
                    key = Fernet.generate_key().decode()

                # Ensure key is bytes
                if isinstance(key, str):
                    key = key.encode()

                self._cipher = Fernet(key)
            except Exception as e:
                logger.error(f"Failed to initialize cipher: {e}")
                raise

        return self._cipher

    def is_ready(self) -> bool:
        """
        Check if cookie manager is ready to use.

        Returns:
            True if ready, False otherwise
        """
        try:
            cookie_manager = self._get_cookie_manager()
            # Check if cookie manager has initialized
            return cookie_manager is not None and hasattr(cookie_manager, 'get_all')
        except Exception as e:
            logger.debug(f"Cookie manager not ready: {e}")
            return False

    def save_credentials(self, credentials: Dict[str, Any]) -> bool:
        """
        Save credentials to encrypted cookie.

        Args:
            credentials: Credentials dictionary to save

        Returns:
            True if successful, False otherwise
        """
        try:
            if not self.is_ready():
                logger.warning("Cookie manager not ready, cannot save credentials")
                return False

            # Convert to JSON
            credentials_json = json.dumps(credentials)

            # Encrypt
            cipher = self._get_cipher()
            encrypted = cipher.encrypt(credentials_json.encode())

            # Store in cookie
            cookie_manager = self._get_cookie_manager()
            cookie_manager.set(
                self.cookie_name,
                encrypted.decode(),
                expires_at=None,  # Uses default expiry
                max_age=self.expiry_days * 24 * 60 * 60  # Convert days to seconds
            )

            logger.info("Credentials saved to encrypted cookie")
            return True

        except Exception as e:
            logger.error(f"Failed to save credentials to cookie: {e}")
            return False

    def load_credentials(self) -> Optional[Dict[str, Any]]:
        """
        Load credentials from encrypted cookie.

        Returns:
            Credentials dictionary if found and valid, None otherwise
        """
        try:
            if not self.is_ready():
                logger.debug("Cookie manager not ready, cannot load credentials")
                return None

            # Get cookie
            cookie_manager = self._get_cookie_manager()
            encrypted_data = cookie_manager.get(self.cookie_name)

            if not encrypted_data:
                logger.debug("No credentials cookie found")
                return None

            # Decrypt
            cipher = self._get_cipher()
            decrypted = cipher.decrypt(encrypted_data.encode())

            # Parse JSON
            credentials = json.loads(decrypted.decode())

            logger.info("Credentials loaded from cookie")
            return credentials

        except Exception as e:
            logger.warning(f"Failed to load credentials from cookie: {e}")
            return None

    def clear_credentials(self) -> None:
        """Clear credentials cookie."""
        try:
            if not self.is_ready():
                logger.warning("Cookie manager not ready, cannot clear credentials")
                return

            cookie_manager = self._get_cookie_manager()
            cookie_manager.delete(self.cookie_name)
            logger.info("Credentials cookie cleared")

        except Exception as e:
            logger.error(f"Failed to clear credentials cookie: {e}")


# Global instance
_storage: Optional[SecureCredentialStorage] = None


def get_secure_storage() -> SecureCredentialStorage:
    """
    Get global secure storage instance.

    Returns:
        SecureCredentialStorage instance
    """
    global _storage
    if _storage is None:
        _storage = SecureCredentialStorage()
    return _storage
