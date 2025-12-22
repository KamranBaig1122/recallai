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


def get_backend_user_id_from_request(request, userId=None):
    """
    Get backend_user_id from request.
    Priority:
    1. request.backend_user_id (from middleware - JWT token)
    2. userId query parameter (for backward compatibility)
    3. userId from request body
    """
    # Check if middleware set backend_user_id
    if hasattr(request, 'backend_user_id') and request.backend_user_id:
        return str(request.backend_user_id)
    
    # Fallback to query parameter
    if userId:
        return str(userId)
    
    # Try query parameter
    userId = request.GET.get('userId')
    if userId:
        return str(userId)
    
    # Try request body
    try:
        if request.body:
            data = json.loads(request.body)
            userId = data.get('userId')
            if userId:
                return str(userId)
    except:
        pass
    
    return None


@require_http_methods(["GET", "OPTIONS"])
@csrf_exempt
def api_list_calendars(request):
    """List all calendars for the authenticated user"""
    if request.method == 'OPTIONS':
        response = JsonResponse({})
        return add_cors_headers(response, request)
    
    # Get backend_user_id from request (JWT token or query param)
    backend_user_id = get_backend_user_id_from_request(request)
    if not backend_user_id:
        response = JsonResponse({'error': 'Authentication required. Provide JWT token or userId parameter'}, status=400)
        return add_cors_headers(response, request)
    
    try:
        from django.db.models import Q
        import uuid
        
        # Convert backend_user_id to UUID if it's a string
        try:
            if isinstance(backend_user_id, str):
                backend_user_id_uuid = uuid.UUID(backend_user_id)
            else:
                backend_user_id_uuid = backend_user_id
        except (ValueError, AttributeError):
            print(f'WARNING: Invalid user_id format: {backend_user_id}')
            response = JsonResponse({'error': 'Invalid user_id format'}, status=400)
            return add_cors_headers(response, request)
        
        print(f'INFO: Fetching calendars for backend_user_id: {backend_user_id_uuid}')
        
        # Get ONLY connected calendars for this user (check both backend_user_id and user_id for backward compatibility)
        calendars = Calendar.objects.filter(
            (Q(backend_user_id=backend_user_id_uuid) | Q(user_id=backend_user_id_uuid)) &
            Q(status='connected')
        ).order_by('-created_at')  # Order by most recent first
        
        print(f'INFO: Found {calendars.count()} connected calendar(s) for user {backend_user_id_uuid}')
        
        # Deduplicate calendars by recall_id (in case of duplicates)
        seen_recall_ids = set()
        calendars_data = []
        for calendar in calendars:
            # Skip if we've already seen this recall_id
            if calendar.recall_id in seen_recall_ids:
                print(f'INFO: Skipping duplicate calendar {calendar.id} with recall_id {calendar.recall_id}')
                continue
            seen_recall_ids.add(calendar.recall_id)
            
            calendars_data.append({
                'id': str(calendar.id),
                'platform': calendar.platform,
                'email': calendar.email,
                'status': calendar.status,
                'connected': calendar.status == 'connected',
                'recall_id': calendar.recall_id,
            })
            print(f'INFO: Calendar {calendar.id}: platform={calendar.platform}, status={calendar.status}, email={calendar.email}, backend_user_id={calendar.backend_user_id}, user_id={calendar.user_id}')
        
        print(f'INFO: Returning {len(calendars_data)} calendar(s)')
        response = JsonResponse({'calendars': calendars_data})
        return add_cors_headers(response, request)
    except Exception as e:
        import traceback
        traceback.print_exc()
        response = JsonResponse({'error': str(e)}, status=500)
        return add_cors_headers(response, request)


