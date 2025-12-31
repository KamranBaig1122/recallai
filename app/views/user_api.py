"""
API endpoints for user-specific data (meetings, transcriptions, recordings)
These endpoints show all user data regardless of calendar connection status
"""
import json
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from app.models import Calendar, CalendarEvent, MeetingTranscription, BotRecording
from app.views.calendar_api import add_cors_headers, get_backend_user_id_from_request
from datetime import datetime


@require_http_methods(["GET", "OPTIONS"])
@csrf_exempt
def api_user_meetings(request):
    """
    Get all meetings for the authenticated user.
    Returns meetings from both connected and disconnected calendars.
    """
    if request.method == 'OPTIONS':
        response = JsonResponse({})
        return add_cors_headers(response, request)
    
    try:
        # Get backend_user_id from request (JWT token or query param)
        backend_user_id = get_backend_user_id_from_request(request)
        if not backend_user_id:
            response = JsonResponse({'error': 'Authentication required. Provide JWT token or userId parameter'}, status=400)
            return add_cors_headers(response, request)
        
        print(f'[UserAPI] Getting all meetings for user: {backend_user_id}')
        
        # Get all calendar events for this user (from both connected and disconnected calendars)
        # First, get events by backend_user_id (preferred)
        events_by_user_id = CalendarEvent.objects.filter(backend_user_id=backend_user_id)
        
        # Also get events from calendars owned by this user (for backward compatibility)
        calendars = Calendar.objects.filter(
            backend_user_id=backend_user_id
        ) | Calendar.objects.filter(
            user_id=backend_user_id
        )
        calendar_ids = [str(cal.id) for cal in calendars]
        events_by_calendar = CalendarEvent.objects.filter(calendar_id__in=calendar_ids)
        
        # Combine both queries (remove duplicates)
        all_event_ids = set()
        all_events = []
        for event in events_by_user_id:
            if str(event.id) not in all_event_ids:
                all_event_ids.add(str(event.id))
                all_events.append(event)
        for event in events_by_calendar:
            if str(event.id) not in all_event_ids:
                all_event_ids.add(str(event.id))
                all_events.append(event)
        
        # Sort events by start time
        sorted_events = sorted(
            all_events,
            key=lambda e: e.start_time if e.start_time else datetime.min,
            reverse=False
        )
        
        # Get calendar info for each event
        calendar_map = {}
        for calendar in calendars:
            calendar_map[str(calendar.id)] = calendar
        
        # Build response
        result = []
        for event in sorted_events:
            calendar = calendar_map.get(str(event.calendar_id))
            calendar_status = calendar.status if calendar else 'unknown'
            calendar_email = calendar.email if calendar else None
            calendar_platform = calendar.platform if calendar else event.platform
            
            # Get transcriptions for this event
            transcriptions = MeetingTranscription.objects.filter(calendar_event_id=event.id)
            has_transcription = transcriptions.exists()
            has_summary = any(t.summary for t in transcriptions)
            has_action_items = any(t.action_items for t in transcriptions)
            
            result.append({
                'id': str(event.id),
                'calendar_id': str(event.calendar_id),
                'calendar_email': calendar_email,
                'calendar_platform': calendar_platform,
                'calendar_status': calendar_status,  # 'connected' or 'disconnected'
                'title': event.title or '(No Title)',
                'start_time': event.start_time.isoformat() if event.start_time else None,
                'end_time': event.end_time.isoformat() if event.end_time else None,
                'meeting_url': event.meeting_url,
                'platform': event.platform,
                'should_record_manual': event.should_record_manual,
                'bots': event.bots,
                'has_transcription': has_transcription,
                'has_summary': has_summary,
                'has_action_items': has_action_items,
                'created_at': event.created_at.isoformat() if event.created_at else None,
                'updated_at': event.updated_at.isoformat() if event.updated_at else None,
            })
        
        print(f'[UserAPI] Returning {len(result)} meetings for user {backend_user_id}')
        response = JsonResponse(result, safe=False)
        return add_cors_headers(response, request)
    except Exception as e:
        import traceback
        traceback.print_exc()
        response = JsonResponse({'error': str(e)}, status=500)
        return add_cors_headers(response, request)


