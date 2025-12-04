"""
API endpoints for fetching transcriptions and summaries
"""
import json
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from app.models import Calendar, CalendarEvent, MeetingTranscription
from app.views.calendar_api import add_cors_headers


@require_http_methods(["GET", "OPTIONS"])
@csrf_exempt
def api_list_transcriptions(request):
    """Get all transcriptions for meetings from connected calendars"""
    if request.method == 'OPTIONS':
        response = JsonResponse({})
        return add_cors_headers(response, request)
    
    try:
        userId = request.GET.get('userId')
        print(f'[TranscriptionAPI] ==========================================')
        print(f'[TranscriptionAPI] 📋 LIST TRANSCRIPTIONS REQUEST')
        print(f'[TranscriptionAPI] User ID: {userId}')
        print(f'[TranscriptionAPI] ==========================================')
        
        if not userId:
            print(f'[TranscriptionAPI] ❌ ERROR: userId parameter is required')
            response = JsonResponse({'error': 'userId parameter is required'}, status=400)
            return add_cors_headers(response, request)
        
        # Get all calendars for this user
        print(f'[TranscriptionAPI] Step 1: Fetching calendars for user...')
        calendars = Calendar.objects.filter(user_id=userId)
        calendar_ids = [str(cal.id) for cal in calendars]
        print(f'[TranscriptionAPI] Found {len(calendars)} calendars: {calendar_ids}')
        
        # Get all events from these calendars
        print(f'[TranscriptionAPI] Step 2: Fetching events from calendars...')
        events = CalendarEvent.objects.filter(calendar_id__in=calendar_ids)
        event_ids = [str(event.id) for event in events]
        print(f'[TranscriptionAPI] Found {len(events)} events: {event_ids}')
        
        # Get all transcriptions for these events (including processing ones)
        print(f'[TranscriptionAPI] Step 3: Fetching transcriptions for events...')
        transcriptions = MeetingTranscription.objects.filter(calendar_event_id__in=event_ids).order_by('-created_at')
        transcription_count = transcriptions.count()
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


@require_http_methods(["GET", "OPTIONS"])
@csrf_exempt
def api_get_transcription(request, transcription_id):
    """Get a specific transcription by ID"""
    if request.method == 'OPTIONS':
        response = JsonResponse({})
        return add_cors_headers(response, request)
    
    try:
        userId = request.GET.get('userId')
        if not userId:
            response = JsonResponse({'error': 'userId parameter is required'}, status=400)
            return add_cors_headers(response, request)
        
        transcription = MeetingTranscription.objects.get(id=transcription_id)
        
        # Verify the transcription belongs to a calendar event owned by this user
        print(f'[TranscriptionAPI] Verifying ownership...')
        event = CalendarEvent.objects.get(id=transcription.calendar_event_id)
        calendar = Calendar.objects.get(id=event.calendar_id)
        
        print(f'[TranscriptionAPI]   Event: {event.title or "Untitled"} (ID: {event.id})')
        print(f'[TranscriptionAPI]   Calendar user ID: {calendar.user_id}')
        print(f'[TranscriptionAPI]   Request user ID: {userId}')
        
        if str(calendar.user_id) != str(userId):
            print(f'[TranscriptionAPI] ❌ ERROR: Transcription does not belong to this user')
            response = JsonResponse({'error': 'Transcription does not belong to this user'}, status=403)
            return add_cors_headers(response, request)
        
        print(f'[TranscriptionAPI] ✓ Ownership verified')
        
        result = {
            'id': str(transcription.id),
            'event_id': str(transcription.calendar_event_id),
            'calendar_id': str(event.calendar_id),
            'bot_id': transcription.bot_id,
            'assemblyai_transcript_id': transcription.assemblyai_transcript_id,
            'meeting_title': event.title or 'Untitled Meeting',
            'meeting_url': event.meeting_url,
            'start_time': event.start_time.isoformat() if event.start_time else None,
            'end_time': event.end_time.isoformat() if event.end_time else None,
            'platform': event.platform,
            'transcript_data': transcription.transcript_data,
            'transcript_text': transcription.transcript_text,
            'summary': transcription.summary,
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

