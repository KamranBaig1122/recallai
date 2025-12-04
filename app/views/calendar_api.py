import json
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from app.logic.oauth import build_google_calendar_oauth_url, build_microsoft_outlook_oauth_url
from app.models import Calendar, User, CalendarEvent, CalendarWebhook, MeetingTranscription
from app.logic.auth import get_user_from_auth_token
from app.logic.sync import sync_calendar_events
from app.services.recall.service import get_service
from datetime import datetime


def add_cors_headers(response, request=None):
    """Add CORS headers to response - use specific origin when credentials are included"""
    # Get origin from request if available
    origin = None
    if request:
        origin = request.META.get('HTTP_ORIGIN')
    
    # Always use the specific origin if provided (for CORS to work properly)
    # Don't use credentials since frontend doesn't send them
    if origin:
        response['Access-Control-Allow-Origin'] = origin
    else:
        # Fallback to * if no origin
        response['Access-Control-Allow-Origin'] = '*'
    
    # Don't set credentials to true since frontend doesn't send credentials
    # This avoids CORS issues
    
    # Get the headers the browser is requesting (from OPTIONS preflight)
    # CORS requires exact match of header names
    requested_headers_str = ''
    if request and request.method == 'OPTIONS':
        requested_headers_str = request.META.get('HTTP_ACCESS_CONTROL_REQUEST_HEADERS', '')
        if requested_headers_str:
            print(f'Browser requested headers (raw): {requested_headers_str}')
            # Use the exact headers the browser requested, preserving case
            allowed_headers = requested_headers_str
        else:
            # No headers requested, use defaults
            allowed_headers = 'Content-Type, Accept, ngrok-skip-browser-warning'
    else:
        # Not an OPTIONS request, use defaults
        allowed_headers = 'Content-Type, Accept, ngrok-skip-browser-warning'
    
    response['Access-Control-Allow-Methods'] = 'GET, POST, PATCH, PUT, DELETE, OPTIONS'
    response['Access-Control-Allow-Headers'] = allowed_headers
    response['Access-Control-Max-Age'] = '3600'  # Cache preflight for 1 hour
    print(f'Responding with allowed headers: {allowed_headers}')
    return response


def get_user_from_request(request, userId=None):
    """
    Get user from userId parameter (no authentication required).
    userId can come from query params or request body.
    """
    # Get userId from query params or request body
    if not userId:
        userId = request.GET.get('userId')
    
    if not userId and request.body:
        try:
            import json
            data = json.loads(request.body)
            userId = data.get('userId')
        except:
            pass
    
    if userId:
        try:
            return User.objects.get(id=userId)
        except User.DoesNotExist:
            pass
    
    return None


@require_http_methods(["GET", "OPTIONS"])
@csrf_exempt
def api_list_calendars(request):
    """Get list of connected calendars for the authenticated user"""
    print(f'api_list_calendars called with method: {request.method}')
    print(f'Request path: {request.path}')
    print(f'Request META: {request.META.get("HTTP_ORIGIN")}')
    print(f'Full request method: {request.method}')
    
    if request.method == 'OPTIONS':
        print('Handling OPTIONS preflight request')
        # Log what headers the browser is requesting
        requested_headers = request.META.get('HTTP_ACCESS_CONTROL_REQUEST_HEADERS', '')
        requested_method = request.META.get('HTTP_ACCESS_CONTROL_REQUEST_METHOD', '')
        print(f'Browser requested headers: {requested_headers}')
        print(f'Browser requested method: {requested_method}')
        
        response = JsonResponse({})
        response = add_cors_headers(response, request)
        print(f'OPTIONS response headers: Access-Control-Allow-Origin={response.get("Access-Control-Allow-Origin")}')
        print(f'OPTIONS response headers: Access-Control-Allow-Methods={response.get("Access-Control-Allow-Methods")}')
        print(f'OPTIONS response headers: Access-Control-Allow-Headers={response.get("Access-Control-Allow-Headers")}')
        return response
    
    print('Handling GET request (not OPTIONS)')
    try:
        # Get userId from query params (no authentication required)
        userId = request.GET.get('userId')
        print(f'GET request received. userId param: {userId}')
        
        if not userId:
            response = JsonResponse({'error': 'userId parameter is required'}, status=400)
            return add_cors_headers(response, request)
        
        # Fetch calendars directly by user_id (no need for User object to exist)
        # This allows calendars to be created via OAuth even if user doesn't exist in DB yet
        print(f'Fetching calendars for userId: {userId}')
        calendars = Calendar.objects.filter(user_id=userId)
        
        calendar_list = []
        for cal in calendars:
            calendar_list.append({
                'id': str(cal.id),
                'platform': cal.platform,
                'email': cal.email,
                'status': cal.status,
                'connected': True,
            })
        
        print(f'Returning {len(calendar_list)} calendars')
        response = JsonResponse(calendar_list, safe=False)
        return add_cors_headers(response, request)
    except Exception as e:
        import traceback
        print(f'ERROR in api_list_calendars: {e}')
        traceback.print_exc()
        response = JsonResponse({'error': str(e)}, status=500)
        return add_cors_headers(response, request)


