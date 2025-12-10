import jwt
import requests
import logging
from django.conf import settings
from app.models import User

logger = logging.getLogger(__name__)


def get_auth_token_for_user(user):
    """Legacy function - kept for backward compatibility during migration"""
    return jwt.encode({'id': str(user.id)}, settings.SECRET_KEY, algorithm='HS256')


def get_backend_user_from_token(token):
    """
    Validate JWT token with Invite-ellie-backend API and return user ID.
    
    Args:
        token: JWT access token from Invite-ellie-backend
        
    Returns:
        dict with 'user_id' (UUID) and 'email' if valid, None otherwise
    """
    if not token:
        return None
    
    backend_api_url = getattr(settings, 'INVITE_ELLIE_BACKEND_API_URL', 'https://api.stage.inviteellie.ai')
    api_endpoint = f"{backend_api_url}/api/accounts/me/"
    
    try:
        # Call Invite-ellie-backend API to validate token
        response = requests.get(
            api_endpoint,
            headers={
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json',
            },
            timeout=5  # 5 second timeout
        )
        
        if response.status_code == 200:
            user_data = response.json()
            # Extract user ID and email from response
            user_id = user_data.get('id')
            email = user_data.get('email')
            
            if user_id:
                logger.info(f"Successfully authenticated user: {user_id} ({email})")
                return {
                    'user_id': user_id,
                    'email': email,
                    'profile_data': user_data
                }
            else:
                logger.warning("Backend API returned user data without ID")
                return None
        elif response.status_code == 401:
            logger.warning("Invalid or expired token")
            return None
        else:
            logger.error(f"Backend API returned error: {response.status_code} - {response.text}")
            return None
            
    except requests.exceptions.RequestException as e:
        logger.error(f"Error calling backend API: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error in get_backend_user_from_token: {e}")
        return None


def get_user_from_auth_token(token):
    """
    Legacy function - kept for backward compatibility.
    Now validates with Invite-ellie-backend API instead of local User model.
    """
    # Try new backend authentication first
    backend_user = get_backend_user_from_token(token)
    if backend_user:
        # Return a mock user object with backend_user_id
        # This maintains compatibility with existing code that expects a user object
        mock_user = type('User', (object,), {
            'id': backend_user['user_id'],
            'backend_user_id': backend_user['user_id'],
            'email': backend_user.get('email'),
        })()
        return mock_user
    
    # Fallback to old JWT decoding (for backward compatibility during migration)
    try:
        decoded = jwt.decode(token, settings.SECRET_KEY, algorithms=['HS256'])
        user = User.objects.get(id=decoded['id'])
        return user
    except (jwt.DecodeError, jwt.InvalidTokenError, User.DoesNotExist):
        return None