@require_http_methods(["GET", "POST", "OPTIONS"])
@csrf_exempt
def api_get_connect_urls(request):
    """Get OAuth connect URLs for Google Calendar and Microsoft Outlook"""
    if request.method == 'OPTIONS':
        response = JsonResponse({})
        return add_cors_headers(response, request)
    
    # Get backend_user_id from request (JWT token or query param)
    backend_user_id = get_backend_user_id_from_request(request)
    if not backend_user_id:
        response = JsonResponse({'error': 'Authentication required. Provide JWT token or userId parameter'}, status=400)
        return add_cors_headers(response, request)
    
    try:
        google_url = build_google_calendar_oauth_url({'userId': backend_user_id})
        microsoft_url = build_microsoft_outlook_oauth_url({'userId': backend_user_id})
        
        response = JsonResponse({
            'googleCalendar': google_url,
            'microsoftOutlook': microsoft_url,
        })
        return add_cors_headers(response, request)
    except Exception as e:
        import traceback
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
    
    # Get backend_user_id from request (JWT token or query param)
    backend_user_id = get_backend_user_id_from_request(request)
    if not backend_user_id:
        response = JsonResponse({'error': 'Authentication required. Provide JWT token or userId parameter'}, status=400)
        return add_cors_headers(response, request)
    
    try:
        calendar = Calendar.objects.get(id=calendar_id)
        
        # Verify the calendar belongs to the user
        calendar_belongs_to_user = (
            (calendar.backend_user_id and str(calendar.backend_user_id) == str(backend_user_id)) or
            (calendar.user_id and str(calendar.user_id) == str(backend_user_id))
        )
        if not calendar_belongs_to_user:
            response = JsonResponse({'error': 'Calendar does not belong to this user'}, status=403)
            return add_cors_headers(response, request)
        
        # Parse request body
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            data = {}
        
        # Update preferences
        if 'auto_record_external_events' in data:
            calendar.auto_record_external_events = data['auto_record_external_events']
        if 'auto_record_only_confirmed_events' in data:
            calendar.auto_record_only_confirmed_events = data['auto_record_only_confirmed_events']
        
        calendar.save()
        
        response = JsonResponse({
            'success': True,
            'message': 'Calendar preferences updated successfully',
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
    """Sync calendar events from Recall.ai"""
    if request.method == 'OPTIONS':
        response = JsonResponse({})
        return add_cors_headers(response, request)
    
    # Get backend_user_id from request (JWT token or query param)
    backend_user_id = get_backend_user_id_from_request(request)
    if not backend_user_id:
        response = JsonResponse({'error': 'Authentication required. Provide JWT token or userId parameter'}, status=400)
        return add_cors_headers(response, request)
    
    try:
        calendar = Calendar.objects.get(id=calendar_id)
        
        # Verify the calendar belongs to the user
        calendar_belongs_to_user = (
            (calendar.backend_user_id and str(calendar.backend_user_id) == str(backend_user_id)) or
            (calendar.user_id and str(calendar.user_id) == str(backend_user_id))
        )
        if not calendar_belongs_to_user:
            response = JsonResponse({'error': 'Calendar does not belong to this user'}, status=403)
            return add_cors_headers(response, request)
        
        # Sync events
        result = sync_calendar_events(calendar)
        
        if result.get('success'):
            response = JsonResponse({
                'success': True,
                'message': f'Synced {result.get("upserted", 0)} events',
                'upserted': result.get('upserted', 0),
                'deleted': result.get('deleted', 0),
            })
        else:
            response = JsonResponse({
                'success': False,
                'error': result.get('error', 'Failed to sync events'),
            }, status=500)
        
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
    
    # Get backend_user_id from request (JWT token or query param)
    backend_user_id = get_backend_user_id_from_request(request)
    if not backend_user_id:
        response = JsonResponse({'error': 'Authentication required. Provide JWT token or userId parameter'}, status=400)
        return add_cors_headers(response, request)
    
    try:
        event = CalendarEvent.objects.get(id=event_id)
        calendar = Calendar.objects.get(id=event.calendar_id)
        
        # Verify the calendar belongs to the user
        calendar_belongs_to_user = (
            (calendar.backend_user_id and str(calendar.backend_user_id) == str(backend_user_id)) or
            (calendar.user_id and str(calendar.user_id) == str(backend_user_id))
        )
        if not calendar_belongs_to_user:
            response = JsonResponse({'error': 'Calendar does not belong to this user'}, status=403)
            return add_cors_headers(response, request)
        
        # Parse request body
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            data = {}
        
        # Update manual record preference
        if 'should_record_manual' in data:
            event.should_record_manual = data['should_record_manual']
            event.save()
        
        response = JsonResponse({
            'success': True,
            'message': 'Manual record preference updated successfully',
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
    """Delete/disconnect a calendar - soft delete (preserves meeting data)"""
    if request.method == 'OPTIONS':
        response = JsonResponse({})
        return add_cors_headers(response, request)
    
    # Get backend_user_id from request (JWT token or query param)
    backend_user_id = get_backend_user_id_from_request(request)
    if not backend_user_id:
        response = JsonResponse({'error': 'Authentication required. Provide JWT token or userId parameter'}, status=400)
        return add_cors_headers(response, request)
    
    try:
        calendar = Calendar.objects.get(id=calendar_id)
        
        # Verify the calendar belongs to the user
        calendar_belongs_to_user = (
            (calendar.backend_user_id and str(calendar.backend_user_id) == str(backend_user_id)) or
            (calendar.user_id and str(calendar.user_id) == str(backend_user_id))
        )
        if not calendar_belongs_to_user:
            response = JsonResponse({'error': 'Calendar does not belong to this user'}, status=403)
            return add_cors_headers(response, request)
        
        # DO NOT delete BotRecordings - they contain meeting recordings
        # Just mark calendar as disconnected
        recall_service = get_service()
        try:
            recall_service.delete_calendar(calendar.recall_id)
        except Exception as e:
            print(f'WARNING: Could not delete calendar from Recall.ai: {e}')
        
        calendar.status = 'disconnected'
        calendar.save()
        
        response = JsonResponse({
            'success': True,
            'message': 'Calendar disconnected successfully',
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


@require_http_methods(["POST", "OPTIONS"])
@csrf_exempt
def api_create_bot_for_event(request, event_id):
    """Create a bot for a calendar event (for previous meetings)"""
    if request.method == 'OPTIONS':
        response = JsonResponse({})
        return add_cors_headers(response, request)
    
    # Get backend_user_id from request (JWT token or query param)
    backend_user_id = get_backend_user_id_from_request(request)
    if not backend_user_id:
        response = JsonResponse({'error': 'Authentication required. Provide JWT token or userId parameter'}, status=400)
        return add_cors_headers(response, request)
    
    try:
        from app.models import CalendarEvent
        from app.logic.bot_creator import create_bot_for_event
        
        event = CalendarEvent.objects.get(id=event_id)
        calendar = Calendar.objects.get(id=event.calendar_id)
        
        # Verify the calendar belongs to the user (check both backend_user_id and user_id for backward compatibility)
        calendar_belongs_to_user = (
            (calendar.backend_user_id and str(calendar.backend_user_id) == str(backend_user_id)) or
            (calendar.user_id and str(calendar.user_id) == str(backend_user_id))
        )
        if not calendar_belongs_to_user:
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


@require_http_methods(["POST", "OPTIONS"])
@csrf_exempt
def api_join_meeting_immediately(request):
    """
    Create a bot and join a meeting immediately (without join_at)
    Used when user enters a meeting link on the dashboard
    """
    if request.method == 'OPTIONS':
        response = JsonResponse({})
        return add_cors_headers(response, request)
    
    # Get backend_user_id from request (JWT token or query param)
    backend_user_id = get_backend_user_id_from_request(request)
    print(f'[api_join_meeting] backend_user_id from request: {backend_user_id}')
    if not backend_user_id:
        response = JsonResponse({'error': 'Authentication required. Provide JWT token or userId parameter'}, status=400)
        return add_cors_headers(response, request)
    
    try:
        # Parse request body
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            data = {}
        
        meeting_url = data.get('meeting_url') or data.get('meetingUrl') or data.get('link')
        meeting_password = data.get('meeting_password') or data.get('meetingPassword') or data.get('password')
        
        if not meeting_url:
            response = JsonResponse({'error': 'meeting_url is required'}, status=400)
            return add_cors_headers(response, request)
        
        print(f'[api_join_meeting] Creating bot for meeting_url: {meeting_url[:50]}...')
        
        # Import the function to create bot immediately
        from app.logic.bot_creator import create_bot_immediately
        
        # Create bot that joins immediately
        # Pass backend_user_id so a CalendarEvent can be created for transcription processing
        result = create_bot_immediately(
            meeting_url=meeting_url, 
            meeting_password=meeting_password,
            backend_user_id=backend_user_id
        )
        
        print(f'[api_join_meeting] Bot creation result: success={result.get("success")}, bot_id={result.get("bot_id")}')
        
        if result['success']:
            response = JsonResponse({
                'success': True,
                'message': 'Bot is joining the meeting now',
                'bot_id': result.get('bot_id'),
            })
        else:
            response = JsonResponse({
                'success': False,
                'error': result.get('error', 'Failed to create bot'),
            }, status=400)
        
        return add_cors_headers(response, request)
    except Exception as e:
        import traceback
        traceback.print_exc()
        response = JsonResponse({'error': str(e)}, status=500)
        return add_cors_headers(response, request)


@require_http_methods(["DELETE", "OPTIONS"])
@csrf_exempt
def api_delete_bot_for_event(request, event_id, bot_id):
    """Delete a scheduled bot for a calendar event"""
    if request.method == 'OPTIONS':
        response = JsonResponse({})
        return add_cors_headers(response, request)
    
    # Get backend_user_id from request (JWT token or query param)
    backend_user_id = get_backend_user_id_from_request(request)
    if not backend_user_id:
        response = JsonResponse({'error': 'Authentication required. Provide JWT token or userId parameter'}, status=400)
        return add_cors_headers(response, request)
    
    try:
        from app.models import BotRecording
        from django.utils import timezone
        
        event = CalendarEvent.objects.get(id=event_id)
        calendar = Calendar.objects.get(id=event.calendar_id)
        
        # Verify the calendar belongs to the user
        calendar_belongs_to_user = (
            (calendar.backend_user_id and str(calendar.backend_user_id) == str(backend_user_id)) or
            (calendar.user_id and str(calendar.user_id) == str(backend_user_id))
        )
        if not calendar_belongs_to_user:
            response = JsonResponse({'error': 'Calendar does not belong to this user'}, status=403)
            return add_cors_headers(response, request)
        
        # Verify bot exists in event
        bots = event.bots
        bot_found = False
        bot_data = None
        for bot in bots:
            if (bot.get('bot_id') or bot.get('id')) == bot_id:
                bot_found = True
                bot_data = bot
                break
        
        if not bot_found:
            response = JsonResponse({'error': 'Bot not found in this event'}, status=404)
            return add_cors_headers(response, request)
        
        # Check if bot has already joined
        recall_service = get_service()
        try:
            bot_info = recall_service.get_bot(bot_id)
            bot_status = bot_info.get('status', '').lower()
            if bot_status in ['joined', 'recording', 'done', 'completed']:
                response = JsonResponse({'error': 'Cannot delete bot that has already joined the meeting'}, status=400)
                return add_cors_headers(response, request)
        except Exception as e:
            # If we can't get bot info, check join_at from event data
            join_at = bot_data.get('join_at') if bot_data else None
            if join_at:
                try:
                    join_time = datetime.fromisoformat(join_at.replace('Z', '+00:00'))
                    if timezone.is_naive(join_time):
                        join_time = timezone.make_aware(join_time)
                    if join_time <= timezone.now():
                        response = JsonResponse({'error': 'Cannot delete bot that has already joined the meeting'}, status=400)
                        return add_cors_headers(response, request)
                except:
                    pass
        
        # Delete bot from Recall.ai
        try:
            recall_service.delete_bot(bot_id)
            print(f'INFO: ✓ Deleted bot {bot_id} from Recall.ai for event {event_id}')
        except Exception as e:
            # If deletion fails, check if bot has already joined
            print(f'WARNING: Failed to delete bot {bot_id} from Recall.ai: {e}')
            # Try to get bot status to see if it's already joined
            try:
                bot_info = recall_service.get_bot(bot_id)
                bot_status = bot_info.get('status', '').lower()
                if bot_status in ['joined', 'recording', 'done', 'completed']:
                    response = JsonResponse({'error': 'Cannot delete bot that has already joined the meeting'}, status=400)
                    return add_cors_headers(response, request)
            except:
                pass
            # If we can't determine status, return error
            response = JsonResponse({'error': f'Failed to delete bot: {str(e)}'}, status=500)
            return add_cors_headers(response, request)
        
        # Remove bot from event's recall_data
        recall_data = event.recall_data.copy()
        bots_list = recall_data.get('bots', [])
        updated_bots = [
            bot for bot in bots_list
            if (bot.get('bot_id') or bot.get('id')) != bot_id
        ]
        recall_data['bots'] = updated_bots
        event.recall_data = recall_data
        event.save()
        
        # Delete BotRecording if it exists (only for scheduled bots)
        BotRecording.objects.filter(bot_id=bot_id).delete()
        
        # Broadcast update to WebSocket clients
        try:
            from channels.layers import get_channel_layer
            from asgiref.sync import async_to_sync
            channel_layer = get_channel_layer()
            if channel_layer:
                group_name = f'calendar_updates_{calendar.user_id}'
                async_to_sync(channel_layer.group_send)(
                    group_name,
                    {
                        'type': 'calendar_update',
                        'message': {
                            'calendar_id': str(calendar.id),
                            'event': 'bot_deleted',
                            'event_id': str(event_id),
                            'bot_id': bot_id,
                        }
                    }
                )
                print(f'INFO: Broadcasted bot deletion to WebSocket group {group_name}')
        except Exception as ws_error:
            print(f'WARNING: Failed to broadcast WebSocket update: {ws_error}')
        
        response = JsonResponse({
            'success': True,
            'message': f'Bot {bot_id} deleted successfully',
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
def api_delete_user_data(request, user_id):
    """
    Delete all data for a user (Invite-ellie-backend user UUID).
    
    This endpoint:
    1. Deletes all bots (scheduled and with media) from Recall.ai
    2. Deletes all calendars from Recall.ai
    3. Deletes all database records (CalendarEvent, BotRecording, MeetingTranscription, etc.)
    
    This is irreversible and should only be called when deleting a user account.
    """
    if request.method == 'OPTIONS':
        response = JsonResponse({})
        return add_cors_headers(response, request)
    
    try:
        from app.models import BotRecording, RecordingArtifact, CalendarWebhook
        from django.db import models
        from django.utils import timezone
        
        if not user_id:
            response = JsonResponse({'error': 'user_id parameter is required'}, status=400)
            return add_cors_headers(response, request)
        
        print(f'INFO: Starting deletion of all data for user {user_id}')
        
        recall_service = get_service()
        deletion_stats = {
            'calendars_deleted': 0,
            'calendars_failed': 0,
            'bots_deleted': 0,
            'bots_media_deleted': 0,
            'bots_failed': 0,
            'db_records_deleted': {
                'calendars': 0,
                'calendar_events': 0,
                'bot_recordings': 0,
                'recording_artifacts': 0,
                'meeting_transcriptions': 0,
                'calendar_webhooks': 0,
            }
        }
        
        # Find all calendars for this user (by backend_user_id)
        calendars = Calendar.objects.filter(backend_user_id=user_id)
        print(f'INFO: Found {calendars.count()} calendar(s) for user {user_id}')
        
        # Process each calendar
        for calendar in calendars:
            try:
                # Get all events for this calendar
                events = CalendarEvent.objects.filter(calendar_id=calendar.id)
                print(f'INFO: Found {events.count()} event(s) for calendar {calendar.id}')
                
                # Collect all bot IDs from events and bot_recordings
                all_bot_ids = set()
                
                # Get bots from events
                for event in events:
                    bots = event.bots
                    if bots:
                        for bot in bots:
                            bot_id = bot.get('bot_id') or bot.get('id')
                            if bot_id:
                                all_bot_ids.add(bot_id)
                
                # Get bots from BotRecording
                bot_recordings = BotRecording.objects.filter(backend_user_id=user_id)
                for recording in bot_recordings:
                    if recording.bot_id:
                        all_bot_ids.add(recording.bot_id)
                
                print(f'INFO: Found {len(all_bot_ids)} unique bot(s) for user {user_id}')
                
                # Delete all bots
                for bot_id in all_bot_ids:
                    try:
                        # First, try to delete bot media (for bots that have joined)
                        try:
                            recall_service.delete_bot_media(bot_id)
                            deletion_stats['bots_media_deleted'] += 1
                            print(f'INFO: ✓ Deleted media for bot {bot_id}')
                        except Exception as media_error:
                            # If media deletion fails, bot might be scheduled or not have media
                            print(f'INFO: Could not delete media for bot {bot_id}: {media_error}')
                        
                        # Then, try to delete the bot (for scheduled bots)
                        try:
                            recall_service.delete_bot(bot_id)
                            deletion_stats['bots_deleted'] += 1
                            print(f'INFO: ✓ Deleted bot {bot_id}')
                        except Exception as bot_error:
                            # If bot deletion fails, it might have already been deleted or joined
                            print(f'WARNING: Could not delete bot {bot_id}: {bot_error}')
                            deletion_stats['bots_failed'] += 1
                    except Exception as e:
                        print(f'ERROR: Error processing bot {bot_id}: {e}')
                        deletion_stats['bots_failed'] += 1
                
                # Delete calendar from Recall.ai
                try:
                    recall_service.delete_calendar(calendar.recall_id)
                    deletion_stats['calendars_deleted'] += 1
                    print(f'INFO: ✓ Deleted calendar {calendar.recall_id} from Recall.ai')
                except Exception as cal_error:
                    print(f'WARNING: Could not delete calendar {calendar.recall_id} from Recall.ai: {cal_error}')
                    deletion_stats['calendars_failed'] += 1
                
            except Exception as calendar_error:
                print(f'ERROR: Error processing calendar {calendar.id}: {calendar_error}')
                import traceback
                traceback.print_exc()
        
        # Delete all database records for this user
        # Delete RecordingArtifacts first (foreign key constraint)
        artifacts = RecordingArtifact.objects.filter(bot_recording_id__in=BotRecording.objects.filter(backend_user_id=user_id).values_list('id', flat=True))
        artifacts_count = artifacts.count()
        artifacts.delete()
        deletion_stats['db_records_deleted']['recording_artifacts'] = artifacts_count
        print(f'INFO: ✓ Deleted {artifacts_count} recording artifact(s)')
        
        # Delete BotRecordings
        bot_recordings = BotRecording.objects.filter(backend_user_id=user_id)
        bot_recordings_count = bot_recordings.count()
        bot_recordings.delete()
        deletion_stats['db_records_deleted']['bot_recordings'] = bot_recordings_count
        print(f'INFO: ✓ Deleted {bot_recordings_count} bot recording(s)')
        
        # Delete MeetingTranscriptions
        transcriptions = MeetingTranscription.objects.filter(backend_user_id=user_id)
        transcriptions_count = transcriptions.count()
        transcriptions.delete()
        deletion_stats['db_records_deleted']['meeting_transcriptions'] = transcriptions_count
        print(f'INFO: ✓ Deleted {transcriptions_count} meeting transcription(s)')
        
        # Delete CalendarWebhooks
        calendar_ids = Calendar.objects.filter(backend_user_id=user_id).values_list('id', flat=True)
        webhooks = CalendarWebhook.objects.filter(calendar_id__in=calendar_ids)
        webhooks_count = webhooks.count()
        webhooks.delete()
        deletion_stats['db_records_deleted']['calendar_webhooks'] = webhooks_count
        print(f'INFO: ✓ Deleted {webhooks_count} calendar webhook(s)')
        
        # Delete CalendarEvents
        calendar_ids = Calendar.objects.filter(backend_user_id=user_id).values_list('id', flat=True)
        events = CalendarEvent.objects.filter(calendar_id__in=calendar_ids)
        events_count = events.count()
        events.delete()
        deletion_stats['db_records_deleted']['calendar_events'] = events_count
        print(f'INFO: ✓ Deleted {events_count} calendar event(s)')
        
        # Delete Calendars
        calendars = Calendar.objects.filter(backend_user_id=user_id)
        calendars_count = calendars.count()
        calendars.delete()
        deletion_stats['db_records_deleted']['calendars'] = calendars_count
        print(f'INFO: ✓ Deleted {calendars_count} calendar(s) from database')
        
        print(f'INFO: ✓ Completed deletion of all data for user {user_id}')
        
        response = JsonResponse({
            'success': True,
            'message': f'Successfully deleted all data for user {user_id}',
            'stats': deletion_stats
        })
        return add_cors_headers(response, request)
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f'ERROR: Failed to delete user data: {e}')
        response = JsonResponse({'error': str(e)}, status=500)
        return add_cors_headers(response, request)