@require_http_methods(["GET", "POST", "OPTIONS"])
@csrf_exempt
def api_get_connect_urls(request):
    """Get OAuth authorization URLs for both Google and Microsoft Calendar - simple like root_view"""
    print(f'api_get_connect_urls called with method: {request.method}')
    print(f'Request path: {request.path}')
    
    if request.method == 'OPTIONS':
        response = JsonResponse({})
        return add_cors_headers(response, request)
    
    try:
        # Get userId from query params or request body (no authentication required)
        userId = request.GET.get('userId')
        print(f'GET request received. userId param: {userId}')
        
        if not userId and request.body:
            try:
                data = json.loads(request.body)
                userId = data.get('userId')
                print(f'Got userId from body: {userId}')
            except json.JSONDecodeError:
                pass
        
        if not userId:
            response = JsonResponse({'error': 'userId is required'}, status=400)
            return add_cors_headers(response, request)
        
        # Build URLs exactly like root_view does
        state = {'userId': userId}
        connect_urls = {
            'googleCalendar': build_google_calendar_oauth_url(state),
            'microsoftOutlook': build_microsoft_outlook_oauth_url(state),
        }
        
        response = JsonResponse(connect_urls)
        return add_cors_headers(response, request)
    except Exception as e:
        import traceback
        print(f'ERROR in api_get_connect_urls: {e}')
        traceback.print_exc()
        response = JsonResponse({'error': str(e)}, status=500)
        return add_cors_headers(response, request)


@require_http_methods(["GET", "OPTIONS"])
@csrf_exempt
def api_get_calendar(request, calendar_id):
    """Get calendar details with events and webhooks"""
    if request.method == 'OPTIONS':
        response = JsonResponse({})
        return add_cors_headers(response, request)
    
    # Get userId from query params (no authentication required)
    userId = request.GET.get('userId')
    if not userId:
        response = JsonResponse({'error': 'userId parameter is required'}, status=400)
        return add_cors_headers(response, request)
    
    try:
        calendar = Calendar.objects.get(id=calendar_id)
        
        # Verify the calendar belongs to the user
        if str(calendar.user_id) != str(userId):
            response = JsonResponse({'error': 'Calendar does not belong to this user'}, status=403)
            return add_cors_headers(response, request)
        
        # Get events
        events = CalendarEvent.objects.filter(calendar_id=calendar_id)
        sorted_events = sorted(
            events,
            key=lambda e: e.start_time if e.start_time else datetime.min,
            reverse=False
        )
        
        # Get webhooks
        webhooks = CalendarWebhook.objects.filter(calendar_id=calendar_id).order_by('-received_at')
        
        # Serialize events
        events_data = []
        for event in sorted_events:
            events_data.append({
                'id': str(event.id),
                'title': event.title or '(No Title)',
                'start_time': event.start_time.isoformat() if event.start_time else None,
                'end_time': event.end_time.isoformat() if event.end_time else None,
                'meeting_url': event.meeting_url,
                'should_record_manual': event.should_record_manual,
                'bots': event.bots,  # Include bots array to check if bot exists
            })
        
        # Serialize webhooks
        webhooks_data = []
        for webhook in webhooks:
            webhooks_data.append({
                'id': str(webhook.id),
                'event': webhook.event,
                'received_at': webhook.received_at.isoformat(),
            })
        
        response_data = {
            'id': str(calendar.id),
            'platform': calendar.platform,
            'email': calendar.email,
            'status': calendar.status,
            'auto_record_external_events': calendar.auto_record_external_events,
            'auto_record_only_confirmed_events': calendar.auto_record_only_confirmed_events,
            'events': events_data,
            'webhooks': webhooks_data,
        }
        
        response = JsonResponse(response_data)
        return add_cors_headers(response, request)
    except Calendar.DoesNotExist:
        response = JsonResponse({'error': 'Calendar not found'}, status=404)
        return add_cors_headers(response, request)
    except Exception as e:
        import traceback
        traceback.print_exc()
        response = JsonResponse({'error': str(e)}, status=500)
        return add_cors_headers(response, request)


