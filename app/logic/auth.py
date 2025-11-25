import jwt
from django.conf import settings
from app.models import User


def get_auth_token_for_user(user):
    return jwt.encode({'id': str(user.id)}, settings.SECRET_KEY, algorithm='HS256')


def get_user_from_auth_token(token):
    try:
        decoded = jwt.decode(token, settings.SECRET_KEY, algorithms=['HS256'])
        return User.objects.get(id=decoded['id'])
    except (jwt.DecodeError, jwt.InvalidTokenError, User.DoesNotExist):
        return None

