"""
Webhook handlers for Recall.ai bot events (transcripts, participant events, etc.)
These are different from calendar webhooks - these come from bots during meetings.
"""
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json
import os

# Import transcript fetcher functions at module level to avoid import errors in background threads
try:
    from app.services.assemblyai.transcript_fetcher import (
        get_assemblyai_transcript,
        extract_assemblyai_transcript_id
    )
except ImportError as e:
    print(f'[bot-wh] ⚠ WARNING: Could not import transcript_fetcher functions: {e}')
    print(f'[bot-wh] Some features may not work correctly. Please check transcript_fetcher.py exists.')
    # Define stubs to prevent crashes
    def get_assemblyai_transcript(*args, **kwargs):
        print('[bot-wh] ERROR: get_assemblyai_transcript not available')
        return None
    def extract_assemblyai_transcript_id(*args, **kwargs):
        print('[bot-wh] ERROR: extract_assemblyai_transcript_id not available')
        return None


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
                            
                            # Get backend_user_id from calendar_event
                            backend_user_id = calendar_event.backend_user_id
                            if not backend_user_id and calendar_event.calendar_id:
                                # Fallback: get from calendar
                                from app.models import Calendar
                                try:
                                    calendar = Calendar.objects.get(id=calendar_event.calendar_id)
                                    backend_user_id = calendar.backend_user_id
                                except Calendar.DoesNotExist:
                                    pass
                            
                            # Get or create transcription record (one per bot per event)
                            transcription, created = MeetingTranscription.objects.get_or_create(
                                calendar_event_id=calendar_event.id,
                                bot_id=bot_id,
                                defaults={
                                    'backend_user_id': backend_user_id,  # Set backend_user_id
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
                            
                            # Update backend_user_id if it wasn't set (for existing records)
                            if not transcription.backend_user_id and backend_user_id:
                                transcription.backend_user_id = backend_user_id
                                transcription.save(update_fields=['backend_user_id'])
                            
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
                                    
                                    # If this is a FINAL transcript, trigger a delayed check to generate summary/action items
                                    # This is a fallback if bot.done event never comes
                                    if event == "transcript.data":  # FINAL transcript
                                        print(f'[bot-wh] [TRANSCRIPT] Final transcript received, will check for summary generation after delay...')
                                        import threading
                                        
                                        def delayed_summary_check():
                                            import time
                                            # Wait 30 seconds after last transcript to see if meeting has ended
                                            time.sleep(30)
                                            
                                            try:
                                                from app.models import MeetingTranscription, CalendarEvent
                                                from app.services.groq.summary_generator import generate_summary_and_action_items_with_groq
                                                from app.logic.bot_retriever import auto_retrieve_bot
                                                
                                                # Re-fetch transcription to check if summary already exists
                                                transcription_check = MeetingTranscription.objects.filter(
                                                    calendar_event_id=calendar_event.id,
                                                    bot_id=bot_id
                                                ).first()
                                                
                                                if transcription_check:
                                                    # Only generate if summary doesn't exist yet
                                                    if not transcription_check.summary or len(transcription_check.summary.strip()) == 0:
                                                        print(f'[bot-wh] [DELAYED CHECK] No summary found, generating with Groq...')
                                                        
                                                        if transcription_check.transcript_text and len(transcription_check.transcript_text.strip()) > 0:
                                                            calendar_event_id = str(calendar_event.id)
                                                            
                                                            # Auto-retrieve bot first
                                                            auto_retrieve_bot(bot_id, calendar_event_id)
                                                            
                                                            # Generate summary and action items
                                                            groq_result = generate_summary_and_action_items_with_groq(transcription_check.transcript_text)
                                                            
                                                            if groq_result:
                                                                summary = groq_result.get("summary", "")
                                                                action_items = groq_result.get("action_items", [])
                                                                
                                                                transcript_data = transcription_check.transcript_data.copy() if transcription_check.transcript_data else {}
                                                                transcript_data['summary'] = summary
                                                                transcript_data['action_items'] = action_items
                                                                
                                                                transcription_check.summary = summary
                                                                transcription_check.action_items = action_items
                                                                transcription_check.status = 'completed'
                                                                transcription_check.transcript_data = transcript_data
                                                                transcription_check.save()
                                                                
                                                                print(f'[bot-wh] [DELAYED CHECK] ✓ Generated and saved summary ({len(summary)} chars) and {len(action_items)} action items')
                                                                print(f'[bot-wh] [DELAYED CHECK] ==========================================')
                                                                print(f'[bot-wh] [DELAYED CHECK] ✅ TRANSCRIPTION PROCESSING COMPLETE (via delayed check)')
                                                                print(f'[bot-wh] [DELAYED CHECK] ==========================================')
                                                            else:
                                                                print(f'[bot-wh] [DELAYED CHECK] ⚠ Failed to generate summary with Groq')
                                                        else:
                                                            print(f'[bot-wh] [DELAYED CHECK] ⚠ No transcript text available for summary generation')
                                                    else:
                                                        print(f'[bot-wh] [DELAYED CHECK] ℹ Summary already exists (possibly generated by bot.done), skipping')
                                            except Exception as e:
                                                print(f'[bot-wh] [DELAYED CHECK] Error in delayed summary check: {e}')
                                                import traceback
                                                traceback.print_exc()
                                        
                                        thread = threading.Thread(target=delayed_summary_check)
                                        thread.daemon = True
                                        thread.start()
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
                                    # Functions are already imported at module level
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
                                            print(f'[bot-wh] [FALLBACK] Auto-retrieve successful')
                                            
                                            # Get transcript text from database (saved during real-time meeting)
                                            from app.models import MeetingTranscription
                                            existing_transcription = MeetingTranscription.objects.filter(
                                                calendar_event_id=calendar_event.id,
                                                bot_id=bot_id
                                            ).first()
                                            
                                            if existing_transcription and existing_transcription.transcript_text:
                                                transcript_text = existing_transcription.transcript_text
                                                print(f'[bot-wh] [FALLBACK] Found transcript text in database ({len(transcript_text)} chars)')
                                                print(f'[bot-wh] [FALLBACK] Generating summary/action_items with Groq API...')
                                                
                                                # Generate summary and action items with Groq
                                                groq_result = generate_summary_and_action_items_with_groq(transcript_text)
                                                if groq_result:
                                                    # Update transcription with Groq results
                                                    summary = groq_result.get("summary", "")
                                                    action_items = groq_result.get("action_items", [])
                                                    
                                                    # Preserve existing transcript data structure
                                                    transcript_data = existing_transcription.transcript_data.copy() if existing_transcription.transcript_data else {}
                                                    
                                                    # Update or create transcription record
                                                    if existing_transcription:
                                                        existing_transcription.summary = summary
                                                        existing_transcription.action_items = action_items
                                                        existing_transcription.status = 'completed'
                                                        transcript_data['summary'] = summary
                                                        transcript_data['action_items'] = action_items
                                                        existing_transcription.transcript_data = transcript_data
                                                        existing_transcription.save()
                                                        print(f'[bot-wh] [FALLBACK] ✓ Updated transcription with summary and action items')
                                                    else:
                                                        # Create new transcription record
                                                        # Get backend_user_id from calendar_event
                                                        backend_user_id = calendar_event.backend_user_id
                                                        if not backend_user_id and calendar_event.calendar_id:
                                                            # Fallback: get from calendar
                                                            from app.models import Calendar
                                                            try:
                                                                calendar = Calendar.objects.get(id=calendar_event.calendar_id)
                                                                backend_user_id = calendar.backend_user_id
                                                            except Calendar.DoesNotExist:
                                                                pass
                                                        
                                                        MeetingTranscription.objects.create(
                                                            calendar_event_id=calendar_event.id,
                                                            bot_id=bot_id,
                                                            backend_user_id=backend_user_id,  # Set backend_user_id
                                                            transcript_text=transcript_text,
                                                            transcript_data={
                                                                **transcript_data,
                                                                'summary': summary,
                                                                'action_items': action_items
                                                            },
                                                            summary=summary,
                                                            action_items=action_items,
                                                            status='completed'
                                                        )
                                                        print(f'[bot-wh] [FALLBACK] ✓ Created transcription with summary and action items')
                                                    
                                                    print(f'[bot-wh] [FALLBACK] Summary length: {len(summary)} chars')
                                                    print(f'[bot-wh] [FALLBACK] Action items: {len(action_items)} items')
                                                    print(f'[bot-wh] [FALLBACK] ✓ Transcript processing complete via fallback mechanism')
                                                else:
                                                    print(f'[bot-wh] [FALLBACK] ⚠ WARNING: Failed to generate summary/action_items with Groq')
                                            else:
                                                print(f'[bot-wh] [FALLBACK] ⚠ WARNING: No transcript text found in database')
                                                print(f'[bot-wh] [FALLBACK] Waiting for real-time transcripts to be saved...')
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
                    print(f'[bot-wh] Triggering auto-retrieve and Groq summarization...')
                    print(f'[bot-wh] ==========================================')
                    try:
                        # Import here to avoid circular imports
                        from app.logic.bot_retriever import auto_retrieve_bot
                        from app.models import CalendarEvent
                        from app.services.groq.summary_generator import generate_summary_and_action_items_with_groq
                        from app.services.recall.service import get_service
                        
                        # Find calendar event with this bot_id
                        calendar_event = CalendarEvent.objects.filter(
                            recall_data__bots__bot_id=bot_id
                        ).first()
                        
                        calendar_event_id = str(calendar_event.id) if calendar_event else None
                        
                        # Trigger auto-retrieve and Groq summarization (async/background)
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
                                
                                # Get transcript from database and process with Groq
                                try:
                                    if calendar_event:
                                        print(f'[bot-wh] [BACKGROUND] Step 2: Getting transcript from database...')
                                        from app.models import MeetingTranscription
                                        
                                        existing_transcription = MeetingTranscription.objects.filter(
                                            calendar_event_id=calendar_event.id,
                                            bot_id=bot_id
                                        ).first()
                                        
                                        if existing_transcription and existing_transcription.transcript_text:
                                            transcript_text = existing_transcription.transcript_text
                                            print(f'[bot-wh] [BACKGROUND] ✓ Found transcript text ({len(transcript_text)} chars)')
                                            
                                            # Check if summary already exists (might have been generated by delayed check)
                                            if existing_transcription.summary and len(existing_transcription.summary.strip()) > 0:
                                                print(f'[bot-wh] [BACKGROUND] ℹ Summary already exists, skipping Groq generation')
                                                print(f'[bot-wh] [BACKGROUND] Summary length: {len(existing_transcription.summary)} chars')
                                                print(f'[bot-wh] [BACKGROUND] Action items: {len(existing_transcription.action_items)} items')
                                                print(f'[bot-wh] [BACKGROUND] ==========================================')
                                                print(f'[bot-wh] [BACKGROUND] ✅ TRANSCRIPTION ALREADY PROCESSED')
                                                print(f'[bot-wh] [BACKGROUND] ==========================================')
                                            else:
                                                print(f'[bot-wh] [BACKGROUND] Step 3: Generating summary/action_items with Groq...')
                                                groq_result = generate_summary_and_action_items_with_groq(transcript_text)
                                                
                                                if groq_result:
                                                    summary = groq_result.get("summary", "")
                                                    action_items = groq_result.get("action_items", [])
                                                    
                                                    print(f'[bot-wh] [BACKGROUND] ✓ Generated summary ({len(summary)} chars) and {len(action_items)} action items')
                                                    
                                                    # Update transcription record
                                                    transcript_data = existing_transcription.transcript_data.copy() if existing_transcription.transcript_data else {}
                                                    transcript_data['summary'] = summary
                                                    transcript_data['action_items'] = action_items
                                                    
                                                    existing_transcription.summary = summary
                                                    existing_transcription.action_items = action_items
                                                    existing_transcription.status = 'completed'
                                                    existing_transcription.transcript_data = transcript_data
                                                    existing_transcription.save()
                                                    
                                                    print(f'[bot-wh] [BACKGROUND] ✓ Saved transcription with summary and action items')
                                                    print(f'[bot-wh] [BACKGROUND] ==========================================')
                                                    print(f'[bot-wh] [BACKGROUND] ✅ TRANSCRIPTION PROCESSING COMPLETE (via bot.done)')
                                                    print(f'[bot-wh] [BACKGROUND] ==========================================')
                                                else:
                                                    print(f'[bot-wh] [BACKGROUND] ⚠ WARNING: Failed to generate summary/action_items with Groq')
                                        else:
                                            print(f'[bot-wh] [BACKGROUND] ⚠ WARNING: No transcript text found in database')
                                            print(f'[bot-wh] [BACKGROUND] Real-time transcripts may not have been saved yet')
                                    

                                    else:
                                        print(f'[bot-wh] [BACKGROUND] ⚠ WARNING: Calendar event not found for bot {bot_id}')
                                except Exception as e:
                                    print(f'[bot-wh] [BACKGROUND] ❌ ERROR: Failed to process transcript: {e}')
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
                                            
                                            # If no transcript ID or missing summary/action_items, generate them with Groq
                                            if not transcript_id or (assemblyai_transcript and (not assemblyai_transcript.get("summary") or not assemblyai_transcript.get("action_items"))):
                                                # Get transcript text and generate with Groq
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
                                                    print(f'[bot-wh] Using transcript text ({len(transcript_text)} chars), generating summary/action_items with Groq...')
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
                                                    else:
                                                        print(f'[bot-wh] ⚠ WARNING: Failed to generate summary/action_items with Groq')
                                                else:
                                                    print(f'[bot-wh] ⚠ WARNING: No transcript text available for Groq processing')
                                            
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

