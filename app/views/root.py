from django.shortcuts import render, redirect
from django.http import HttpResponse
from app.logic.oauth import build_google_calendar_oauth_url, build_microsoft_outlook_oauth_url


def root_view(request):
    if request.authenticated:
        user = request.authentication.user
        calendars = user.get_calendars()
        
        connect_urls = {
            'googleCalendar': build_google_calendar_oauth_url({
                'userId': str(user.id)
            }),
            'microsoftOutlook': build_microsoft_outlook_oauth_url({
                'userId': str(user.id)
            }),
        }
        
        return render(request, 'index.html', {
            'notice': request.notice,
            'user': user,
            'calendars': calendars,
            'connectUrls': connect_urls,
        })
    else:
        from app.middleware.notice_middleware import generate_notice
        from django.http import HttpResponseRedirect
        response = HttpResponseRedirect('/sign-in')
        response.set_cookie('notice', 
            str({'type': 'error', 'message': 'You must be signed in to proceed.'}))
        return response

