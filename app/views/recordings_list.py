"""
View to list all recordings
"""
from django.shortcuts import render
from django.db.models import Q
from app.models import BotRecording, CalendarEvent


def list_recordings(request):
    """
    List all recordings with filtering options
    """
    # Get all recordings
    recordings = BotRecording.objects.all().order_by('-created_at')
    
    # Filter by calendar event if provided
    event_id = request.GET.get('event_id')
    if event_id:
        recordings = recordings.filter(calendar_event_id=event_id)
    
    # Filter by status if provided
    status = request.GET.get('status')
    if status:
        recordings = recordings.filter(status=status)
    
    # Get associated calendar events
    event_ids = [r.calendar_event_id for r in recordings if r.calendar_event_id]
    events = {}
    if event_ids:
        events = {
            str(e.id): e for e in CalendarEvent.objects.filter(id__in=event_ids)
        }
    
    context = {
        'recordings': recordings,
        'events': events,
        'total_count': recordings.count(),
    }
    
    return render(request, 'recordings_list.html', context)

