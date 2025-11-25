import json
import requests
from django.conf import settings
from urllib.parse import urlencode


def build_google_calendar_oauth_url(state):
    params = {
        'client_id': settings.GOOGLE_CALENDAR_OAUTH_CLIENT_ID,
        'redirect_uri': f"{settings.PUBLIC_URL}/oauth-callback/google-calendar",
        'response_type': 'code',
        'scope': ' '.join(build_google_oauth_scopes()),
        'access_type': 'offline',
        'prompt': 'consent',
        'state': json.dumps(state),
    }
    
    url = 'https://accounts.google.com/o/oauth2/v2/auth'
    return f"{url}?{urlencode(params)}"


def build_google_oauth_scopes():
    if settings.REQUEST_ONLY_CALENDAR_SCOPES:
        return ['https://www.googleapis.com/auth/calendar.events.readonly']
    return [
        'https://www.googleapis.com/auth/userinfo.email',
        'https://www.googleapis.com/auth/calendar.events.readonly'
    ]


def build_microsoft_outlook_oauth_url(state):
    params = {
        'client_id': settings.MICROSOFT_OUTLOOK_OAUTH_CLIENT_ID,
        'redirect_uri': f"{settings.PUBLIC_URL}/oauth-callback/microsoft-outlook",
        'response_type': 'code',
        'scope': ' '.join(build_microsoft_outlook_oauth_scopes()),
        'state': json.dumps(state),
    }
    
    url = 'https://login.microsoftonline.com/common/oauth2/v2.0/authorize'
    return f"{url}?{urlencode(params)}"


def build_microsoft_outlook_oauth_scopes():
    base_scopes = [
        'offline_access',
        'https://graph.microsoft.com/Calendars.Read'
    ]
    if settings.REQUEST_ONLY_CALENDAR_SCOPES:
        return base_scopes
    return base_scopes + ['openid', 'email']


def fetch_tokens_from_authorization_code_for_google_calendar(code):
    params = {
        'client_id': settings.GOOGLE_CALENDAR_OAUTH_CLIENT_ID,
        'client_secret': settings.GOOGLE_CALENDAR_OAUTH_CLIENT_SECRET,
        'redirect_uri': f"{settings.PUBLIC_URL}/oauth-callback/google-calendar",
        'grant_type': 'authorization_code',
        'code': code,
    }
    
    response = requests.post(
        'https://oauth2.googleapis.com/token',
        data=params
    )
    return response.json()


def fetch_tokens_from_authorization_code_for_microsoft_outlook(code):
    params = {
        'client_id': settings.MICROSOFT_OUTLOOK_OAUTH_CLIENT_ID,
        'client_secret': settings.MICROSOFT_OUTLOOK_OAUTH_CLIENT_SECRET,
        'redirect_uri': f"{settings.PUBLIC_URL}/oauth-callback/microsoft-outlook",
        'grant_type': 'authorization_code',
        'code': code,
    }
    
    response = requests.post(
        'https://login.microsoftonline.com/common/oauth2/v2.0/token',
        data=params
    )
    return response.json()

