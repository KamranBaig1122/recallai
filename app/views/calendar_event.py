from django.shortcuts import redirect
from django.http import HttpResponse
from app.models import CalendarEvent, Calendar
from app.middleware.notice_middleware import generate_notice
import json


def set_manual_record(request, event_id):
    if not request.authenticated:
        return redirect('/')
    
    if request.method not in ['POST', 'PATCH', 'PUT']:
        return redirect('/')
    
    try:
        event = CalendarEvent.objects.get(id=event_id)
        manual_record = request.POST.get('manualRecord')
        
        # Convert string to boolean or None
        if manual_record == 'true':
            event.should_record_manual = True
        elif manual_record == 'false':
            event.should_record_manual = False
        else:
            event.should_record_manual = None
        
        event.save()
        
        print(f'INFO: Will set manual record to {event.should_record_manual} for event(ID: {event.id}).')
        
        # TODO: Update auto-record status and schedule bots (background tasks)
        
        try:
            calendar = Calendar.objects.get(id=event.calendar_id)
            response = redirect(f'/calendar/{calendar.id}')
        except Calendar.DoesNotExist:
            response = redirect('/')
        
        response.set_cookie('notice', json.dumps(generate_notice(
            'success',
            f'Calendar Event(ID: {event.id}) manual record set successfully.'
        )))
        return response
    except CalendarEvent.DoesNotExist:
        return HttpResponse(status=404)