@require_http_methods(["POST", "PATCH", "PUT", "OPTIONS"])
@csrf_exempt
def api_update_calendar(request, calendar_id):
    """Update calendar preferences"""
    if request.method == 'OPTIONS':
        response = JsonResponse({})
        return add_cors_headers(response, request)
    
    # Get userId from query params (no authentication required)
    userId = request.GET.get('userId')
    if not userId:
        response = JsonResponse({'error': 'userId parameter is required'}, status=400)
        return add_cors_headers(response, request)
    
    try:
        calendar = Calendar.objects.get(id=calendar_id)
        
        # Verify the calendar belongs to the user
        if str(calendar.user_id) != str(userId):
            response = JsonResponse({'error': 'Calendar does not belong to this user'}, status=403)
            return add_cors_headers(response, request)
        
        # Parse request body
        if request.body:
            data = json.loads(request.body)
            calendar.auto_record_external_events = data.get('autoRecordExternalEvents', calendar.auto_record_external_events)
            calendar.auto_record_only_confirmed_events = data.get('autoRecordOnlyConfirmedEvents', calendar.auto_record_only_confirmed_events)
        else:
            # Fallback to form data
            calendar.auto_record_external_events = request.POST.get('autoRecordExternalEvents', 'off') == 'on'
            calendar.auto_record_only_confirmed_events = request.POST.get('autoRecordOnlyConfirmedEvents', 'off') == 'on'
        
        calendar.save()
        
        response = JsonResponse({
            'message': 'Calendar preferences updated successfully',
            'calendar': {
                'id': str(calendar.id),
                'auto_record_external_events': calendar.auto_record_external_events,
                'auto_record_only_confirmed_events': calendar.auto_record_only_confirmed_events,
            }
        })
        return add_cors_headers(response, request)
    except Calendar.DoesNotExist:
        response = JsonResponse({'error': 'Calendar not found'}, status=404)
        return add_cors_headers(response, request)
    except Exception as e:
        import traceback
        traceback.print_exc()
        response = JsonResponse({'error': str(e)}, status=500)
        return add_cors_headers(response, request)


@require_http_methods(["POST", "GET", "OPTIONS"])
@csrf_exempt
def api_sync_calendar(request, calendar_id):
    """Sync calendar events from Recall API"""
    if request.method == 'OPTIONS':
        response = JsonResponse({})
        return add_cors_headers(response, request)
    
    # Get userId from query params (no authentication required)
    userId = request.GET.get('userId')
    if not userId:
        response = JsonResponse({'error': 'userId parameter is required'}, status=400)
        return add_cors_headers(response, request)
    
    try:
        calendar = Calendar.objects.get(id=calendar_id)
        
        # Verify the calendar belongs to the user
        if str(calendar.user_id) != str(userId):
            response = JsonResponse({'error': 'Calendar does not belong to this user'}, status=403)
            return add_cors_headers(response, request)
        
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
        
        response = JsonResponse({
            'success': result['success'],
            'message': message,
            'upserted': result.get('upserted', 0),
            'deleted': result.get('deleted', 0),
        })
        return add_cors_headers(response, request)
    except Calendar.DoesNotExist:
        response = JsonResponse({'error': 'Calendar not found'}, status=404)
        return add_cors_headers(response, request)
    except Exception as e:
        import traceback
        traceback.print_exc()
        response = JsonResponse({'error': str(e)}, status=500)
        return add_cors_headers(response, request)


@require_http_methods(["POST", "PATCH", "PUT", "OPTIONS"])
@csrf_exempt
def api_set_manual_record(request, event_id):
    """Set manual record preference for a calendar event"""
    if request.method == 'OPTIONS':
        response = JsonResponse({})
        return add_cors_headers(response, request)
    
    # Get userId from query params (no authentication required)
    userId = request.GET.get('userId')
    if not userId:
        response = JsonResponse({'error': 'userId parameter is required'}, status=400)
        return add_cors_headers(response, request)
    
    try:
        event = CalendarEvent.objects.get(id=event_id)
        calendar = Calendar.objects.get(id=event.calendar_id)
        
        # Verify the calendar belongs to the user
        if str(calendar.user_id) != str(userId):
            response = JsonResponse({'error': 'Calendar does not belong to this user'}, status=403)
            return add_cors_headers(response, request)
        
        # Parse request body
        manual_record = None
        if request.body:
            data = json.loads(request.body)
            manual_record = data.get('manualRecord')
        else:
            manual_record = request.POST.get('manualRecord')
        
        # Convert string to boolean or None
        if manual_record == 'true' or manual_record is True:
            event.should_record_manual = True
        elif manual_record == 'false' or manual_record is False:
            event.should_record_manual = False
        else:
            event.should_record_manual = None
        
        event.save()
        
        response = JsonResponse({
            'message': 'Manual record preference updated successfully',
            'event': {
                'id': str(event.id),
                'should_record_manual': event.should_record_manual,
            }
        })
        return add_cors_headers(response, request)
    except CalendarEvent.DoesNotExist:
        response = JsonResponse({'error': 'Event not found'}, status=404)
        return add_cors_headers(response, request)
    except Exception as e:
        import traceback
        traceback.print_exc()
        response = JsonResponse({'error': str(e)}, status=500)
        return add_cors_headers(response, request)


