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
    
    # Check AssemblyAI configuration (only log once per session to avoid spam)
    import os
    use_assembly_ai = os.getenv('USE_ASSEMBLY_AI', '').strip().lower() == 'true'
    assemblyai_api_key = os.getenv('ASSEMBLY_AI_API_KEY', '')
    
    # Log configuration status (only for first few webhooks to avoid spam)
    if not hasattr(bot_webhook, '_config_logged'):
        bot_webhook._config_logged = True
        print(f'[bot-wh] ==========================================')
        print(f'[bot-wh] 🔧 WEBHOOK HANDLER CONFIGURATION')
        print(f'[bot-wh] USE_ASSEMBLY_AI: {use_assembly_ai}')
        print(f'[bot-wh] ASSEMBLY_AI_API_KEY: {"✓ Set" if assemblyai_api_key else "✗ Not set"}')
        if not use_assembly_ai:
            print(f'[bot-wh] ⚠ WARNING: USE_ASSEMBLY_AI is not set to "true"')
            print(f'[bot-wh] ⚠ Real-time transcription may not work without AssemblyAI')
            print(f'[bot-wh] ⚠ Set USE_ASSEMBLY_AI=true in your .env file')
        print(f'[bot-wh] ==========================================')
    
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
            print(f'[bot-wh] Payload structure (first 2000 chars): {json.dumps(payload, indent=2)[:2000]}')
            print(f'[bot-wh] Event data keys: {list(event_data.keys()) if isinstance(event_data, dict) else "Not a dict"}')
        else:
            # Log full payload for transcript events to debug why they're not being received
            if event.startswith("transcript.") or event.startswith("bot."):
                print(f'[bot-wh] Full payload for {event}: {json.dumps(payload, indent=2)[:3000]}')
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
            # This matches the webhook.js implementation from the demo
            print(f'[bot-wh] [TRANSCRIPT] ✓ Received transcript event: {event}')
            
            # Extract data structure (as per demo: data.data contains the transcript data)
            transcript_data = event_data.get("data") or event_data
            words = transcript_data.get("words") or []
            participant = transcript_data.get("participant") or event_data.get("participant")
            transcript = transcript_data.get("transcript") or {}
            
            # Get participant name
            participant_name = None
            if isinstance(participant, dict):
                participant_name = participant.get("name") or participant.get("id")
            
            # Extract transcript text - try formatted text first, fall back to words (as per demo)
            transcript_text = ''
            if transcript_data.get("text"):
                transcript_text = transcript_data.get("text")
            elif transcript and transcript.get("text"):
                transcript_text = transcript.get("text")
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
                            
                            # Save both partial and final transcripts to database
                            # Partial transcripts allow real-time viewing, final transcripts are more accurate
                            print(f'[bot-wh] [TRANSCRIPT] Saving {event_type} transcript to database')
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
                                            'words': words,
                                            'type': event_type  # Mark as PARTIAL or FINAL
                                        }]
                                    },
                                    'transcript_text': f"{participant_name}: {transcript_text}",
                                    'status': 'processing',
                                }
                            )
                            
                            if created:
                                print(f'[bot-wh] [TRANSCRIPT] ✓ Created new transcription record in database (ID: {transcription.id})')
                                print(f'[bot-wh] [TRANSCRIPT]   Saved to table: meeting_transcriptions')
                            else:
                                # Append to existing transcription
                                print(f'[bot-wh] [TRANSCRIPT] Updating existing transcription in database (ID: {transcription.id})')
                                utterances = transcription.transcript_data.get('utterances', [])
                                
                                # Check if this utterance already exists (avoid duplicates)
                                utterance_exists = any(
                                    u.get('text') == transcript_text and 
                                    u.get('speaker') == participant_name and
                                    u.get('start') == timestamp
                                    for u in utterances
                                )
                                
                                if not utterance_exists:
                                    utterances.append({
                                        'speaker': participant_name,
                                        'text': transcript_text,
                                        'start': timestamp,
                                        'words': words,
                                        'type': event_type  # Mark as PARTIAL or FINAL
                                    })
                                    transcription.transcript_data['utterances'] = utterances
                                    # Append to transcript text
                                    if transcription.transcript_text:
                                        transcription.transcript_text += f"\n{participant_name}: {transcript_text}"
                                    else:
                                        transcription.transcript_text = f"{participant_name}: {transcript_text}"
                                    transcription.save()
                                    print(f'[bot-wh] [TRANSCRIPT] ✓ Updated transcript in database (now {len(utterances)} utterances)')
                                    print(f'[bot-wh] [TRANSCRIPT]   Database record updated successfully')
                                else:
                                    print(f'[bot-wh] [TRANSCRIPT] ⚠ Duplicate utterance skipped (already in database)')
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
        
            # If participant leaves and it's the last participant, check if bot is done
            if event == "participant_events.leave" and bot_id:
                # Check if we should trigger transcript fetch (fallback if bot.done never comes)
                try:
                    from app.models import BotRecording
                    from app.services.recall.service import get_service
                    import threading
                    
                    # Check bot status in background after a delay
                    def check_bot_status_after_delay():
                        import time
                        time.sleep(10)  # Wait 10 seconds after last participant leaves
                        
                        try:
                            recall_service = get_service()
                            bot_json = recall_service.get_bot(bot_id)
                            
                            if bot_json:
                                status = bot_json.get("status", "")
                                status_changes = bot_json.get("status_changes", [])
                                last_status = status_changes[-1].get("code", "") if status_changes else ""
                                
                                print(f'[bot-wh] [FALLBACK] Checking bot status after participant leave...')
                                print(f'[bot-wh] [FALLBACK] Bot status: {status}, Last status change: {last_status}')
                                
                                # If bot is done but we haven't processed it, trigger transcript fetch
                                # Check multiple variations of "done" status
                                is_done = (
                                    status == "done" or 
                                    last_status == "bot.done" or 
                                    last_status == "done" or
                                    status == "completed" or
                                    last_status == "completed"
                                )
                                if is_done:
                                    print(f'[bot-wh] [FALLBACK] Bot is done! Triggering transcript fetch...')
                                    # Trigger the same processing as bot.done webhook
                                    from app.logic.bot_retriever import auto_retrieve_bot
                                    from app.models import CalendarEvent
                                    from app.services.assemblyai.transcript_fetcher import (
                                        get_assemblyai_transcript,
                                        extract_assemblyai_transcript_id,
                                        get_audio_url_from_bot,
                                        submit_audio_for_transcription_with_summary
                                    )
                                    from app.services.groq.summary_generator import generate_summary_and_action_items_with_groq
                                    
                                    # Find calendar event
                                    bot_recording = BotRecording.objects.filter(bot_id=bot_id).first()
                                    calendar_event = None
                                    if bot_recording and bot_recording.calendar_event_id:
                                        calendar_event = CalendarEvent.objects.filter(id=bot_recording.calendar_event_id).first()
                                    
                                    if not calendar_event:
                                        calendar_event = CalendarEvent.objects.filter(
                                            recall_data__bots__bot_id=bot_id
                                        ).first()
                                    
                                    if calendar_event:
                                        calendar_event_id = str(calendar_event.id)
                                        result = auto_retrieve_bot(bot_id, calendar_event_id)
                                        if result.get('success'):
                                            print(f'[bot-wh] [FALLBACK] Auto-retrieve successful, fetching fresh bot data...')
                                            # Get fresh bot data after auto-retrieve (bot_json from outer scope might be stale)
                                            fresh_bot_json = recall_service.get_bot(bot_id)
                                            if fresh_bot_json:
                                                bot_json = fresh_bot_json
                                                print(f'[bot-wh] [FALLBACK] Got fresh bot data')
                                            
                                            print(f'[bot-wh] [FALLBACK] Extracting transcript ID from bot data...')
                                            print(f'[bot-wh] [FALLBACK] Bot data keys: {list(bot_json.keys()) if bot_json else "None"}')
                                            transcript_id = extract_assemblyai_transcript_id(bot_json)
                                            assemblyai_transcript = None
                                            
                                            if transcript_id:
                                                print(f'[bot-wh] [FALLBACK] ✓ Found transcript ID: {transcript_id}')
                                                print(f'[bot-wh] [FALLBACK] Fetching transcript from AssemblyAI...')
                                                assemblyai_transcript = get_assemblyai_transcript(transcript_id)
                                                
                                                # If fetching failed (e.g., 400 error), the ID might be from Recall.ai, not AssemblyAI
                                                if not assemblyai_transcript:
                                                    print(f'[bot-wh] [FALLBACK] ⚠ WARNING: Failed to fetch transcript from AssemblyAI')
                                                    print(f'[bot-wh] [FALLBACK] The ID might be from Recall.ai, not AssemblyAI')
                                                    print(f'[bot-wh] [FALLBACK] Will use existing transcript text and generate summary/action_items with LeMUR')
                                                    transcript_id = None  # Clear invalid ID
                                                    assemblyai_transcript = None  # Ensure it's None
                                            
                                            # If no transcript ID or transcript doesn't have summary/action_items, try to generate them
                                            needs_summary_or_action_items = (
                                                not transcript_id or 
                                                not assemblyai_transcript or
                                                (assemblyai_transcript and (not assemblyai_transcript.get("summary") or not assemblyai_transcript.get("action_items")))
                                            )
                                            
                                            if needs_summary_or_action_items:
                                                print(f'[bot-wh] [FALLBACK] Attempting to get summary/action_items from audio file...')
                                                audio_url = get_audio_url_from_bot(bot_json)
                                                if audio_url:
                                                    print(f'[bot-wh] [FALLBACK] Found audio URL, submitting to AssemblyAI with summarization...')
                                                    new_transcript_id = submit_audio_for_transcription_with_summary(audio_url)
                                                    if new_transcript_id:
                                                        import time
                                                        time.sleep(10)
                                                        enhanced_transcript = get_assemblyai_transcript(new_transcript_id)
                                                        if enhanced_transcript:
                                                            if not assemblyai_transcript:
                                                                assemblyai_transcript = enhanced_transcript
                                                                transcript_id = new_transcript_id
                                                            else:
                                                                # Merge summary and action_items
                                                                if enhanced_transcript.get("summary"):
                                                                    assemblyai_transcript["summary"] = enhanced_transcript.get("summary")
                                                                if enhanced_transcript.get("action_items"):
                                                                    assemblyai_transcript["action_items"] = enhanced_transcript.get("action_items")
                                                            print(f'[bot-wh] [FALLBACK] ✓ Got transcript with summary and action items')
                                                else:
                                                    # Use existing transcript text from database and generate with Groq
                                                    from app.models import MeetingTranscription
                                                    existing_transcription = MeetingTranscription.objects.filter(
                                                        calendar_event_id=calendar_event.id,
                                                        bot_id=bot_id
                                                    ).first()
                                                    
                                                    if existing_transcription and existing_transcription.transcript_text:
                                                        transcript_text = existing_transcription.transcript_text
                                                        print(f'[bot-wh] [FALLBACK] Using existing transcript text from database ({len(transcript_text)} chars)')
                                                        print(f'[bot-wh] [FALLBACK] Generating summary/action_items with Groq API...')
                                                        
                                                        # Import Groq service
                                                        from app.services.groq.summary_generator import generate_summary_and_action_items_with_groq
                                                        
                                                        groq_result = generate_summary_and_action_items_with_groq(transcript_text)
                                                        if groq_result:
                                                            if not assemblyai_transcript:
                                                                # Create a minimal transcript structure
                                                                assemblyai_transcript = {
                                                                    "text": transcript_text,
                                                                    "status": "completed"
                                                                }
                                                            if groq_result.get("summary"):
                                                                assemblyai_transcript["summary"] = groq_result.get("summary")
                                                            if groq_result.get("action_items"):
                                                                assemblyai_transcript["action_items"] = groq_result.get("action_items")
                                                            print(f'[bot-wh] [FALLBACK] ✓ Generated summary and action items using Groq')
                                                        else:
                                                            print(f'[bot-wh] [FALLBACK] ⚠ WARNING: Failed to generate summary/action_items with Groq')
                                                    else:
                                                        print(f'[bot-wh] [FALLBACK] ⚠ WARNING: No transcript text available in database')
                                            
                                            if assemblyai_transcript:
                                                    # Save transcript (same logic as bot.done handler)
                                                    from app.models import MeetingTranscription
                                                    # Extract action items
                                                    action_items = assemblyai_transcript.get('action_items', [])
                                                    
                                                    transcription, created = MeetingTranscription.objects.get_or_create(
                                                        calendar_event_id=calendar_event.id,
                                                        bot_id=bot_id,
                                                        defaults={
                                                            'assemblyai_transcript_id': transcript_id,
                                                            'transcript_data': assemblyai_transcript,
                                                            'transcript_text': assemblyai_transcript.get('text', ''),
                                                            'summary': assemblyai_transcript.get('summary', ''),
                                                            'action_items': action_items,
                                                            'status': 'completed' if assemblyai_transcript.get('status') == 'completed' else 'processing',
                                                            'language': assemblyai_transcript.get('language_code', 'en'),
                                                            'duration': assemblyai_transcript.get('audio_duration', None),
                                                        }
                                                    )
                                                    if not created:
                                                        # Preserve existing utterances from real-time transcripts
                                                        existing_utterances = transcription.transcript_data.get('utterances', [])
                                                        existing_words = transcription.transcript_data.get('words', [])
                                                        
                                                        # Merge with new data, preserving utterances
                                                        if existing_utterances:
                                                            assemblyai_transcript['utterances'] = existing_utterances
                                                        if existing_words:
                                                            assemblyai_transcript['words'] = existing_words
                                                        
                                                        transcription.assemblyai_transcript_id = transcript_id
                                                        transcription.transcript_data = assemblyai_transcript
                                                        # Keep existing transcript_text if it's longer (from real-time)
                                                        if transcription.transcript_text and len(transcription.transcript_text) > len(assemblyai_transcript.get('text', '')):
                                                            pass  # Keep existing
                                                        else:
                                                            transcription.transcript_text = assemblyai_transcript.get('text', '') or transcription.transcript_text
                                                        transcription.summary = assemblyai_transcript.get('summary', '') or transcription.summary
                                                        transcription.action_items = action_items or transcription.action_items
                                                        transcription.status = 'completed' if assemblyai_transcript.get('status') == 'completed' else 'processing'
                                                        transcription.save()
                                                        print(f'[bot-wh] [FALLBACK] ✓ Updated transcription (preserved {len(existing_utterances)} utterances)')
                                                    else:
                                                        print(f'[bot-wh] [FALLBACK] ✓ Created new transcription')
                                                    print(f'[bot-wh] [FALLBACK] ✓ Transcript saved via fallback mechanism')
                        except Exception as e:
                            print(f'[bot-wh] [FALLBACK] Error checking bot status: {e}')
                            import traceback
                            traceback.print_exc()
                    
                    thread = threading.Thread(target=check_bot_status_after_delay)
                    thread.daemon = True
                    thread.start()
                except Exception as e:
                    print(f'[bot-wh] Error setting up fallback check: {e}')
        
        elif event == "bot.status_change" or event.startswith("bot."):
            # Handle bot status changes - could be "bot.status_change" or "bot.done" directly
            code = event_data.get("code") or event.replace("bot.", "")
            print(f'[bot-wh] ==========================================')
            print(f'[bot-wh] 🔄 BOT STATUS CHANGE')
            print(f'[bot-wh] Event: {event}')
            print(f'[bot-wh] Code: {code}')
            print(f'[bot-wh] Timestamp: {timestamp}')
            print(f'[bot-wh] Full event_data keys: {list(event_data.keys())}')
            print(f'[bot-wh] Full payload: {json.dumps(payload, indent=2)[:2000]}')
            print(f'[bot-wh] ==========================================')
            
            # Auto-retrieve when bot is done
            # Check multiple possible codes for bot completion
            completion_codes = ["bot.done", "recording_done", "done", "completed", "finished"]
            # Also check if event itself is "bot.done"
            is_complete = code in completion_codes or event == "bot.done"
            if is_complete:
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
                                                print(f'[bot-wh] [BACKGROUND] Has action items: {bool(assemblyai_transcript.get("action_items"))}')
                                                
                                                # Check if summary/action_items are missing - if so, try to generate them
                                                has_summary = bool(assemblyai_transcript.get("summary"))
                                                has_action_items = bool(assemblyai_transcript.get("action_items"))
                                                
                                                if not has_summary or not has_action_items:
                                                    print(f'[bot-wh] [BACKGROUND] ⚠ Summary or action items missing, attempting to generate...')
                                                    
                                                    # Try to get audio URL and submit for transcription with summary/action_items
                                                    audio_url = get_audio_url_from_bot(bot_json)
                                                    if audio_url:
                                                        print(f'[bot-wh] [BACKGROUND] Found audio URL, submitting to AssemblyAI with summarization...')
                                                        new_transcript_id = submit_audio_for_transcription_with_summary(audio_url)
                                                        if new_transcript_id:
                                                            print(f'[bot-wh] [BACKGROUND] Audio submitted, fetching transcript with summary/action_items...')
                                                            # Wait a bit for processing
                                                            import time
                                                            time.sleep(5)
                                                            enhanced_transcript = get_assemblyai_transcript(new_transcript_id)
                                                            if enhanced_transcript:
                                                                # Merge summary and action_items if available
                                                                if enhanced_transcript.get("summary") and not has_summary:
                                                                    assemblyai_transcript["summary"] = enhanced_transcript.get("summary")
                                                                    print(f'[bot-wh] [BACKGROUND] ✓ Added summary from enhanced transcript')
                                                                if enhanced_transcript.get("action_items") and not has_action_items:
                                                                    assemblyai_transcript["action_items"] = enhanced_transcript.get("action_items")
                                                                    print(f'[bot-wh] [BACKGROUND] ✓ Added action items from enhanced transcript')
                                                    else:
                                                        # Fallback: Use Groq API to generate from transcript text
                                                        print(f'[bot-wh] [BACKGROUND] No audio URL, using Groq API to generate summary/action_items...')
                                                        transcript_text = assemblyai_transcript.get("text", "")
                                                        if not transcript_text:
                                                            # Get from database if not in transcript
                                                            from app.models import MeetingTranscription
                                                            existing_transcription = MeetingTranscription.objects.filter(
                                                                calendar_event_id=calendar_event.id,
                                                                bot_id=bot_id
                                                            ).first()
                                                            if existing_transcription and existing_transcription.transcript_text:
                                                                transcript_text = existing_transcription.transcript_text
                                                        
                                                        if transcript_text:
                                                            from app.services.groq.summary_generator import generate_summary_and_action_items_with_groq
                                                            groq_result = generate_summary_and_action_items_with_groq(transcript_text)
                                                            if groq_result:
                                                                if groq_result.get("summary") and not has_summary:
                                                                    assemblyai_transcript["summary"] = groq_result.get("summary")
                                                                    print(f'[bot-wh] [BACKGROUND] ✓ Generated summary using Groq')
                                                                if groq_result.get("action_items") and not has_action_items:
                                                                    assemblyai_transcript["action_items"] = groq_result.get("action_items")
                                                                    print(f'[bot-wh] [BACKGROUND] ✓ Generated action items using Groq')
                                                
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
                                                    # Extract action items from AssemblyAI transcript
                                                    action_items = assemblyai_transcript.get('action_items', [])
                                                    
                                                    transcription, created = MeetingTranscription.objects.get_or_create(
                                                        calendar_event_id=calendar_event.id,
                                                        bot_id=bot_id,
                                                        defaults={
                                                            'assemblyai_transcript_id': transcript_id,
                                                            'transcript_data': assemblyai_transcript,
                                                            'transcript_text': assemblyai_transcript.get('text', ''),
                                                            'summary': assemblyai_transcript.get('summary', ''),
                                                            'action_items': action_items,
                                                            'status': 'completed' if assemblyai_transcript.get('status') == 'completed' else 'processing',
                                                            'language': assemblyai_transcript.get('language_code', 'en'),
                                                            'duration': assemblyai_transcript.get('audio_duration', None),
                                                        }
                                                    )
                                                    
                                                    if created:
                                                        print(f'[bot-wh] [BACKGROUND] ✓ Created new MeetingTranscription (ID: {transcription.id})')
                                                    else:
                                                        print(f'[bot-wh] [BACKGROUND] Updating existing MeetingTranscription (ID: {transcription.id})')
                                                        # Preserve existing utterances from real-time transcripts
                                                        existing_utterances = transcription.transcript_data.get('utterances', [])
                                                        existing_words = transcription.transcript_data.get('words', [])
                                                        
                                                        # Merge with new data, preserving utterances
                                                        if existing_utterances:
                                                            assemblyai_transcript['utterances'] = existing_utterances
                                                        if existing_words:
                                                            assemblyai_transcript['words'] = existing_words
                                                        
                                                        # Update existing transcription with final data from AssemblyAI
                                                        transcription.assemblyai_transcript_id = transcript_id
                                                        transcription.transcript_data = assemblyai_transcript
                                                        # Keep existing transcript_text if it's longer (from real-time)
                                                        if transcription.transcript_text and len(transcription.transcript_text) > len(assemblyai_transcript.get('text', '')):
                                                            pass  # Keep existing
                                                        else:
                                                            transcription.transcript_text = assemblyai_transcript.get('text', '') or transcription.transcript_text
                                                        transcription.summary = assemblyai_transcript.get('summary', '') or transcription.summary
                                                        transcription.action_items = action_items or transcription.action_items
                                                        transcription.status = 'completed' if assemblyai_transcript.get('status') == 'completed' else 'processing'
                                                        transcription.language = assemblyai_transcript.get('language_code', 'en') or transcription.language
                                                        transcription.duration = assemblyai_transcript.get('audio_duration', None) or transcription.duration
                                                        transcription.save()
                                                        print(f'[bot-wh] [BACKGROUND] ✓ Updated MeetingTranscription with final transcript (preserved {len(existing_utterances)} utterances)')
                                                    
                                                    print(f'[bot-wh] [BACKGROUND] Transcription saved with:')
                                                    print(f'[bot-wh] [BACKGROUND]   - Text length: {len(transcription.transcript_text or "")} chars')
                                                    print(f'[bot-wh] [BACKGROUND]   - Summary length: {len(transcription.summary or "")} chars')
                                                    print(f'[bot-wh] [BACKGROUND]   - Action items: {len(action_items)} items')
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
                                            print(f'[bot-wh] [BACKGROUND] Attempting to get summary/action_items from audio file...')
                                            
                                            # Try to get audio URL and submit for transcription with summary/action_items
                                            audio_url = get_audio_url_from_bot(bot_json)
                                            if audio_url:
                                                print(f'[bot-wh] [BACKGROUND] Found audio URL, submitting to AssemblyAI...')
                                                new_transcript_id = submit_audio_for_transcription_with_summary(audio_url)
                                                if new_transcript_id:
                                                    print(f'[bot-wh] [BACKGROUND] Audio submitted, waiting for processing...')
                                                    # Wait for processing
                                                    import time
                                                    time.sleep(10)  # Wait 10 seconds
                                                    
                                                    # Fetch the transcript with summary and action items
                                                    enhanced_transcript = get_assemblyai_transcript(new_transcript_id)
                                                    if enhanced_transcript:
                                                        print(f'[bot-wh] [BACKGROUND] ✓ Got transcript with summary and action items')
                                                        # Use this transcript instead
                                                        assemblyai_transcript = enhanced_transcript
                                                        transcript_id = new_transcript_id
                                                        
                                                        # Save to database (same logic as above)
                                                        from app.models import BotRecording, MeetingTranscription
                                                        action_items = assemblyai_transcript.get('action_items', [])
                                                        
                                                        if calendar_event:
                                                            transcription, created = MeetingTranscription.objects.get_or_create(
                                                                calendar_event_id=calendar_event.id,
                                                                bot_id=bot_id,
                                                                defaults={
                                                                    'assemblyai_transcript_id': transcript_id,
                                                                    'transcript_data': assemblyai_transcript,
                                                                    'transcript_text': assemblyai_transcript.get('text', ''),
                                                                    'summary': assemblyai_transcript.get('summary', ''),
                                                                    'action_items': action_items,
                                                                    'status': 'completed',
                                                                    'language': assemblyai_transcript.get('language_code', 'en'),
                                                                    'duration': assemblyai_transcript.get('audio_duration', None),
                                                                }
                                                            )
                                                            if not created:
                                                                # Preserve existing utterances from real-time transcripts
                                                                existing_utterances = transcription.transcript_data.get('utterances', [])
                                                                existing_words = transcription.transcript_data.get('words', [])
                                                                
                                                                # Merge with new data, preserving utterances
                                                                if existing_utterances:
                                                                    assemblyai_transcript['utterances'] = existing_utterances
                                                                if existing_words:
                                                                    assemblyai_transcript['words'] = existing_words
                                                                
                                                                transcription.assemblyai_transcript_id = transcript_id
                                                                transcription.transcript_data = assemblyai_transcript
                                                                # Keep existing transcript_text if it's longer
                                                                if transcription.transcript_text and len(transcription.transcript_text) > len(assemblyai_transcript.get('text', '')):
                                                                    pass  # Keep existing
                                                                else:
                                                                    transcription.transcript_text = assemblyai_transcript.get('text', '') or transcription.transcript_text
                                                                transcription.summary = assemblyai_transcript.get('summary', '') or transcription.summary
                                                                transcription.action_items = action_items or transcription.action_items
                                                                transcription.status = 'completed'
                                                                transcription.save()
                                                                print(f'[bot-wh] [BACKGROUND] ✓ Updated transcript (preserved {len(existing_utterances)} utterances)')
                                                            else:
                                                                print(f'[bot-wh] [BACKGROUND] ✓ Created new transcript')
                                                            print(f'[bot-wh] [BACKGROUND] ✓ Saved transcript with summary and action items')
                                                    else:
                                                        print(f'[bot-wh] [BACKGROUND] ⚠ Transcript not ready yet, will be processed later')
                                            else:
                                                print(f'[bot-wh] [BACKGROUND] ⚠ No audio URL found, cannot generate summary/action_items')
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
            # Log unknown events - this helps us see what events we're missing
            payload_str = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
            print(f'[bot-wh] ⚠ UNKNOWN EVENT: {event}')
            print(f'[bot-wh] Payload: {(payload_str[:1500] + "…") if len(payload_str) > 1500 else payload_str}')
            
            # Check if this might be a transcript event with different naming
            if "transcript" in event.lower() or "transcript" in payload_str.lower():
                print(f'[bot-wh] ⚠ WARNING: This might be a transcript event but wasn\'t recognized!')
                print(f'[bot-wh] Please check if transcript events are being sent with a different event name.')
            
            # Check if this might be a bot.done event with different naming
            if "done" in event.lower() or "done" in payload_str.lower() or "completed" in event.lower():
                print(f'[bot-wh] ⚠ WARNING: This might be a bot completion event but wasn\'t recognized!')
                print(f'[bot-wh] Attempting to process as bot.done...')
                # Try to process as bot.done
                try:
                    if bot_id:
                        from app.logic.bot_retriever import auto_retrieve_bot
                        from app.models import CalendarEvent, BotRecording
                        from app.services.assemblyai.transcript_fetcher import (
                            get_assemblyai_transcript,
                            extract_assemblyai_transcript_id
                        )
                        from app.services.recall.service import get_service
                        import threading
                        
                        def process_bot_done():
                            try:
                                # Find calendar event
                                bot_recording = BotRecording.objects.filter(bot_id=bot_id).first()
                                calendar_event = None
                                if bot_recording and bot_recording.calendar_event_id:
                                    calendar_event = CalendarEvent.objects.filter(id=bot_recording.calendar_event_id).first()
                                
                                if not calendar_event:
                                    calendar_event = CalendarEvent.objects.filter(
                                        recall_data__bots__bot_id=bot_id
                                    ).first()
                                
                                if calendar_event:
                                    calendar_event_id = str(calendar_event.id)
                                    result = auto_retrieve_bot(bot_id, calendar_event_id)
                                    if result.get('success'):
                                        recall_service = get_service()
                                        bot_json = recall_service.get_bot(bot_id)
                                        if bot_json:
                                            transcript_id = extract_assemblyai_transcript_id(bot_json)
                                            assemblyai_transcript = None
                                            
                                            if transcript_id:
                                                assemblyai_transcript = get_assemblyai_transcript(transcript_id)
                                            
                                            # If no transcript ID or missing summary/action_items, try to generate them
                                            if not transcript_id or (assemblyai_transcript and (not assemblyai_transcript.get("summary") or not assemblyai_transcript.get("action_items"))):
                                                audio_url = get_audio_url_from_bot(bot_json)
                                                if audio_url:
                                                    new_transcript_id = submit_audio_for_transcription_with_summary(audio_url)
                                                    if new_transcript_id:
                                                        import time
                                                        time.sleep(10)
                                                        enhanced = get_assemblyai_transcript(new_transcript_id)
                                                        if enhanced:
                                                            if not assemblyai_transcript:
                                                                assemblyai_transcript = enhanced
                                                                transcript_id = new_transcript_id
                                                            else:
                                                                if enhanced.get("summary"):
                                                                    assemblyai_transcript["summary"] = enhanced.get("summary")
                                                                if enhanced.get("action_items"):
                                                                    assemblyai_transcript["action_items"] = enhanced.get("action_items")
                                                else:
                                                    # Use Groq API to generate from transcript text
                                                    transcript_text = assemblyai_transcript.get("text", "") if assemblyai_transcript else ""
                                                    if not transcript_text:
                                                        # Get from database if not in transcript
                                                        from app.models import MeetingTranscription
                                                        existing_transcription = MeetingTranscription.objects.filter(
                                                            calendar_event_id=calendar_event.id,
                                                            bot_id=bot_id
                                                        ).first()
                                                        if existing_transcription and existing_transcription.transcript_text:
                                                            transcript_text = existing_transcription.transcript_text
                                                    
                                                    if transcript_text:
                                                        from app.services.groq.summary_generator import generate_summary_and_action_items_with_groq
                                                        groq_result = generate_summary_and_action_items_with_groq(transcript_text)
                                                        if groq_result:
                                                            if not assemblyai_transcript:
                                                                assemblyai_transcript = {"text": transcript_text, "status": "completed"}
                                                            if groq_result.get("summary"):
                                                                assemblyai_transcript["summary"] = groq_result.get("summary")
                                                            if groq_result.get("action_items"):
                                                                assemblyai_transcript["action_items"] = groq_result.get("action_items")
                                                            print(f'[bot-wh] ✓ Generated summary and action items using Groq')
                                            
                                            if assemblyai_transcript:
                                                from app.models import MeetingTranscription
                                                # Extract action items
                                                action_items = assemblyai_transcript.get('action_items', [])
                                                
                                                transcription, created = MeetingTranscription.objects.get_or_create(
                                                    calendar_event_id=calendar_event.id,
                                                    bot_id=bot_id,
                                                    defaults={
                                                        'assemblyai_transcript_id': transcript_id,
                                                        'transcript_data': assemblyai_transcript,
                                                        'transcript_text': assemblyai_transcript.get('text', ''),
                                                        'summary': assemblyai_transcript.get('summary', ''),
                                                        'action_items': action_items,
                                                        'status': 'completed' if assemblyai_transcript.get('status') == 'completed' else 'processing',
                                                        'language': assemblyai_transcript.get('language_code', 'en'),
                                                        'duration': assemblyai_transcript.get('audio_duration', None),
                                                    }
                                                )
                                                if not created:
                                                    # Preserve existing utterances from real-time transcripts
                                                    existing_utterances = transcription.transcript_data.get('utterances', [])
                                                    existing_words = transcription.transcript_data.get('words', [])
                                                    
                                                    # Merge with new data, preserving utterances
                                                    if existing_utterances:
                                                        assemblyai_transcript['utterances'] = existing_utterances
                                                    if existing_words:
                                                        assemblyai_transcript['words'] = existing_words
                                                    
                                                    transcription.assemblyai_transcript_id = transcript_id
                                                    transcription.transcript_data = assemblyai_transcript
                                                    # Keep existing transcript_text if it's longer
                                                    if transcription.transcript_text and len(transcription.transcript_text) > len(assemblyai_transcript.get('text', '')):
                                                        pass  # Keep existing
                                                    else:
                                                        transcription.transcript_text = assemblyai_transcript.get('text', '') or transcription.transcript_text
                                                    transcription.summary = assemblyai_transcript.get('summary', '') or transcription.summary
                                                    transcription.action_items = action_items or transcription.action_items
                                                    transcription.status = 'completed' if assemblyai_transcript.get('status') == 'completed' else 'processing'
                                                    transcription.save()
                                                    print(f'[bot-wh] ✓ Updated transcript (preserved {len(existing_utterances)} utterances)')
                                                print(f'[bot-wh] ✓ Processed unknown event as bot.done and saved transcript')
                            except Exception as e:
                                print(f'[bot-wh] Error processing unknown event as bot.done: {e}')
                                import traceback
                                traceback.print_exc()
                        
                        thread = threading.Thread(target=process_bot_done)
                        thread.daemon = True
                        thread.start()
                except Exception as e:
                    print(f'[bot-wh] Error setting up bot.done processing: {e}')
        
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

