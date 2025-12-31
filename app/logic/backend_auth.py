"""
Authentication utility for Invite-ellie-backend API calls.
Uses EMAIL and PASS environment variables to automatically authenticate
and get bearer token for API calls.
"""
import os
import requests
import time
import logging
from typing import Optional, Dict

logger = logging.getLogger(__name__)

# Cache for bearer token
_token_cache: Optional[Dict[str, any]] = None


def get_backend_bearer_token() -> Optional[str]:
    """
    Get bearer token for Invite-ellie-backend API calls.
    Uses EMAIL and PASS environment variables to login and get token.
    Caches the token until it expires.
    
    Returns:
        Bearer token string or None if authentication fails
    """
    global _token_cache
    
    # Check if we have a valid cached token
    if _token_cache:
        expires_at = _token_cache.get('expires_at', 0)
        if time.time() < expires_at:
            return _token_cache.get('token')
        else:
            # Token expired, clear cache
            _token_cache = None
    
    # Get credentials from environment
    email = os.environ.get('EMAIL')
    password = os.environ.get('PASS')
    
    if not email or not password:
        logger.warning('[BackendAuth] EMAIL or PASS environment variables not set, cannot authenticate')
        return None
    
    # Get API base URL
    api_base_url = os.environ.get('INVITE_ELLIE_BACKEND_API_URL', 'http://localhost:8000')
    
    # Login endpoint (backend uses /api/accounts/login/)
    login_url = f'{api_base_url}/api/accounts/login/'
    
    try:
        logger.info(f'[BackendAuth] Attempting to login with email: {email}')
        response = requests.post(
            login_url,
            json={
                'email': email,
                'password': password,
            },
            headers={
                'Content-Type': 'application/json',
            },
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            access_token = data.get('access_token')
            expires_in = data.get('expires_in', 3600)  # Default to 1 hour if not provided
            
            if access_token:
                # Cache the token (expire 5 minutes before actual expiration for safety)
                expires_at = time.time() + expires_in - 300
                _token_cache = {
                    'token': access_token,
                    'expires_at': expires_at,
                }
                logger.info(f'[BackendAuth] ✓ Successfully authenticated, token expires in {expires_in}s')
                return access_token
            else:
                logger.error('[BackendAuth] Login response missing access_token')
                return None
        else:
            logger.error(f'[BackendAuth] Login failed with status {response.status_code}: {response.text}')
            return None
            
    except requests.exceptions.RequestException as e:
        logger.error(f'[BackendAuth] Error during login: {e}')
        return None
    except Exception as e:
        logger.error(f'[BackendAuth] Unexpected error during login: {e}')
        return None


def get_backend_api_headers(additional_headers: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """
    Get headers for Invite-ellie-backend API calls with bearer token.
    
    Args:
        additional_headers: Optional additional headers to include
        
    Returns:
        Dictionary of headers including Authorization with bearer token
    """
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
    }
    
    # Get bearer token
    token = get_backend_bearer_token()
    if token:
        headers['Authorization'] = f'Bearer {token}'
    else:
        logger.warning('[BackendAuth] No bearer token available, API call may fail')
    
    # Add any additional headers
    if additional_headers:
        headers.update(additional_headers)
    
    return headers


def clear_token_cache():
    """Clear the cached token (useful for testing or forced re-authentication)"""
    global _token_cache
    _token_cache = None
    logger.info('[BackendAuth] Token cache cleared')