@require_http_methods(["GET", "OPTIONS"])
@csrf_exempt
def api_user_transcriptions(request):
    """
    Get all transcriptions for the authenticated user.
    Returns transcriptions from both connected and disconnected calendars.
    """
    if request.method == 'OPTIONS':
        response = JsonResponse({})
        return add_cors_headers(response, request)
    
    try:
        # Get backend_user_id from request (JWT token or query param)
        backend_user_id = get_backend_user_id_from_request(request)
        if not backend_user_id:
            response = JsonResponse({'error': 'Authentication required. Provide JWT token or userId parameter'}, status=400)
            return add_cors_headers(response, request)
        
        print(f'[UserAPI] Getting all transcriptions for user: {backend_user_id}')
        
        # Get all transcriptions for this user (by backend_user_id)
        transcriptions = MeetingTranscription.objects.filter(
            backend_user_id=backend_user_id
        ).order_by('-created_at')
        
        # Also get transcriptions linked via calendar events (for backward compatibility)
        calendars = Calendar.objects.filter(
            backend_user_id=backend_user_id
        ) | Calendar.objects.filter(
            user_id=backend_user_id
        )
        calendar_ids = [str(cal.id) for cal in calendars]
        events = CalendarEvent.objects.filter(calendar_id__in=calendar_ids)
        event_ids = [str(event.id) for event in events]
        
        transcriptions_by_event = MeetingTranscription.objects.filter(
            calendar_event_id__in=event_ids
        ).order_by('-created_at')
        
        # Combine both queries (remove duplicates)
        all_transcription_ids = set()
        all_transcriptions = []
        for t in transcriptions:
            if str(t.id) not in all_transcription_ids:
                all_transcription_ids.add(str(t.id))
                all_transcriptions.append(t)
        for t in transcriptions_by_event:
            if str(t.id) not in all_transcription_ids:
                all_transcription_ids.add(str(t.id))
                all_transcriptions.append(t)
        
        # Build response
        result = []
        for transcription in all_transcriptions:
            # Get associated event and calendar (handle missing gracefully)
            event = None
            calendar = None
            try:
                event = CalendarEvent.objects.get(id=transcription.calendar_event_id)
                if event and event.calendar_id:
                    try:
                        calendar = Calendar.objects.get(id=event.calendar_id)
                    except Calendar.DoesNotExist:
                        calendar = None
            except CalendarEvent.DoesNotExist:
                event = None
                calendar = None
            
            result.append({
                'id': str(transcription.id),
                'event_id': str(transcription.calendar_event_id),
                'calendar_id': str(event.calendar_id) if event and event.calendar_id else None,
                'calendar_email': calendar.email if calendar else None,
                'calendar_platform': calendar.platform if calendar else (event.platform if event else None),
                'calendar_status': calendar.status if calendar else 'unknown',
                'bot_id': transcription.bot_id,
                'assemblyai_transcript_id': transcription.assemblyai_transcript_id or '',
                'meeting_title': event.title if event else 'Unknown Meeting',
                'meeting_url': event.meeting_url if event else None,
                'start_time': event.start_time.isoformat() if event and event.start_time else None,
                'end_time': event.end_time.isoformat() if event and event.end_time else None,
                'platform': event.platform if event else None,
                'transcript_text': transcription.transcript_text or '',
                'summary': transcription.summary or '',
                'action_items': transcription.action_items_list or [],
                'status': transcription.status,
                'language': transcription.language or 'en',
                'duration': transcription.duration,
                'utterances': transcription.utterances or [],
                'words': transcription.words or [],
                'workspace_id': str(transcription.workspace_id) if transcription.workspace_id else None,
                'folder_id': str(transcription.folder_id) if transcription.folder_id else None,
                'created_at': transcription.created_at.isoformat() if transcription.created_at else None,
                'updated_at': transcription.updated_at.isoformat() if transcription.updated_at else None,
            })
        
        print(f'[UserAPI] Returning {len(result)} transcriptions for user {backend_user_id}')
        response = JsonResponse(result, safe=False)
        return add_cors_headers(response, request)
    except Exception as e:
        import traceback
        traceback.print_exc()
        response = JsonResponse({'error': str(e)}, status=500)
        return add_cors_headers(response, request)


