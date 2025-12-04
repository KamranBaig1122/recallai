"""
Webhook handlers for Recall.ai bot events (transcripts, participant events, etc.)
These are different from calendar webhooks - these come from bots during meetings.
"""
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json
import os


@csrf_exempt
def bot_webhook(request, bot_id=None):
    """
    Handle webhooks from Recall.ai bots during meetings.
    
    Receives:
    - transcript.data: Real-time transcripts
    - participant_events.*: Join/leave, speech on/off, webcam on/off, etc.
    - bot.status_change: Bot status updates (e.g., bot.done when meeting ends)
    
    Similar to meeting-bot/app/pythonHowToBuildABot.py wh() function
    """
    if request.method != 'POST':
        return HttpResponse(status=405)
    
    try:
        # Parse request body
        body_str = request.body.decode('utf-8')
        try:
            payload = json.loads(body_str)
        except json.JSONDecodeError:
            print(f'[bot-wh] non-JSON payload: {body_str[:200]}')
            return JsonResponse({"ok": False, "error": "bad json"}, status=400)
        
        # Log all incoming webhook events for debugging
        event = payload.get("event") or payload.get("type", "")
        
        data = payload.get("data") or payload.get("payload") or {}
        event_data = data.get("data") or data
        
        # Extract bot_id from various possible locations in the payload
        # The bot_id is typically at data.bot.id (as seen in the logs)
        bot_id = (
            payload.get("bot_id") or 
            data.get("bot", {}).get("id") or  # This is the correct location!
            payload.get("data", {}).get("bot_id") or
            payload.get("data", {}).get("bot", {}).get("id") or
            event_data.get("bot_id") or
            event_data.get("bot", {}).get("id") or
            payload.get("payload", {}).get("bot_id") or
            payload.get("payload", {}).get("bot", {}).get("id")
        )
        
        print(f'[bot-wh] ==========================================')
        print(f'[bot-wh] 📨 WEBHOOK RECEIVED')
        print(f'[bot-wh] Event: {event}')
        print(f'[bot-wh] Bot ID: {bot_id}')
        print(f'[bot-wh] Payload keys: {list(payload.keys())}')
        if not bot_id:
            print(f'[bot-wh] ⚠ WARNING: bot_id not found in payload!')
            print(f'[bot-wh] Payload structure (first 1000 chars): {json.dumps(payload, indent=2)[:1000]}')
            print(f'[bot-wh] Event data keys: {list(event_data.keys()) if isinstance(event_data, dict) else "Not a dict"}')
        print(f'[bot-wh] ==========================================')
        
        # Extract timestamp and participant info
        timestamp = (event_data.get("timestamp") or {}).get("absolute")
        participant = event_data.get("participant")
        participant_name = None
        if isinstance(participant, dict):
            participant_name = participant.get("name") or participant.get("id")
        
        # Handle different event types
        if event == "transcript.data" or event == "transcript.partial_data":
            # Real-time transcript events from AssemblyAI (as per demo project)
            words = event_data.get("words") or []
            transcript_data = event_data.get("transcript", {})
            
            # Extract transcript text - try formatted text first, fall back to words (as per demo)
            transcript_text = ''
            if event_data.get("text"):
                transcript_text = event_data.get("text")
            elif transcript_data and transcript_data.get("text"):
                transcript_text = transcript_data.get("text")
            else:
                # Reconstruct from individual words (as per demo)
                transcript_text = " ".join((w.get("text", "") for w in words))
            
            event_type = "FINAL" if event == "transcript.data" else "PARTIAL"
            
            if participant_name and transcript_text:
                print(f'[bot-wh] [TRANSCRIPT] {event_type} - {participant_name}: {transcript_text[:200]}')
                
                # Store real-time transcripts in database for immediate access
                # This allows frontend to see transcripts as they happen
                try:
                    from app.models import CalendarEvent, MeetingTranscription
                    from app.services.recall.service import get_service
                    
                    if bot_id:
                        print(f'[bot-wh] [TRANSCRIPT] Looking for calendar event with bot_id: {bot_id}')
                        calendar_event = None
                        
                        # First, try to find via BotRecording table (most reliable)
                        from app.models import BotRecording
                        bot_recording = BotRecording.objects.filter(bot_id=bot_id).first()
                        if bot_recording and bot_recording.calendar_event_id:
                            calendar_event = CalendarEvent.objects.filter(id=bot_recording.calendar_event_id).first()
                            if calendar_event:
                                print(f'[bot-wh] [TRANSCRIPT] ✓ Found calendar event via BotRecording: {calendar_event.id}')
                        
                        # If not found, try searching in CalendarEvent's recall_data
                        if not calendar_event:
                            # Try searching where bots is an array of objects with 'bot_id' field
                            calendar_event = CalendarEvent.objects.filter(
                                recall_data__bots__bot_id=bot_id
                            ).first()
                            
                            # If not found, try searching where bots is an array of objects with 'id' field
                            if not calendar_event:
                                calendar_event = CalendarEvent.objects.filter(
                                    recall_data__bots__id=bot_id
                                ).first()
                        
                        if not calendar_event:
                            print(f'[bot-wh] [TRANSCRIPT] ⚠ WARNING: Calendar event not found for bot_id: {bot_id}')
                            print(f'[bot-wh] [TRANSCRIPT] This transcript will not be saved to database')
                        else:
                            print(f'[bot-wh] [TRANSCRIPT] ✓ Found calendar event: {calendar_event.id}')
                            
                            if event == "transcript.data":  # Only save final transcripts
                                print(f'[bot-wh] [TRANSCRIPT] Saving real-time transcript to database')
                            print(f'[bot-wh] [TRANSCRIPT]   Calendar Event ID: {calendar_event.id}')
                            print(f'[bot-wh] [TRANSCRIPT]   Bot ID: {bot_id}')
                            print(f'[bot-wh] [TRANSCRIPT]   Speaker: {participant_name}')
                            print(f'[bot-wh] [TRANSCRIPT]   Text: {transcript_text[:100]}...')
                            
                            # Get or create transcription record (one per bot per event)
                            transcription, created = MeetingTranscription.objects.get_or_create(
                                calendar_event_id=calendar_event.id,
                                bot_id=bot_id,
                                defaults={
                                    'assemblyai_transcript_id': None,  # Will be set when final transcript is fetched
                                    'transcript_data': {
                                        'utterances': [{
                                            'speaker': participant_name,
                                            'text': transcript_text,
                                            'start': timestamp,
                                            'words': words
                                        }]
                                    },
                                    'transcript_text': f"{participant_name}: {transcript_text}",
                                    'status': 'processing',
                                }
                            )
                            
                            if created:
                                print(f'[bot-wh] [TRANSCRIPT] ✓ Created new transcription record (ID: {transcription.id})')
                            else:
                                # Append to existing transcription
                                print(f'[bot-wh] [TRANSCRIPT] Updating existing transcription (ID: {transcription.id})')
                                utterances = transcription.transcript_data.get('utterances', [])
                                utterances.append({
                                    'speaker': participant_name,
                                    'text': transcript_text,
                                    'start': timestamp,
                                    'words': words
                                })
                                transcription.transcript_data['utterances'] = utterances
                                # Append to transcript text
                                if transcription.transcript_text:
                                    transcription.transcript_text += f"\n{participant_name}: {transcript_text}"
                                else:
                                    transcription.transcript_text = f"{participant_name}: {transcript_text}"
                                transcription.save()
                                print(f'[bot-wh] [TRANSCRIPT] ✓ Updated real-time transcript (now {len(utterances)} utterances)')
                except Exception as e:
                    print(f'[bot-wh] [TRANSCRIPT] Error saving real-time transcript: {e}')
                    import traceback
                    traceback.print_exc()
        
        elif event.startswith("participant_events."):
            # Compact logging for participant events
            details = json.dumps(event_data, separators=(",", ":"), ensure_ascii=False)
            if len(details) > 500:
                details = details[:500] + "…"
            print(f'[bot-wh] {event} ts={timestamp} who={participant_name} details={details}')
        
        elif event == "bot.status_change":
            code = event_data.get("code")
            print(f'[bot-wh] ==========================================')
            print(f'[bot-wh] 🔄 BOT STATUS CHANGE')
            print(f'[bot-wh] Code: {code}')
            print(f'[bot-wh] Timestamp: {timestamp}')
            print(f'[bot-wh] Full event_data keys: {list(event_data.keys())}')
            print(f'[bot-wh] ==========================================')
            
            # Auto-retrieve when bot is done
            # Check multiple possible codes for bot completion
            completion_codes = ["bot.done", "recording_done", "done", "completed", "finished"]
            if code in completion_codes:
                if bot_id:
                    print(f'[bot-wh] ==========================================')
                    print(f'[bot-wh] 🎯 BOT COMPLETED: {bot_id}')
                    print(f'[bot-wh] Status code: {code}')
                    print(f'[bot-wh] Timestamp: {timestamp}')
                    print(f'[bot-wh] Triggering auto-retrieve and AssemblyAI transcript fetch...')
                    print(f'[bot-wh] ==========================================')
                    try:
                        # Import here to avoid circular imports
                        from app.logic.bot_retriever import auto_retrieve_bot
                        from app.models import CalendarEvent
                        from app.services.assemblyai.transcript_fetcher import (
                            get_assemblyai_transcript,
                            extract_assemblyai_transcript_id
                        )
                        from app.services.recall.service import get_service
                        
                        # Find calendar event with this bot_id
                        calendar_event = CalendarEvent.objects.filter(
                            recall_data__bots__bot_id=bot_id
                        ).first()
                        
                        calendar_event_id = str(calendar_event.id) if calendar_event else None
                        
                        # Trigger auto-retrieve and AssemblyAI transcript fetch (async/background)
                        # Use threading to avoid blocking webhook response
                        import threading
                        def retrieve_in_background():
                            print(f'[bot-wh] [BACKGROUND] Starting background processing for bot {bot_id}')
                            
                            # First, retrieve bot data
                            print(f'[bot-wh] [BACKGROUND] Step 1: Auto-retrieving bot data...')
                            result = auto_retrieve_bot(bot_id, calendar_event_id)
                            if result['success']:
                                print(f'[bot-wh] [BACKGROUND] ✓ Auto-retrieved bot {bot_id}')
                                print(f'[bot-wh] [BACKGROUND] Recording ID: {result.get("recording_id")}')
                                
                                # Now fetch AssemblyAI transcript
                                try:
                                    print(f'[bot-wh] [BACKGROUND] Step 2: Fetching bot data from Recall.ai...')
                                    # Get fresh bot data to find transcript ID
                                    recall_service = get_service()
                                    bot_json = recall_service.get_bot(bot_id)
                                    
                                    if bot_json:
                                        print(f'[bot-wh] [BACKGROUND] ✓ Retrieved bot data from Recall.ai')
                                        print(f'[bot-wh] [BACKGROUND] Bot status: {bot_json.get("status", "unknown")}')
                                        
                                        # Extract AssemblyAI transcript ID
                                        print(f'[bot-wh] [BACKGROUND] Step 3: Extracting AssemblyAI transcript ID...')
                                        transcript_id = extract_assemblyai_transcript_id(bot_json)
                                        
                                        if transcript_id:
                                            print(f'[bot-wh] [BACKGROUND] ✓ Found AssemblyAI transcript ID: {transcript_id}')
                                            print(f'[bot-wh] [BACKGROUND] Step 4: Fetching transcript from AssemblyAI...')
                                            
                                            # Fetch full transcript from AssemblyAI
                                            assemblyai_transcript = get_assemblyai_transcript(transcript_id)
                                            
                                            if assemblyai_transcript:
                                                print(f'[bot-wh] [BACKGROUND] ✓ Successfully fetched transcript from AssemblyAI')
                                                print(f'[bot-wh] [BACKGROUND] Transcript status: {assemblyai_transcript.get("status", "unknown")}')
                                                print(f'[bot-wh] [BACKGROUND] Transcript text length: {len(assemblyai_transcript.get("text", ""))} chars')
                                                print(f'[bot-wh] [BACKGROUND] Has summary: {bool(assemblyai_transcript.get("summary"))}')
                                                print(f'[bot-wh] [BACKGROUND] Utterances count: {len(assemblyai_transcript.get("utterances", []))}')
                                                print(f'[bot-wh] [BACKGROUND] Words count: {len(assemblyai_transcript.get("words", []))}')
                                                # Save transcript to database
                                                from app.models import BotRecording, MeetingTranscription
                                                
                                                print(f'[bot-wh] [BACKGROUND] Step 5: Saving transcript to database...')
                                                
                                                # Save to BotRecording (existing)
                                                bot_recording = BotRecording.objects.filter(bot_id=bot_id).first()
                                                
                                                if bot_recording:
                                                    print(f'[bot-wh] [BACKGROUND] Saving to BotRecording table...')
                                                    recall_data = bot_recording.recall_data.copy()
                                                    recall_data['assemblyai_transcript'] = assemblyai_transcript
                                                    recall_data['assemblyai_transcript_id'] = transcript_id
                                                    bot_recording.recall_data = recall_data
                                                    bot_recording.save()
                                                    print(f'[bot-wh] [BACKGROUND] ✓ Saved AssemblyAI transcript to BotRecording (ID: {bot_recording.id})')
                                                else:
                                                    print(f'[bot-wh] [BACKGROUND] ⚠ WARNING: BotRecording not found for bot {bot_id}')
                                                
                                                # Save to MeetingTranscription (new dedicated table)
                                                if calendar_event:
                                                    print(f'[bot-wh] [BACKGROUND] Saving to MeetingTranscription table...')
                                                    print(f'[bot-wh] [BACKGROUND] Calendar Event ID: {calendar_event.id}')
                                                    print(f'[bot-wh] [BACKGROUND] Event Title: {calendar_event.title or "Untitled"}')
                                                    
                                                    # Get or create MeetingTranscription (one per bot per event)
                                                    # Use calendar_event_id + bot_id as unique key (not assemblyai_transcript_id)
                                                    transcription, created = MeetingTranscription.objects.get_or_create(
                                                        calendar_event_id=calendar_event.id,
                                                        bot_id=bot_id,
                                                        defaults={
                                                            'assemblyai_transcript_id': transcript_id,
                                                            'transcript_data': assemblyai_transcript,
                                                            'transcript_text': assemblyai_transcript.get('text', ''),
                                                            'summary': assemblyai_transcript.get('summary', ''),
                                                            'status': 'completed' if assemblyai_transcript.get('status') == 'completed' else 'processing',
                                                            'language': assemblyai_transcript.get('language_code', 'en'),
                                                            'duration': assemblyai_transcript.get('audio_duration', None),
                                                        }
                                                    )
                                                    
                                                    if created:
                                                        print(f'[bot-wh] [BACKGROUND] ✓ Created new MeetingTranscription (ID: {transcription.id})')
                                                    else:
                                                        print(f'[bot-wh] [BACKGROUND] Updating existing MeetingTranscription (ID: {transcription.id})')
                                                        # Update existing transcription with final data from AssemblyAI
                                                        transcription.assemblyai_transcript_id = transcript_id
                                                        transcription.transcript_data = assemblyai_transcript
                                                        # Use AssemblyAI transcript text (more accurate than real-time)
                                                        transcription.transcript_text = assemblyai_transcript.get('text', '')
                                                        transcription.summary = assemblyai_transcript.get('summary', '')
                                                        transcription.status = 'completed' if assemblyai_transcript.get('status') == 'completed' else 'processing'
                                                        transcription.language = assemblyai_transcript.get('language_code', 'en')
                                                        transcription.duration = assemblyai_transcript.get('audio_duration', None)
                                                        transcription.save()
                                                        print(f'[bot-wh] [BACKGROUND] ✓ Updated MeetingTranscription with final transcript')
                                                    
                                                    print(f'[bot-wh] [BACKGROUND] Transcription saved with:')
                                                    print(f'[bot-wh] [BACKGROUND]   - Text length: {len(transcription.transcript_text or "")} chars')
                                                    print(f'[bot-wh] [BACKGROUND]   - Summary length: {len(transcription.summary or "")} chars')
                                                    print(f'[bot-wh] [BACKGROUND]   - Status: {transcription.status}')
                                                    print(f'[bot-wh] [BACKGROUND]   - Language: {transcription.language}')
                                                    print(f'[bot-wh] [BACKGROUND]   - Duration: {transcription.duration}s')
                                                    print(f'[bot-wh] [BACKGROUND] ==========================================')
                                                    print(f'[bot-wh] [BACKGROUND] ✅ TRANSCRIPTION PROCESSING COMPLETE')
                                                    print(f'[bot-wh] [BACKGROUND] ==========================================')
                                                else:
                                                    print(f'[bot-wh] [BACKGROUND] ⚠ WARNING: Calendar event not found for bot {bot_id}')
                                                    print(f'[bot-wh] [BACKGROUND] Calendar Event ID was: {calendar_event_id}')
                                            else:
                                                print(f'[bot-wh] [BACKGROUND] ⚠ WARNING: Failed to fetch AssemblyAI transcript')
                                                print(f'[bot-wh] [BACKGROUND] Transcript ID was: {transcript_id}')
                                        else:
                                            print(f'[bot-wh] [BACKGROUND] ℹ INFO: No AssemblyAI transcript ID found in bot data')
                                            print(f'[bot-wh] [BACKGROUND] This might mean AssemblyAI was not configured for this bot')
                                    else:
                                        print(f'[bot-wh] [BACKGROUND] ⚠ WARNING: Could not fetch bot data for transcript extraction')
                                except Exception as e:
                                    print(f'[bot-wh] [BACKGROUND] ❌ ERROR: Failed to fetch AssemblyAI transcript: {e}')
                                    import traceback
                                    traceback.print_exc()
                            else:
                                print(f'[bot-wh] [BACKGROUND] ⚠ Auto-retrieve failed for bot {bot_id}')
                                print(f'[bot-wh] [BACKGROUND] Error: {result.get("error")}')
                        
                        thread = threading.Thread(target=retrieve_in_background)
                        thread.daemon = True
                        thread.start()
                    except Exception as e:
                        print(f'[bot-wh] ERROR: Failed to trigger auto-retrieve: {e}')
                        import traceback
                        traceback.print_exc()
        
        else:
            # Log unknown events
            payload_str = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
            print(f'[bot-wh] event: {event} | payload: {(payload_str[:800] + "…") if len(payload_str) > 800 else payload_str}')
        
        # Return success quickly (do heavy work in background)
        return JsonResponse({"ok": True})
        
    except Exception as e:
        print(f'[bot-wh] ERROR: {e}')
        import traceback
        traceback.print_exc()
        # Still return 200 to prevent webhook retries
        return JsonResponse({"ok": False, "error": str(e)}, status=200)


@csrf_exempt
def bot_websocket_info(request):
    """
    Info endpoint for WebSocket connections.
    Returns WebSocket connection information.
    """
    if request.method != 'GET':
        return HttpResponse(status=405)
    
    # Check token if provided
    token = request.GET.get('token')
    expected_token = os.getenv('WS_TOKEN', 'dev-secret')
    
    if token != expected_token:
        return JsonResponse({"error": "Invalid token"}, status=401)
    
    # Return WebSocket connection info
    public_url = os.getenv('PUBLIC_URL', '')
    ws_url = None
    if public_url:
        if public_url.startswith('https://'):
            ws_url = public_url.replace('https://', 'wss://') + '/ws/rt?token=' + expected_token
        elif public_url.startswith('http://'):
            ws_url = public_url.replace('http://', 'ws://') + '/ws/rt?token=' + expected_token
    
    return JsonResponse({
        "message": "WebSocket endpoint available",
        "websocket_url": ws_url or "ws://localhost:3003/ws/rt?token=" + expected_token,
        "status": "ready"
    })

