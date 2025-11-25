import json
from django.shortcuts import redirect
from django.http import HttpResponse
from app.models import Calendar
from app.logic.oauth import (
    fetch_tokens_from_authorization_code_for_google_calendar,
    fetch_tokens_from_authorization_code_for_microsoft_outlook
)
from app.services.recall.service import get_service
from app.middleware.notice_middleware import generate_notice
from django.conf import settings


def google_calendar_callback(request):
    try:
        state = json.loads(request.GET.get('state', '{}'))
        userId = state.get('userId')
        calendarId = state.get('calendarId')
        code = request.GET.get('code')
        
        print(f'Received google oauth callback for user {userId} with code {code}')
        
        oauth_tokens = fetch_tokens_from_authorization_code_for_google_calendar(code)
        
        if 'error' in oauth_tokens:
            response = redirect('/')
            response.set_cookie('notice', json.dumps(generate_notice(
                'error',
                f'Failed to exchange code for oauth tokens due to "{oauth_tokens.get("error")}({oauth_tokens.get("error_description")})"'
            )))
            return response
        
        print(f'Successfully exchanged code for oauth tokens: {json.dumps(oauth_tokens)}')
        
        recall_service = get_service()
        local_calendar = None
        recall_calendar = None
        
        if calendarId:
            try:
                local_calendar = Calendar.objects.get(id=calendarId)
            except Calendar.DoesNotExist:
                pass
        
        if local_calendar:
            # Update existing calendar
            recall_calendar = recall_service.update_calendar(local_calendar.recall_id, {
                'oauth_refresh_token': oauth_tokens.get('refresh_token'),
                'oauth_client_id': settings.GOOGLE_CALENDAR_OAUTH_CLIENT_ID,
                'oauth_client_secret': settings.GOOGLE_CALENDAR_OAUTH_CLIENT_SECRET,
                'webhook_url': f"{settings.PUBLIC_URL}/webhooks/recall-calendar-updates",
            })
            local_calendar.recall_data = recall_calendar
            local_calendar.save()
        else:
            # Create new calendar
            recall_calendar = recall_service.create_calendar({
                'platform': 'google_calendar',
                'webhook_url': f"{settings.PUBLIC_URL}/webhooks/recall-calendar-updates",
                'oauth_refresh_token': oauth_tokens.get('refresh_token'),
                'oauth_client_id': settings.GOOGLE_CALENDAR_OAUTH_CLIENT_ID,
                'oauth_client_secret': settings.GOOGLE_CALENDAR_OAUTH_CLIENT_SECRET,
            })
            
            local_calendar = Calendar.objects.create(
                platform='google_calendar',
                recall_id=recall_calendar['id'],
                recall_data=recall_calendar,
                user_id=userId,
            )
        
        email = local_calendar.email or ''
        response = redirect('/')
        response.set_cookie('notice', json.dumps(generate_notice(
            'success',
            f'Successfully connected google calendar{" for " + email if email else ""}'
        )))
        return response
        
    except Exception as err:
        print(f'INFO: Failed to handle oauth callback from Google Calendar due to {err}')
        return HttpResponse(status=500)


def microsoft_outlook_callback(request):
    try:
        state = json.loads(request.GET.get('state', '{}'))
        userId = state.get('userId')
        calendarId = state.get('calendarId')
        code = request.GET.get('code')
        
        print(f'Received microsoft oauth callback for user {userId} with code {code}')
        
        oauth_tokens = fetch_tokens_from_authorization_code_for_microsoft_outlook(code)
        
        if 'error' in oauth_tokens:
            response = redirect('/')
            response.set_cookie('notice', json.dumps(generate_notice(
                'error',
                f'Failed to exchange code for oauth tokens due to "{oauth_tokens.get("error")}({oauth_tokens.get("error_description")})"'
            )))
            return response
        
        print(f'Successfully exchanged code for oauth tokens: {json.dumps(oauth_tokens)}')
        
        recall_service = get_service()
        local_calendar = None
        recall_calendar = None
        
        if calendarId:
            try:
                local_calendar = Calendar.objects.get(id=calendarId)
            except Calendar.DoesNotExist:
                pass
        
        if local_calendar:
            # Update existing calendar
            recall_calendar = recall_service.update_calendar(local_calendar.recall_id, {
                'oauth_refresh_token': oauth_tokens.get('refresh_token'),
                'oauth_client_id': settings.MICROSOFT_OUTLOOK_OAUTH_CLIENT_ID,
                'oauth_client_secret': settings.MICROSOFT_OUTLOOK_OAUTH_CLIENT_SECRET,
                'webhook_url': f"{settings.PUBLIC_URL}/webhooks/recall-calendar-updates",
            })
            local_calendar.recall_data = recall_calendar
            local_calendar.save()
        else:
            # Create new calendar
            recall_calendar = recall_service.create_calendar({
                'platform': 'microsoft_outlook',
                'webhook_url': f"{settings.PUBLIC_URL}/webhooks/recall-calendar-updates",
                'oauth_refresh_token': oauth_tokens.get('refresh_token'),
                'oauth_client_id': settings.MICROSOFT_OUTLOOK_OAUTH_CLIENT_ID,
                'oauth_client_secret': settings.MICROSOFT_OUTLOOK_OAUTH_CLIENT_SECRET,
            })
            
            local_calendar = Calendar.objects.create(
                platform='microsoft_outlook',
                recall_id=recall_calendar['id'],
                recall_data=recall_calendar,
                user_id=userId,
            )
        
        email = local_calendar.email or ''
        response = redirect('/')
        response.set_cookie('notice', json.dumps(generate_notice(
            'success',
            f'Successfully connected microsoft calendar{" for " + email if email else ""}'
        )))
        return response
        
    except Exception as err:
        print(f'INFO: Failed to handle oauth callback from Microsoft calendar due to {err}')
        return HttpResponse(status=500)