@require_http_methods(["GET", "OPTIONS"])
@csrf_exempt
def api_user_recordings(request):
    """
    Get all bot recordings for the authenticated user.
    Returns recordings from both connected and disconnected calendars.
    """
    if request.method == 'OPTIONS':
        response = JsonResponse({})
        return add_cors_headers(response, request)
    
    try:
        # Get backend_user_id from request (JWT token or query param)
        backend_user_id = get_backend_user_id_from_request(request)
        if not backend_user_id:
            response = JsonResponse({'error': 'Authentication required. Provide JWT token or userId parameter'}, status=400)
            return add_cors_headers(response, request)
        
        print(f'[UserAPI] Getting all recordings for user: {backend_user_id}')
        
        # Get all bot recordings for this user (by backend_user_id)
        recordings = BotRecording.objects.filter(
            backend_user_id=backend_user_id
        ).order_by('-created_at')
        
        # Also get recordings linked via calendar events (for backward compatibility)
        calendars = Calendar.objects.filter(
            backend_user_id=backend_user_id
        ) | Calendar.objects.filter(
            user_id=backend_user_id
        )
        calendar_ids = [str(cal.id) for cal in calendars]
        events = CalendarEvent.objects.filter(calendar_id__in=calendar_ids)
        event_ids = [str(event.id) for event in events]
        
        recordings_by_event = BotRecording.objects.filter(
            calendar_event_id__in=event_ids
        ).order_by('-created_at')
        
        # Combine both queries (remove duplicates)
        all_recording_ids = set()
        all_recordings = []
        for r in recordings:
            if str(r.id) not in all_recording_ids:
                all_recording_ids.add(str(r.id))
                all_recordings.append(r)
        for r in recordings_by_event:
            if str(r.id) not in all_recording_ids:
                all_recording_ids.add(str(r.id))
                all_recordings.append(r)
        
        # Build response
        result = []
        for recording in all_recordings:
            # Get associated event and calendar
            event = None
            calendar = None
            if recording.calendar_event_id:
                try:
                    event = CalendarEvent.objects.get(id=recording.calendar_event_id)
                    if event.calendar_id:
                        try:
                            calendar = Calendar.objects.get(id=event.calendar_id)
                        except Calendar.DoesNotExist:
                            pass
                except CalendarEvent.DoesNotExist:
                    pass
            
            result.append({
                'id': str(recording.id),
                'bot_id': recording.bot_id,
                'event_id': str(recording.calendar_event_id) if recording.calendar_event_id else None,
                'calendar_id': str(event.calendar_id) if event else None,
                'calendar_email': calendar.email if calendar else None,
                'calendar_platform': calendar.platform if calendar else (event.platform if event else None),
                'calendar_status': calendar.status if calendar else 'unknown',
                'meeting_title': event.title if event else 'Unknown Meeting',
                'meeting_url': event.meeting_url if event else None,
                'status': recording.status,
                'recordings': recording.recordings,
                'recall_data': recording.recall_data,
                'created_at': recording.created_at.isoformat() if recording.created_at else None,
                'updated_at': recording.updated_at.isoformat() if recording.updated_at else None,
            })
        
        print(f'[UserAPI] Returning {len(result)} recordings for user {backend_user_id}')
        response = JsonResponse(result, safe=False)
        return add_cors_headers(response, request)
    except Exception as e:
        import traceback
        traceback.print_exc()
        response = JsonResponse({'error': str(e)}, status=500)
        return add_cors_headers(response, request)


