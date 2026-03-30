"""
API endpoints for fetching transcriptions and summaries
"""
import json
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from app.models import Calendar, CalendarEvent, MeetingTranscription, BotRecording, RecordingArtifact
from app.views.calendar_api import add_cors_headers, get_backend_user_id_from_request


@require_http_methods(["GET", "OPTIONS"])
@csrf_exempt
def api_list_transcriptions(request):
    """Get all transcriptions for meetings from connected calendars"""
    if request.method == 'OPTIONS':
        response = JsonResponse({})
        return add_cors_headers(response, request)
    
    try:
        # Get backend_user_id from request (JWT token or query param)
        backend_user_id = get_backend_user_id_from_request(request)
        print(f'[TranscriptionAPI] ==========================================')
        print(f'[TranscriptionAPI] 📋 LIST TRANSCRIPTIONS REQUEST')
        print(f'[TranscriptionAPI] Backend User ID: {backend_user_id}')
        print(f'[TranscriptionAPI] ==========================================')
        
        if not backend_user_id:
            print(f'[TranscriptionAPI] ❌ ERROR: Authentication required')
            response = JsonResponse({'error': 'Authentication required. Provide JWT token or userId parameter'}, status=400)
            return add_cors_headers(response, request)
        
        # Get all transcriptions for this user (by backend_user_id)
        # This includes transcriptions from both connected and disconnected calendars
        print(f'[TranscriptionAPI] Step 1: Fetching transcriptions for user...')
        transcriptions = MeetingTranscription.objects.filter(
            backend_user_id=backend_user_id
        ).order_by('-created_at')
        
        # Also include transcriptions linked via calendar events (for backward compatibility)
        # Get calendars for this user
        calendars = Calendar.objects.filter(
            backend_user_id=backend_user_id
        ) | Calendar.objects.filter(
            user_id=backend_user_id
        )
        calendar_ids = [str(cal.id) for cal in calendars]
        print(f'[TranscriptionAPI] Found {len(calendars)} calendars: {calendar_ids}')
        
        # Get events from these calendars
        events = CalendarEvent.objects.filter(calendar_id__in=calendar_ids)
        event_ids = [str(event.id) for event in events]
        print(f'[TranscriptionAPI] Found {len(events)} events: {event_ids}')
        
        # Also get transcriptions by calendar_event_id (for backward compatibility)
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
        
        transcriptions = all_transcriptions
        transcription_count = len(transcriptions)
        print(f'[TranscriptionAPI] Found {transcription_count} transcriptions')
        
        if transcription_count == 0:
            print(f'[TranscriptionAPI] ⚠ No transcriptions found for {len(event_ids)} events')
            print(f'[TranscriptionAPI] This might mean:')
            print(f'[TranscriptionAPI]   1. Meetings haven\'t ended yet (transcriptions are created after bot.done)')
            print(f'[TranscriptionAPI]   2. Real-time transcripts are being saved but not yet finalized')
            print(f'[TranscriptionAPI]   3. No bots were created for these events')
        
        result = []
        print(f'[TranscriptionAPI] Step 4: Processing transcriptions...')
        for idx, transcription in enumerate(transcriptions, 1):
            print(f'[TranscriptionAPI] Processing transcription {idx}/{transcription_count}: {transcription.id}')
            print(f'[TranscriptionAPI]   Bot ID: {transcription.bot_id}')
            print(f'[TranscriptionAPI]   Status: {transcription.status}')
            print(f'[TranscriptionAPI]   AssemblyAI ID: {transcription.assemblyai_transcript_id}')
            
            # Get the associated calendar event
            try:
                event = CalendarEvent.objects.get(id=transcription.calendar_event_id)
                calendar = Calendar.objects.get(id=event.calendar_id)
                print(f'[TranscriptionAPI]   Event: {event.title or "Untitled"} (ID: {event.id})')
                print(f'[TranscriptionAPI]   Calendar: {calendar.email or calendar.platform} (ID: {calendar.id})')
            except (CalendarEvent.DoesNotExist, Calendar.DoesNotExist) as e:
                print(f'[TranscriptionAPI]   ⚠ WARNING: Event or calendar not found: {e}')
                print(f'[TranscriptionAPI]   Skipping this transcription')
                continue
            
            # Build result object
            result_item = {
                'id': str(transcription.id),
                'event_id': str(transcription.calendar_event_id),
                'calendar_id': str(event.calendar_id),
                'bot_id': transcription.bot_id,
                'assemblyai_transcript_id': transcription.assemblyai_transcript_id or '',
                'meeting_title': event.title or 'Untitled Meeting',
                'meeting_url': event.meeting_url,
                'start_time': event.start_time.isoformat() if event.start_time else None,
                'end_time': event.end_time.isoformat() if event.end_time else None,
                'platform': event.platform,
                'transcript_text': transcription.transcript_text or '',
                'summary': transcription.summary or '',
                'action_items': transcription.action_items_list or [],
                'contextual_nudges': transcription.contextual_nudges or [],
                'impact_score': transcription.impact_score,
                'key_outcomes_signals': transcription.key_outcomes_signals or [],
                'meeting_gaps': transcription.meeting_gaps or [],
                'open_questions': transcription.open_questions or [],
                'status': transcription.status,
                'language': transcription.language or 'en',
                'duration': transcription.duration,
                'utterances': transcription.utterances or [],
                'words': transcription.words or [],
                'created_at': transcription.created_at.isoformat() if transcription.created_at else None,
                'updated_at': transcription.updated_at.isoformat() if transcription.updated_at else None,
            }
            result.append(result_item)
            print(f'[TranscriptionAPI]   ✓ Added to result')
            print(f'[TranscriptionAPI]     - Transcript length: {len(result_item["transcript_text"])} chars')
            print(f'[TranscriptionAPI]     - Summary length: {len(result_item["summary"])} chars')
            print(f'[TranscriptionAPI]     - Utterances: {len(result_item["utterances"])}')
            print(f'[TranscriptionAPI]     - Status: {result_item["status"]}')
        
        print(f'[TranscriptionAPI] Step 5: Returning {len(result)} transcriptions')
        print(f'[TranscriptionAPI] ==========================================')
        response = JsonResponse(result, safe=False)
        return add_cors_headers(response, request)
    except Exception as e:
        import traceback
        traceback.print_exc()
        response = JsonResponse({'error': str(e)}, status=500)
        return add_cors_headers(response, request)