@require_http_methods(["DELETE", "OPTIONS"])
@csrf_exempt
def api_delete_calendar(request, calendar_id):
    """Delete/disconnect a calendar"""
    if request.method == 'OPTIONS':
        response = JsonResponse({})
        return add_cors_headers(response, request)
    
    # Get userId from query params (no authentication required)
    userId = request.GET.get('userId')
    if not userId:
        response = JsonResponse({'error': 'userId parameter is required'}, status=400)
        return add_cors_headers(response, request)
    
    try:
        calendar = Calendar.objects.get(id=calendar_id)
        
        # Verify the calendar belongs to the user
        if str(calendar.user_id) != str(userId):
            response = JsonResponse({'error': 'Calendar does not belong to this user'}, status=403)
            return add_cors_headers(response, request)
        
        # Delete from Recall.ai first
        recall_service = get_service()
        recall_id = calendar.recall_id
        try:
            recall_service.delete_calendar(recall_id)
            print(f'INFO: Successfully deleted calendar {recall_id} from Recall.ai')
        except Exception as e:
            # Log warning but continue with local deletion
            print(f'WARNING: Could not delete calendar from Recall API: {e}')
            import traceback
            traceback.print_exc()
        
        # Delete related events and webhooks from local database
        CalendarEvent.objects.filter(calendar_id=calendar_id).delete()
        CalendarWebhook.objects.filter(calendar_id=calendar_id).delete()
        
        # Delete calendar from local database
        calendar.delete()
        
        response = JsonResponse({'message': 'Calendar deleted successfully'}, status=200)
        return add_cors_headers(response, request)
    except Calendar.DoesNotExist:
        response = JsonResponse({'error': 'Calendar not found'}, status=404)
        return add_cors_headers(response, request)
    except Exception as e:
        response = JsonResponse({'error': str(e)}, status=500)
        return add_cors_headers(response, request)


@require_http_methods(["POST", "OPTIONS"])
@csrf_exempt
def api_create_bot_for_event(request, event_id):
    """Create a bot for a calendar event (for previous meetings)"""
    if request.method == 'OPTIONS':
        response = JsonResponse({})
        return add_cors_headers(response, request)
    
    # Get userId from query params (no authentication required)
    userId = request.GET.get('userId')
    if not userId:
        response = JsonResponse({'error': 'userId parameter is required'}, status=400)
        return add_cors_headers(response, request)
    
    try:
        from app.models import CalendarEvent
        from app.logic.bot_creator import create_bot_for_event
        
        event = CalendarEvent.objects.get(id=event_id)
        calendar = Calendar.objects.get(id=event.calendar_id)
        
        # Verify the calendar belongs to the user
        if str(calendar.user_id) != str(userId):
            response = JsonResponse({'error': 'Calendar does not belong to this user'}, status=403)
            return add_cors_headers(response, request)
        
        # Create bot for event
        # Allow creating bots for past meetings (meetings synced after calendar connection)
        # Note: Bots for past meetings won't be able to join, but can be created for record-keeping
        result = create_bot_for_event(event, force=True)
        
        if result['success']:
            response = JsonResponse({
                'success': True,
                'message': f'Bot created successfully for event "{event.title}"',
                'bot_id': result.get('bot_id'),
                'join_at': result.get('join_at'),
            })
        else:
            response = JsonResponse({
                'success': False,
                'error': result.get('error', 'Failed to create bot'),
                'bot_id': result.get('bot_id'),  # May exist if already created
            }, status=400)
        
        return add_cors_headers(response, request)
    except CalendarEvent.DoesNotExist:
        response = JsonResponse({'error': 'Event not found'}, status=404)
        return add_cors_headers(response, request)
    except Exception as e:
        import traceback
        traceback.print_exc()
        response = JsonResponse({'error': str(e)}, status=500)
        return add_cors_headers(response, request)
