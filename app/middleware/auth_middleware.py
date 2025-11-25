from django.utils.deprecation import MiddlewareMixin
from app.logic.auth import get_user_from_auth_token


class AuthMiddleware(MiddlewareMixin):
    def process_request(self, request):
        request.authenticated = False
        request.authentication = None
        
        auth_token = request.COOKIES.get('authToken')
        if auth_token:
            user = get_user_from_auth_token(auth_token)
            if user:
                request.authenticated = True
                request.authentication = type('obj', (object,), {'user': user})()