def api_delete_transcription(request, transcription_id):
    """
    Delete a transcription and all associated meeting data.
    This deletes:
    - MeetingTranscription (transcript, summary, action items, nudges, impact score)
    - BotRecording (associated bot recording)
    - RecordingArtifact (any downloaded artifacts)
    """
    try:
        # Get backend_user_id from request
        backend_user_id = get_backend_user_id_from_request(request)
        if not backend_user_id:
            response = JsonResponse({'error': 'Authentication required. Provide JWT token or userId parameter'}, status=400)
            return add_cors_headers(response, request)
        
        print(f'[TranscriptionAPI] DELETE request for transcription {transcription_id} by user {backend_user_id}')
        
        # Get the transcription
        try:
            transcription = MeetingTranscription.objects.get(id=transcription_id)
        except MeetingTranscription.DoesNotExist:
            response = JsonResponse({'error': 'Transcription not found'}, status=404)
            return add_cors_headers(response, request)
        
        # Verify ownership (similar to api_get_transcription)
        transcription_user_id = str(transcription.backend_user_id) if transcription.backend_user_id else None
        request_user_id = str(backend_user_id)
        
        is_owned = False
        
        # Method 1: Direct backend_user_id match
        if transcription_user_id and transcription_user_id == request_user_id:
            is_owned = True
        
        # Method 2: Check via calendar events (for old meetings without backend_user_id)
        if not is_owned:
            try:
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
                print(f'[TranscriptionAPI] Error checking calendar ownership: {e}')
        
        if not is_owned:
            print(f'[TranscriptionAPI] ❌ Ownership check failed: transcription.backend_user_id={transcription_user_id}, request.backend_user_id={request_user_id}')
            response = JsonResponse({'error': 'Unauthorized: Transcription does not belong to user'}, status=403)
            return add_cors_headers(response, request)
        
        print(f'[TranscriptionAPI] ✓ Ownership verified, proceeding with deletion')
        
        # Get related data before deletion
        bot_id = transcription.bot_id
        calendar_event_id = transcription.calendar_event_id
        
        # 1. Delete RecordingArtifacts (foreign key constraint - must delete first)
        # Get BotRecording IDs first
        bot_recording_ids = list(BotRecording.objects.filter(bot_id=bot_id).values_list('id', flat=True))
        artifacts = RecordingArtifact.objects.filter(bot_recording_id__in=bot_recording_ids)
        artifacts_count = artifacts.count()
        artifacts.delete()
        print(f'[TranscriptionAPI] ✓ Deleted {artifacts_count} recording artifact(s)')
        
        # 2. Delete BotRecording(s) associated with this bot_id
        bot_recordings = BotRecording.objects.filter(bot_id=bot_id)
        bot_recordings_count = bot_recordings.count()
        bot_recordings.delete()
        print(f'[TranscriptionAPI] ✓ Deleted {bot_recordings_count} bot recording(s)')
        
        # 3. Delete MeetingTranscription
        transcription.delete()
        print(f'[TranscriptionAPI] ✓ Deleted meeting transcription')
        
        # 4. Optionally delete CalendarEvent if it's a manual meeting and has no other transcriptions
        try:
            event = CalendarEvent.objects.get(id=calendar_event_id)
            # Check if this event has any other transcriptions
            other_transcriptions = MeetingTranscription.objects.filter(calendar_event_id=calendar_event_id)
            if other_transcriptions.count() == 0:
                # Check if it's a manual meeting (has a calendar but might be disconnected)
                # For now, we'll keep the event as it might be useful for history
                # Uncomment below if you want to delete the event too:
                # event.delete()
                # print(f'[TranscriptionAPI] ✓ Deleted calendar event (manual meeting)')
                print(f'[TranscriptionAPI] Keeping calendar event (may have historical value)')
        except CalendarEvent.DoesNotExist:
            print(f'[TranscriptionAPI] Calendar event not found (may have been deleted already)')
        
        print(f'[TranscriptionAPI] ✅ Successfully deleted all data for transcription {transcription_id}')
        response = JsonResponse({
            'success': True,
            'message': 'Meeting data deleted successfully',
            'transcription_id': str(transcription_id),
            'deleted': {
                'transcription': True,
                'bot_recordings': bot_recordings_count,
                'recording_artifacts': artifacts_count,
            }
        })
        return add_cors_headers(response, request)
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f'[TranscriptionAPI] ❌ Error deleting transcription: {e}')
        response = JsonResponse({'error': str(e)}, status=500)
        return add_cors_headers(response, request)