@require_http_methods(["POST", "OPTIONS"])
@csrf_exempt
def api_assign_folder_to_transcription(request, transcription_id):
    """
    Assign a folder to a transcription (and its associated BotRecording).
    This resolves an unresolved meeting by assigning it to a folder.
    """
    if request.method == 'OPTIONS':
        response = JsonResponse({})
        return add_cors_headers(response, request)
    
    try:
        # Get backend_user_id from request
        backend_user_id = get_backend_user_id_from_request(request)
        if not backend_user_id:
            response = JsonResponse({'error': 'Authentication required. Provide JWT token or userId parameter'}, status=400)
            return add_cors_headers(response, request)
        
        # Parse request body
        data = json.loads(request.body)
        folder_id = data.get('folder_id')
        workspace_id = data.get('workspace_id')
        
        if not folder_id:
            response = JsonResponse({'error': 'folder_id is required'}, status=400)
            return add_cors_headers(response, request)
        
        if not workspace_id:
            response = JsonResponse({'error': 'workspace_id is required'}, status=400)
            return add_cors_headers(response, request)
        
        print(f'[UserAPI] Assigning folder {folder_id} to transcription {transcription_id} for user {backend_user_id}')
        
        # Get the transcription
        try:
            transcription = MeetingTranscription.objects.get(id=transcription_id)
        except MeetingTranscription.DoesNotExist:
            response = JsonResponse({'error': 'Transcription not found'}, status=404)
            return add_cors_headers(response, request)
        
        # Verify the transcription belongs to the user
        # Check multiple ways for old meetings that might not have backend_user_id set
        transcription_user_id = str(transcription.backend_user_id) if transcription.backend_user_id else None
        request_user_id = str(backend_user_id)
        
        is_owned = False
        
        # Method 1: Direct backend_user_id match
        if transcription_user_id and transcription_user_id == request_user_id:
            is_owned = True
        
        # Method 2: Check via calendar events (for old meetings without backend_user_id)
        if not is_owned:
            try:
                from app.models import CalendarEvent, Calendar
                event = CalendarEvent.objects.get(id=transcription.calendar_event_id)
                
                # Check if event has backend_user_id matching
                if event.backend_user_id and str(event.backend_user_id) == request_user_id:
                    is_owned = True
                
                # Check via calendar ownership
                if not is_owned and event.calendar_id:
                    try:
                        calendar = Calendar.objects.get(id=event.calendar_id)
                        if calendar.backend_user_id and str(calendar.backend_user_id) == request_user_id:
                            is_owned = True
                        elif calendar.user_id and str(calendar.user_id) == request_user_id:
                            is_owned = True
                    except Calendar.DoesNotExist:
                        pass
            except CalendarEvent.DoesNotExist:
                pass
            except Exception as e:
                print(f'[UserAPI] Error checking calendar ownership: {e}')
        
        if not is_owned:
            print(f'[UserAPI] Ownership check failed: transcription.backend_user_id={transcription_user_id}, request.backend_user_id={request_user_id}')
            response = JsonResponse({'error': 'Unauthorized: Transcription does not belong to user'}, status=403)
            return add_cors_headers(response, request)
        
        # Update the transcription with folder_id and workspace_id
        # Also ensure backend_user_id is set (for old meetings that might not have it)
        transcription.folder_id = folder_id
        transcription.workspace_id = workspace_id
        if not transcription.backend_user_id:
            transcription.backend_user_id = backend_user_id
            transcription.save(update_fields=['folder_id', 'workspace_id', 'backend_user_id'])
        else:
            transcription.save(update_fields=['folder_id', 'workspace_id'])
        
        # Also update the associated BotRecording if it exists
        bot_recordings = BotRecording.objects.filter(bot_id=transcription.bot_id)
        for bot_recording in bot_recordings:
            bot_recording.folder_id = folder_id
            bot_recording.workspace_id = workspace_id
            if not bot_recording.backend_user_id:
                bot_recording.backend_user_id = backend_user_id
                bot_recording.save(update_fields=['folder_id', 'workspace_id', 'backend_user_id'])
            else:
                bot_recording.save(update_fields=['folder_id', 'workspace_id'])
        
        print(f'[UserAPI] Successfully assigned folder {folder_id} to transcription {transcription_id}')
        response = JsonResponse({
            'success': True,
            'message': 'Folder assigned successfully',
            'transcription_id': str(transcription.id),
            'folder_id': folder_id,
            'workspace_id': workspace_id,
        })
        return add_cors_headers(response, request)
    except Exception as e:
        import traceback
        traceback.print_exc()
        response = JsonResponse({'error': str(e)}, status=500)
        return add_cors_headers(response, request)
