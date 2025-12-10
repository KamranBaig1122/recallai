from django.shortcuts import render, redirect
from django.http import HttpResponse
from app.models import Calendar, CalendarEvent, CalendarWebhook
from app.services.recall.service import get_service
from app.middleware.notice_middleware import generate_notice
from app.logic.sync import sync_calendar_events
import json


def calendar_get(request, calendar_id):
    if not request.authenticated:
        return redirect('/')
    
    try:
        calendar = Calendar.objects.get(id=calendar_id)
        webhooks = CalendarWebhook.objects.filter(calendar_id=calendar_id).order_by('-received_at')
        # Filter out deleted events when displaying to users (per Recall API documentation)
        # We only show events that are not deleted
        events = CalendarEvent.objects.filter(calendar_id=calendar_id)
        
        # Sort events by start time
        from datetime import datetime
        sorted_events = sorted(
            events, 
            key=lambda e: e.start_time if e.start_time else datetime.min,
            reverse=False
        )
        
        # Add current time for status checking
        current_time = datetime.now()
        
        return render(request, 'calendar.html', {
            'calendar': calendar,
            'webhooks': webhooks,
            'events': sorted_events,
            'current_time': current_time,
            'notice': request.notice,
            'user': request.authentication.user,
        })
    except Calendar.DoesNotExist:
        return render(request, '404.html', {'notice': request.notice})


def calendar_update(request, calendar_id):
    if not request.authenticated:
        return redirect('/')
    
    if request.method not in ['POST', 'PATCH', 'PUT']:
        return redirect(f'/calendar/{calendar_id}')
    
    try:
        calendar = Calendar.objects.get(id=calendar_id)
        
        # HTML forms don't include unchecked checkboxes
        auto_record_external = request.POST.get('autoRecordExternalEvents', 'off') == 'on'
        auto_record_confirmed = request.POST.get('autoRecordOnlyConfirmedEvents', 'off') == 'on'
        
        calendar.auto_record_external_events = auto_record_external
        calendar.auto_record_only_confirmed_events = auto_record_confirmed
        calendar.save()
        
        email = calendar.email or ''
        response = redirect(f'/calendar/{calendar_id}')
        response.set_cookie('notice', json.dumps(generate_notice(
            'success',
            f'Calendar(ID: {calendar_id}, email: {email}) recording preferences updated successfully.'
        )))
        
        # TODO: Update auto-record status and schedule bots (background tasks)
        
        return response
    except Calendar.DoesNotExist:
        return render(request, '404.html', {'notice': request.notice})


def calendar_sync(request, calendar_id):
    """Sync calendar events from Recall API (manual sync)"""
    if not request.authenticated:
        return redirect('/')
    
    # Accept both GET (link click) and POST (form submit)
    if request.method not in ['GET', 'POST']:
        return redirect(f'/calendar/{calendar_id}')
    
    try:
        calendar = Calendar.objects.get(id=calendar_id)
        
        print(f'INFO: Manual sync triggered for calendar {calendar_id}')
        
        # Sync events
        result = sync_calendar_events(calendar)
        
        if result['success']:
            if result['upserted'] == 0 and result['deleted'] == 0:
                message = "No events to sync (either no events found or already up to date)"
            else:
                message = f"Successfully synced {result['upserted']} events"
                if result['deleted'] > 0:
                    message += f", deleted {result['deleted']} events"
        else:
            message = f"Sync failed: {result.get('error', 'Unknown error')}"
            print(f'ERROR: Sync failed for calendar {calendar_id}: {message}')
        
        response = redirect(f'/calendar/{calendar_id}')
        response.set_cookie('notice', json.dumps(generate_notice(
            'success' if result['success'] else 'error',
            message
        )))
        return response
    except Calendar.DoesNotExist:
        response = redirect('/')
        response.set_cookie('notice', json.dumps(generate_notice(
            'error',
            'Calendar not found.'
        )))
        return response
    except Exception as e:
        print(f'ERROR: Exception in calendar_sync: {e}')
        import traceback
        traceback.print_exc()
        response = redirect(f'/calendar/{calendar_id}')
        response.set_cookie('notice', json.dumps(generate_notice(
            'error',
            f'Sync failed: {str(e)}'
        )))
        return response


def calendar_delete(request, calendar_id):
    """
    Delete calendar - accepts POST with _method=DELETE (method override) or DELETE method.
    Similar to calendar-integration-demo/v2-demo/routes/calendar/delete.js
    """
    if not request.authenticated:
        return redirect('/')
    
    # Support method override (like JS project's allow-put-delete-via-forms middleware)
    if request.method == 'POST' and request.POST.get('_method') == 'DELETE':
        pass  # Treat as DELETE
    elif request.method not in ['POST', 'DELETE']:
        return redirect('/')
    
    try:
        calendar = Calendar.objects.get(id=calendar_id)
        recall_service = get_service()
        
        # Delete from Recall API first (like JS project)
        try:
            recall_service.delete_calendar(calendar.recall_id)
        except Exception as e:
            print(f'Warning: Could not delete calendar from Recall API: {e}')
            # Continue with local deletion even if Recall API fails
        
        calendar_email = calendar.email or ''
        calendar_id_str = str(calendar_id)
        
        # SOFT DELETE: Preserve meeting data (events, transcriptions, summaries, action items)
        # Mark calendar as disconnected instead of deleting
        calendar.status = 'disconnected'
        calendar.save()
        
        # DO NOT delete CalendarEvents - they contain meeting data
        # DO NOT delete CalendarWebhooks - they are historical data
        # DO NOT delete MeetingTranscriptions - they contain summaries and action items
        # DO NOT delete BotRecordings - they contain meeting recordings
        
        response = redirect('/')
        response.set_cookie('notice', json.dumps(generate_notice(
            'success',
            f'Calendar(ID: {calendar_id_str}, email: {calendar_email}) deleted successfully.'
        )))
        return response
    except Calendar.DoesNotExist:
        response = redirect('/')
        response.set_cookie('notice', json.dumps(generate_notice(
            'error',
            'Calendar not found.'
        )))
        return response
    except Exception as e:
        print(f'Error deleting calendar: {e}')
        import traceback
        traceback.print_exc()
        response = redirect('/')
        response.set_cookie('notice', json.dumps(generate_notice(
            'error',
            f'Failed to delete calendar: {str(e)}'
        )))
        return response