@require_http_methods(["GET", "DELETE", "OPTIONS"])
@csrf_exempt
def api_get_transcription(request, transcription_id):
    """Get a specific transcription by ID, or delete it and all associated data"""
    if request.method == 'OPTIONS':
        response = JsonResponse({})
        return add_cors_headers(response, request)
    
    # Handle DELETE request
    if request.method == 'DELETE':
        return api_delete_transcription(request, transcription_id)
    
    # Handle GET request
    try:
        # Get backend_user_id from request (JWT token or query param)
        backend_user_id = get_backend_user_id_from_request(request)
        if not backend_user_id:
            response = JsonResponse({'error': 'Authentication required. Provide JWT token or userId parameter'}, status=400)
            return add_cors_headers(response, request)
        
        transcription = MeetingTranscription.objects.get(id=transcription_id)
        
        # Get event and calendar (handle missing gracefully)
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
        
        # Verify the transcription belongs to this user
        print(f'[TranscriptionAPI] Verifying ownership...')
        
        # Check backend_user_id first (preferred)
        if transcription.backend_user_id:
            transcription_belongs_to_user = str(transcription.backend_user_id) == str(backend_user_id)
        else:
            # Fallback: check via calendar event (if it exists)
            if calendar:
                calendar_belongs_to_user = (
                    (calendar.backend_user_id and str(calendar.backend_user_id) == str(backend_user_id)) or
                    (calendar.user_id and str(calendar.user_id) == str(backend_user_id))
                )
                transcription_belongs_to_user = calendar_belongs_to_user
            else:
                # No calendar/event found, can't verify ownership - deny access
                transcription_belongs_to_user = False
        
        if not transcription_belongs_to_user:
            print(f'[TranscriptionAPI] ❌ ERROR: Transcription does not belong to this user')
            response = JsonResponse({'error': 'Transcription does not belong to this user'}, status=403)
            return add_cors_headers(response, request)
        
        print(f'[TranscriptionAPI] ✓ Ownership verified')
        
        result = {
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
            'transcript_data': transcription.transcript_data,
            'transcript_text': transcription.transcript_text,
            'summary': transcription.summary,
            'action_items': transcription.action_items_list or [],
            'contextual_nudges': transcription.contextual_nudges or [],
            'impact_score': transcription.impact_score,
            'impact_breakdown': transcription.transcript_data.get('impact_breakdown', {}) if transcription.transcript_data else {},
            'key_outcomes_signals': transcription.key_outcomes_signals or [],
            'meeting_gaps': transcription.meeting_gaps or [],
            'open_questions': transcription.open_questions or [],
            'status': transcription.status,
            'language': transcription.language,
            'duration': transcription.duration,
            'utterances': transcription.utterances,
            'words': transcription.words,
            'created_at': transcription.created_at.isoformat() if transcription.created_at else None,
            'updated_at': transcription.updated_at.isoformat() if transcription.updated_at else None,
        }
        
        print(f'[TranscriptionAPI] ✓ Returning transcription data')
        print(f'[TranscriptionAPI] ==========================================')
        response = JsonResponse(result)
        return add_cors_headers(response, request)
    except MeetingTranscription.DoesNotExist:
        response = JsonResponse({'error': 'Transcription not found'}, status=404)
        return add_cors_headers(response, request)
    except Exception as e:
        import traceback
        traceback.print_exc()
        response = JsonResponse({'error': str(e)}, status=500)
        return add_cors_headers(response, request)

