"""Google OAuth authentication utilities for Streamlit."""

import json
import logging
from typing import Optional, Dict, Any
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
import requests

logger = logging.getLogger(__name__)

# Google OAuth scopes needed for the app
SCOPES = [
    'openid',
    'https://www.googleapis.com/auth/userinfo.email',
    'https://www.googleapis.com/auth/userinfo.profile',
    'https://www.googleapis.com/auth/drive.file',  # Access to files created by the app
]


def create_flow(client_config: Dict[str, Any], redirect_uri: str) -> Flow:
    """
    Create Google OAuth flow.

    Args:
        client_config: Google OAuth client configuration dict
        redirect_uri: OAuth redirect URI

    Returns:
        Configured Flow object
    """
    flow = Flow.from_client_config(
        client_config=client_config,
        scopes=SCOPES,
        redirect_uri=redirect_uri
    )
    return flow


def get_authorization_url(client_config: Dict[str, Any], redirect_uri: str) -> str:
    """
    Generate Google OAuth authorization URL.

    Args:
        client_config: Google OAuth client configuration dict
        redirect_uri: OAuth redirect URI

    Returns:
        Authorization URL string
    """
    flow = create_flow(client_config, redirect_uri)
    authorization_url, _ = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent'  # Force consent to get refresh token
    )
    return authorization_url


def exchange_code_for_token(
    code: str,
    client_config: Dict[str, Any],
    redirect_uri: str
) -> Credentials:
    """
    Exchange authorization code for access token.

    Args:
        code: Authorization code from OAuth callback
        client_config: Google OAuth client configuration dict
        redirect_uri: OAuth redirect URI

    Returns:
        Google OAuth2 Credentials object
    """
    flow = create_flow(client_config, redirect_uri)
    flow.fetch_token(code=code)
    return flow.credentials


def refresh_credentials(credentials: Credentials) -> Credentials:
    """
    Refresh expired credentials.

    Args:
        credentials: Credentials object to refresh

    Returns:
        Refreshed Credentials object
    """
    if credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
    return credentials


def credentials_to_dict(credentials: Credentials) -> Dict[str, Any]:
    """
    Convert Credentials object to dict for serialization.

    Args:
        credentials: Credentials object

    Returns:
        Dictionary representation of credentials
    """
    return {
        'token': credentials.token,
        'refresh_token': credentials.refresh_token,
        'token_uri': credentials.token_uri,
        'client_id': credentials.client_id,
        'client_secret': credentials.client_secret,
        'scopes': credentials.scopes,
        'expiry': credentials.expiry.isoformat() if credentials.expiry else None
    }


def credentials_from_dict(creds_dict: Dict[str, Any]) -> Credentials:
    """
    Create Credentials object from dict.

    Args:
        creds_dict: Dictionary representation of credentials

    Returns:
        Credentials object
    """
    from datetime import datetime

    # Handle expiry
    expiry = None
    if creds_dict.get('expiry'):
        expiry = datetime.fromisoformat(creds_dict['expiry'])

    return Credentials(
        token=creds_dict['token'],
        refresh_token=creds_dict.get('refresh_token'),
        token_uri=creds_dict.get('token_uri'),
        client_id=creds_dict.get('client_id'),
        client_secret=creds_dict.get('client_secret'),
        scopes=creds_dict.get('scopes'),
        expiry=expiry
    )


def get_user_info(credentials: Credentials) -> Dict[str, Any]:
    """
    Get user info from Google using credentials.

    Args:
        credentials: Valid Google OAuth2 credentials

    Returns:
        Dictionary with user information (email, name, picture, etc.)
    """
    # Refresh if needed
    if credentials.expired:
        credentials = refresh_credentials(credentials)

    # Call Google UserInfo API
    response = requests.get(
        'https://www.googleapis.com/oauth2/v2/userinfo',
        headers={'Authorization': f'Bearer {credentials.token}'}
    )
    response.raise_for_status()

    return response.json()


def revoke_credentials(credentials: Credentials) -> None:
    """
    Revoke OAuth credentials.

    Args:
        credentials: Credentials to revoke
    """
    try:
        requests.post(
            'https://oauth2.googleapis.com/revoke',
            params={'token': credentials.token},
            headers={'content-type': 'application/x-www-form-urlencoded'}
        )
        logger.info("Credentials revoked successfully")
    except Exception as e:
        logger.warning(f"Failed to revoke credentials: {e}")
