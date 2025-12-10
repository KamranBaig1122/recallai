from django.utils.deprecation import MiddlewareMixin
from app.logic.auth import get_user_from_auth_token, get_backend_user_from_token


class AuthMiddleware(MiddlewareMixin):
    def process_request(self, request):
        request.authenticated = False
        request.authentication = None
        request.backend_user_id = None  # Store backend user ID for easy access
        
        # Try to get token from Authorization header first (Bearer token)
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        auth_token = None
        
        if auth_header.startswith('Bearer '):
            auth_token = auth_header.split('Bearer ')[1].strip()
        elif auth_header.startswith('bearer '):
            auth_token = auth_header.split('bearer ')[1].strip()
        else:
            # Fallback to cookie (for backward compatibility)
            auth_token = request.COOKIES.get('authToken')
        
        if auth_token:
            # Try new backend authentication first
            backend_user = get_backend_user_from_token(auth_token)
            if backend_user:
                # Create authentication object with backend user ID
                request.authenticated = True
                request.backend_user_id = backend_user['user_id']
                request.authentication = type('obj', (object,), {
                    'user': type('User', (object,), {
                        'id': backend_user['user_id'],
                        'backend_user_id': backend_user['user_id'],
                        'email': backend_user.get('email'),
                    })(),
                    'backend_user_id': backend_user['user_id'],
                })()
            else:
                # Fallback to legacy authentication (for backward compatibility)
                user = get_user_from_auth_token(auth_token)
                if user:
                    request.authenticated = True
                    request.backend_user_id = getattr(user, 'backend_user_id', getattr(user, 'id', None))
                    request.authentication = type('obj', (object,), {'user': user})()

