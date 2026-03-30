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
        participant_id = None
        if isinstance(participant, dict):
            participant_name = participant.get("name") or participant.get("id")
            participant_id = participant.get("id")  # Store participant ID for disambiguation
        
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
            
            # Get participant name and ID
            participant_name = None
            participant_id = None
            if isinstance(participant, dict):
                participant_name = participant.get("name") or participant.get("id")
                participant_id = participant.get("id")  # Store participant ID for disambiguation
            
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
                        if bot_recording:
                            print(f'[bot-wh] [TRANSCRIPT] Found BotRecording: calendar_event_id={bot_recording.calendar_event_id}, backend_user_id={bot_recording.backend_user_id}')
                            if bot_recording.calendar_event_id:
                                calendar_event = CalendarEvent.objects.filter(id=bot_recording.calendar_event_id).first()
                                if calendar_event:
                                    print(f'[bot-wh] [TRANSCRIPT] ✓ Found calendar event via BotRecording: {calendar_event.id}')
                                else:
                                    print(f'[bot-wh] [TRANSCRIPT] ⚠ BotRecording has calendar_event_id={bot_recording.calendar_event_id} but CalendarEvent not found in database')
                            else:
                                print(f'[bot-wh] [TRANSCRIPT] ⚠ BotRecording exists but has no calendar_event_id')
                        else:
                            print(f'[bot-wh] [TRANSCRIPT] ⚠ BotRecording not found for bot_id: {bot_id}')
                        
                        # If not found, try searching in CalendarEvent's recall_data
                        if not calendar_event:
                            print(f'[bot-wh] [TRANSCRIPT] Trying to find CalendarEvent via recall_data bots array...')
                            # Try searching where bots is an array of objects with 'bot_id' field
                            calendar_event = CalendarEvent.objects.filter(
                                recall_data__bots__bot_id=bot_id
                            ).first()
                            
                            # If not found, try searching where bots is an array of objects with 'id' field
                            if not calendar_event:
                                calendar_event = CalendarEvent.objects.filter(
                                    recall_data__bots__id=bot_id
                                ).first()
                            
                            if calendar_event:
                                print(f'[bot-wh] [TRANSCRIPT] ✓ Found calendar event via recall_data query: {calendar_event.id}')
                        
                        if not calendar_event:
                            print(f'[bot-wh] [TRANSCRIPT] ⚠ WARNING: Calendar event not found for bot_id: {bot_id}')
                            
                            # Try to create CalendarEvent on-the-fly if we have backend_user_id from BotRecording
                            if bot_recording and bot_recording.backend_user_id:
                                print(f'[bot-wh] [TRANSCRIPT] Attempting to create CalendarEvent on-the-fly...')
                                try:
                                    from app.models import Calendar, CalendarEvent
                                    from datetime import datetime
                                    import uuid
                                    
                                    # Get bot data to extract meeting URL
                                    recall_service = get_service()
                                    bot_json = recall_service.get_bot(bot_id)
                                    meeting_url = bot_json.get('meeting_url') if bot_json else None
                                    
                                    if meeting_url:
                                        # Find or create manual calendar
                                        manual_calendar = Calendar.objects.filter(
                                            backend_user_id=bot_recording.backend_user_id,
                                            recall_data__is_manual=True
                                        ).first()
                                        
                                        if not manual_calendar:
                                            manual_calendar = Calendar.objects.create(
                                                user_id=bot_recording.backend_user_id,
                                                backend_user_id=bot_recording.backend_user_id,
                                                platform='google_calendar',
                                                recall_id=f'manual-{bot_recording.backend_user_id}',
                                                recall_data={'is_manual': True, 'platform_email': None},
                                                status='connected',
                                            )
                                        
                                        # Create CalendarEvent
                                        calendar_event = CalendarEvent.objects.create(
                                            calendar_id=manual_calendar.id,
                                            backend_user_id=bot_recording.backend_user_id,
                                            platform='google_calendar',
                                            recall_id=f'manual-event-{uuid.uuid4()}',
                                            recall_data={
                                                'meeting_url': meeting_url,
                                                'title': f'Manual Meeting - {datetime.now().strftime("%Y-%m-%d %H:%M")}',
                                                'start_time': datetime.now().isoformat(),
                                                'bots': [{'bot_id': bot_id, 'status': 'joining'}],
                                                'is_manual': True,
                                            },
                                            should_record_manual=True,
                                        )
                                        
                                        # Update BotRecording with calendar_event_id
                                        bot_recording.calendar_event_id = calendar_event.id
                                        bot_recording.save()
                                        
                                        print(f'[bot-wh] [TRANSCRIPT] ✓ Created CalendarEvent {calendar_event.id} on-the-fly and linked to BotRecording')
                                    else:
                                        print(f'[bot-wh] [TRANSCRIPT] ⚠ Could not get meeting_url from bot data')
                                except Exception as e:
                                    print(f'[bot-wh] [TRANSCRIPT] ❌ Error creating CalendarEvent on-the-fly: {e}')
                                    import traceback
                                    traceback.print_exc()
                            
                            if not calendar_event:
                                print(f'[bot-wh] [TRANSCRIPT] This transcript will not be saved to database')
                                print(f'[bot-wh] [TRANSCRIPT] Debug: Checking all CalendarEvents with is_manual=True...')
                                # Debug: Check if any manual events exist
                                from app.models import CalendarEvent
                                manual_events = CalendarEvent.objects.filter(recall_data__is_manual=True)
                                print(f'[bot-wh] [TRANSCRIPT] Found {manual_events.count()} manual CalendarEvents')
                                for me in manual_events[:5]:  # Show first 5
                                    bots_in_event = me.recall_data.get('bots', [])
                                    print(f'[bot-wh] [TRANSCRIPT]   Event {me.id}: {len(bots_in_event)} bots, bot_ids: {[b.get("bot_id") for b in bots_in_event]}')
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
                            
                            # Get BotRecording to copy workspace_id and folder_id
                            from app.models import BotRecording
                            bot_recording = BotRecording.objects.filter(bot_id=bot_id).first()
                            workspace_id = bot_recording.workspace_id if bot_recording else None
                            folder_id = bot_recording.folder_id if bot_recording else None
                            
                            # Get or create transcription record (one per bot per event)
                            transcription, created = MeetingTranscription.objects.get_or_create(
                                calendar_event_id=calendar_event.id,
                                bot_id=bot_id,
                                defaults={
                                    'backend_user_id': backend_user_id,  # Set backend_user_id
                                    'workspace_id': workspace_id,  # Copy from BotRecording
                                    'folder_id': folder_id,  # Copy from BotRecording (None = unresolved)
                                    'assemblyai_transcript_id': None,  # Will be set when final transcript is fetched
                                    'transcript_data': {
                                        'utterances': [{
                                            'speaker': participant_name,
                                            'speaker_id': participant_id,  # Store participant ID for disambiguation
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
                            
                            # Update backend_user_id, workspace_id, folder_id if they weren't set (for existing records)
                            updated = False
                            if not transcription.backend_user_id and backend_user_id:
                                transcription.backend_user_id = backend_user_id
                                updated = True
                            if not transcription.workspace_id and workspace_id:
                                transcription.workspace_id = workspace_id
                                updated = True
                            if transcription.folder_id is None and folder_id is not None:
                                transcription.folder_id = folder_id
                                updated = True
                            if updated:
                                transcription.save(update_fields=['backend_user_id', 'workspace_id', 'folder_id'])
                            
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
                                        'speaker_id': participant_id,  # Store participant ID for disambiguation
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
                                                from app.models import MeetingTranscription, CalendarEvent, BotRecording
                                                from app.services.groq.summary_generator import generate_summary_and_action_items_with_groq
                                                from app.logic.bot_retriever import auto_retrieve_bot
                                                
                                                # SIMPLIFIED: Check BotRecording.status - if not 'completed', bot is still active
                                                # Re-fetch bot_recording from database to get latest status
                                                bot_recording = BotRecording.objects.filter(bot_id=bot_id).first()
                                                if bot_recording:
                                                    # Re-fetch to ensure we get latest data
                                                    bot_recording = BotRecording.objects.get(id=bot_recording.id)
                                                    bot_status = bot_recording.status
                                                    
                                                    print(f'[bot-wh] [DELAYED CHECK] Checking bot status: bot_status={bot_status}')
                                                    
                                                    # SIMPLE CHECK: If status is NOT 'completed', bot is still active
                                                    if bot_status != 'completed':
                                                        print(f'[bot-wh] [DELAYED CHECK] Bot is still active (status: {bot_status}), skipping summary generation')
                                                        return  # Don't generate summary while bot is still in meeting
                                                    
                                                    # Bot status is 'completed', proceed with summary generation
                                                        print(f'[bot-wh] [DELAYED CHECK] Bot is done (latest_status: {latest_status}, bot_status: {bot_status}), proceeding with summary generation')
                                                
                                                # Re-fetch transcription to check if summary already exists
                                                transcription_check = MeetingTranscription.objects.filter(
                                                    calendar_event_id=calendar_event.id,
                                                    bot_id=bot_id
                                                ).first()
                                                
                                                if transcription_check:
                                                    # Only generate if summary doesn't exist yet
                                                    if not transcription_check.summary or len(transcription_check.summary.strip()) == 0:
                                                        print(f'[bot-wh] [DELAYED CHECK] Bot is done, no summary found, generating with Groq...')
                                                        
                                                        if transcription_check.transcript_text and len(transcription_check.transcript_text.strip()) > 0:
                                                            calendar_event_id = str(calendar_event.id)
                                                            
                                                            # Auto-retrieve bot first
                                                            auto_retrieve_bot(bot_id, calendar_event_id)
                                                            
                                                            # Generate summary and action items
                                                            groq_result = generate_summary_and_action_items_with_groq(transcription_check.transcript_text)
                                                            
                                                            if groq_result:
                                                                summary = groq_result.get("summary", "")
                                                                action_items = groq_result.get("action_items", [])
                                                                meeting_gaps = groq_result.get("meeting_gaps") or []
                                                                open_questions = groq_result.get("open_questions") or []
                                                                
                                                                # Initialize transcript_data before using it
                                                                transcript_data = transcription_check.transcript_data.copy() if transcription_check.transcript_data else {}
                                                                transcription_check.impact_score = None
                                                                transcript_data.pop('impact_breakdown', None)
                                                                
                                                                # Generate contextual nudges and key outcomes/signals (replaces legacy impact score)
                                                                nudge_result = None
                                                                try:
                                                                    from app.services.groq.nudge_analyzer import generate_contextual_nudges_and_signals_with_groq
                                                                    from app.models import MeetingTranscription
                                                                    
                                                                    # Get previous meetings for context
                                                                    previous_meetings = []
                                                                    if transcription_check.backend_user_id:
                                                                        previous_transcriptions = MeetingTranscription.objects.filter(
                                                                            backend_user_id=transcription_check.backend_user_id
                                                                        ).exclude(
                                                                            id=transcription_check.id
                                                                        ).order_by('-created_at')[:5]
                                                                        
                                                                        previous_meetings = [
                                                                            {
                                                                                'summary': t.summary or '',
                                                                                'action_items': t.action_items_list or []
                                                                            }
                                                                            for t in previous_transcriptions
                                                                            if t.summary
                                                                        ]
                                                                    
                                                                    nudge_result = generate_contextual_nudges_and_signals_with_groq(
                                                                        transcript_text=transcription_check.transcript_text,
                                                                        summary=summary,
                                                                        action_items=action_items,
                                                                        previous_meetings=previous_meetings
                                                                    )
                                                                    
                                                                    if nudge_result:
                                                                        contextual_nudges = nudge_result.get("contextual_nudges", [])
                                                                        key_outcomes_signals = nudge_result.get("key_outcomes_signals") or []
                                                                        
                                                                        transcription_check.contextual_nudges = contextual_nudges
                                                                        transcription_check.key_outcomes_signals = key_outcomes_signals
                                                                        
                                                                        print(f'[bot-wh] [DELAYED CHECK] ✓ Generated {len(contextual_nudges)} nudges and {len(key_outcomes_signals)} key outcome signals')
                                                                except Exception as nudge_error:
                                                                    print(f'[bot-wh] [DELAYED CHECK] ⚠ WARNING: Error generating nudges: {nudge_error}')
                                                                transcript_data['summary'] = summary
                                                                transcript_data['action_items'] = action_items
                                                                
                                                                transcription_check.summary = summary
                                                                transcription_check.action_items = action_items
                                                                transcription_check.meeting_gaps = meeting_gaps
                                                                transcription_check.open_questions = open_questions
                                                                transcription_check.status = 'completed'
                                                                transcription_check.transcript_data = transcript_data
                                                                transcription_check.save()
                                                                
                                                                # Update BotRecording.status to 'completed' to mark meeting as ended
                                                                if bot_recording:
                                                                    bot_recording.status = 'completed'
                                                                    bot_recording.save()
                                                                    print(f'[bot-wh] [DELAYED CHECK] ✓ Updated BotRecording.status to "completed" for bot {bot_id}')
                                                                
                                                                print(f'[bot-wh] [DELAYED CHECK] ✓ Generated and saved summary ({len(summary)} chars), {len(action_items)} action items, nudges, gaps, and open questions')
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
        
            # Store participant information in transcription for real-time contextual nudges
            if bot_id and (event == "participant_events.join" or event == "participant_events.leave"):
                try:
                    from app.models import CalendarEvent, MeetingTranscription, BotRecording
                    
                    # Find calendar event and transcription
                    bot_recording = BotRecording.objects.filter(bot_id=bot_id).first()
                    calendar_event = None
                    if bot_recording and bot_recording.calendar_event_id:
                        calendar_event = CalendarEvent.objects.filter(id=bot_recording.calendar_event_id).first()
                    
                    if not calendar_event:
                        calendar_event = CalendarEvent.objects.filter(
                            recall_data__bots__bot_id=bot_id
                        ).first()
                    
                    if calendar_event:
                        # Get BotRecording to copy workspace_id and folder_id
                        workspace_id = bot_recording.workspace_id if bot_recording else None
                        folder_id = bot_recording.folder_id if bot_recording else None
                        
                        # Get or create transcription
                        transcription, created = MeetingTranscription.objects.get_or_create(
                            calendar_event_id=calendar_event.id,
                            bot_id=bot_id,
                            defaults={
                                'backend_user_id': calendar_event.backend_user_id,
                                'workspace_id': workspace_id,  # Copy from BotRecording
                                'folder_id': folder_id,  # Copy from BotRecording (None = unresolved)
                                'transcript_data': {'participants': []},
                                'status': 'processing',
                            }
                        )
                        
                        # Update backend_user_id, workspace_id, folder_id if not set
                        updated = False
                        if not transcription.backend_user_id and calendar_event.backend_user_id:
                            transcription.backend_user_id = calendar_event.backend_user_id
                            updated = True
                        if not transcription.workspace_id and workspace_id:
                            transcription.workspace_id = workspace_id
                            updated = True
                        if transcription.folder_id is None and folder_id is not None:
                            transcription.folder_id = folder_id
                            updated = True
                        if updated:
                            transcription.save(update_fields=['backend_user_id', 'workspace_id', 'folder_id'])
                        
                        # Get or initialize participants list in transcript_data
                        if 'participants' not in transcription.transcript_data:
                            transcription.transcript_data['participants'] = []
                        
                        participants_list = transcription.transcript_data['participants']
                        
                        # Create participant entry
                        participant_id = None  # Session ID (temporary, session-specific)
                        persistent_id = None   # Platform-specific persistent ID (consistent across meetings)
                        platform_type = None
                        
                        if isinstance(participant, dict):
                            participant_id = participant.get("id")  # Session-specific ID
                            platform_type = participant.get("platform", "unknown")
                            extra_data = participant.get("extra_data", {})
                            
                            # Extract platform-specific persistent ID
                            if platform_type == "zoom" and isinstance(extra_data.get("zoom"), dict):
                                # Zoom: use conf_user_id (consistent across meetings)
                                persistent_id = extra_data["zoom"].get("conf_user_id")
                                if persistent_id:
                                    print(f'[bot-wh] [PARTICIPANTS] Zoom participant - using conf_user_id: {persistent_id}')
                            elif platform_type == "microsoft_teams" and isinstance(extra_data.get("microsoft_teams"), dict):
                                # Teams: use user_id (consistent across meetings)
                                persistent_id = extra_data["microsoft_teams"].get("user_id")
                                if persistent_id:
                                    print(f'[bot-wh] [PARTICIPANTS] Teams participant - using user_id: {persistent_id}')
                            elif platform_type in ["desktop", "mobile_app"] and isinstance(extra_data.get("google_meet"), dict):
                                # Google Meet: use static_participant_id (consistent across meetings)
                                persistent_id = extra_data["google_meet"].get("static_participant_id")
                                if persistent_id:
                                    print(f'[bot-wh] [PARTICIPANTS] Google Meet participant - using static_participant_id: {persistent_id}')
                        
                        # Use persistent_id as primary identifier if available, fallback to session id
                        primary_id = persistent_id if persistent_id else participant_id
                        
                        participant_entry = {
                            'id': participant_id,  # Session ID (for reference)
                            'persistent_id': persistent_id,  # Platform-specific persistent ID (for matching)
                            'primary_id': primary_id,  # Primary identifier to use for matching
                            'name': participant_name,
                            'is_host': participant.get("is_host", False) if isinstance(participant, dict) else False,
                            'platform': platform_type or (participant.get("platform", "unknown") if isinstance(participant, dict) else "unknown"),
                            'joined_at': timestamp,
                        }
                        
                        if event == "participant_events.join":
                            # Add participant if not already in list
                            # Check by primary_id (persistent_id or session id), otherwise check by name
                            if primary_id is not None:
                                existing = next((p for p in participants_list if p.get('primary_id') == primary_id or p.get('persistent_id') == primary_id or p.get('id') == primary_id), None)
                            else:
                                existing = next((p for p in participants_list if p.get('name') == participant_name), None)
                            
                            if not existing:
                                participants_list.append(participant_entry)
                                print(f'[bot-wh] [PARTICIPANTS] Added participant: {participant_name} (Session ID: {participant_id}, Persistent ID: {persistent_id or "N/A"})')
                            else:
                                # Update existing participant entry (in case session ID changed but persistent ID is same)
                                existing.update(participant_entry)
                                print(f'[bot-wh] [PARTICIPANTS] Updated participant: {participant_name} (Session ID: {participant_id}, Persistent ID: {persistent_id or "N/A"})')
                        elif event == "participant_events.leave":
                            # Remove participant from list
                            # Remove by primary_id (persistent_id or session id), otherwise remove by name
                            if primary_id is not None:
                                participants_list[:] = [p for p in participants_list if not (p.get('primary_id') == primary_id or p.get('persistent_id') == primary_id or p.get('id') == primary_id)]
                            else:
                                participants_list[:] = [p for p in participants_list if p.get('name') != participant_name]
                            print(f'[bot-wh] [PARTICIPANTS] Removed participant: {participant_name} (Session ID: {participant_id}, Persistent ID: {persistent_id or "N/A"})')
                        
                        # Update transcript_data
                        transcription.transcript_data['participants'] = participants_list
                        transcription.save()
                        print(f'[bot-wh] [PARTICIPANTS] Updated participant list: {len(participants_list)} participants')
                        
                except Exception as e:
                    print(f'[bot-wh] [PARTICIPANTS] Error updating participant list: {e}')
                    import traceback
                    traceback.print_exc()
        
            # Check if account owner left - if so, make bot leave (FALLBACK: if owner_name not stored, bot stays)
            if event == "participant_events.leave" and bot_id and participant_name:
                try:
                    from app.models import BotRecording
                    from app.services.recall.service import get_service
                    import os
                    
                    # Get bot recording to find owner
                    bot_recording = BotRecording.objects.filter(bot_id=bot_id).first()
                    
                    if bot_recording and bot_recording.backend_user_id:
                        # Get stored owner name from recall_data (OPTIONAL - may not exist)
                        owner_name = None
                        if bot_recording.recall_data and isinstance(bot_recording.recall_data, dict):
                            owner_name = bot_recording.recall_data.get('owner_name')
                        
                        # Only check if owner_name is stored (FALLBACK: if not stored, bot stays - current behavior)
                        if owner_name:
                            # Normalize names for comparison (trim whitespace, case-insensitive)
                            leaving_name = participant_name.strip()
                            owner_name_normalized = owner_name.strip()
                            
                            # Check if account owner left (exact match)
                            if leaving_name.lower() == owner_name_normalized.lower():
                                print(f'[bot-wh] [OWNER LEAVE] ⚠ Account owner ({owner_name}) left the meeting')
                                print(f'[bot-wh] [OWNER LEAVE] Making bot leave the call...')
                                
                                try:
                                    # Get region from environment or use default
                                    recall_region = os.getenv('RECALL_REGION', 'us-west-2')
                                    
                                    # Call Recall.ai API to make bot leave the call
                                    recall_service = get_service()
                                    recall_service.leave_bot_call(bot_id, region=recall_region)
                                    
                                    print(f'[bot-wh] [OWNER LEAVE] ✓ Successfully called leave_bot_call API for bot_id: {bot_id}')
                                    
                                    # Mark bot recording as completed
                                    bot_recording.status = 'completed'
                                    bot_recording.save()
                                    print(f'[bot-wh] [OWNER LEAVE] ✓ Bot recording marked as completed')
                                except Exception as api_error:
                                    # If API call fails, still mark as completed (bot will stop naturally)
                                    print(f'[bot-wh] [OWNER LEAVE] ⚠ API call failed (non-fatal): {api_error}')
                                    print(f'[bot-wh] [OWNER LEAVE] Marking bot as completed anyway...')
                                    bot_recording.status = 'completed'
                                    bot_recording.save()
                                    import traceback
                                    traceback.print_exc()
                            else:
                                print(f'[bot-wh] [PARTICIPANT LEAVE] Non-owner participant left ({participant_name}), bot stays in meeting')
                        else:
                            # FALLBACK: Owner name not stored - bot continues as normal (current behavior)
                            print(f'[bot-wh] [PARTICIPANT LEAVE] Participant left ({participant_name}), owner name not stored - bot stays (fallback: works as before)')
                    else:
                        print(f'[bot-wh] [PARTICIPANT LEAVE] BotRecording not found or no backend_user_id - bot stays')
                except Exception as e:
                    # Non-fatal error - don't break the webhook processing
                    print(f'[bot-wh] [OWNER LEAVE] Error checking owner leave (non-fatal, continuing): {e}')
                    import traceback
                    traceback.print_exc()
            
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
                                                    meeting_gaps = groq_result.get("meeting_gaps") or []
                                                    open_questions = groq_result.get("open_questions") or []
                                                    
                                                    # Preserve existing transcript data structure (initialize before using)
                                                    transcript_data = existing_transcription.transcript_data.copy() if existing_transcription.transcript_data else {}
                                                    existing_transcription.impact_score = None
                                                    transcript_data.pop('impact_breakdown', None)
                                                    
                                                    # Generate contextual nudges and key outcomes/signals
                                                    nudge_result = None
                                                    try:
                                                        from app.services.groq.nudge_analyzer import generate_contextual_nudges_and_signals_with_groq
                                                        from app.models import MeetingTranscription
                                                        
                                                        # Get previous meetings for context
                                                        previous_meetings = []
                                                        if existing_transcription and existing_transcription.backend_user_id:
                                                            previous_transcriptions = MeetingTranscription.objects.filter(
                                                                backend_user_id=existing_transcription.backend_user_id
                                                            ).exclude(
                                                                id=existing_transcription.id
                                                            ).order_by('-created_at')[:5]
                                                            
                                                            previous_meetings = [
                                                                {
                                                                    'summary': t.summary or '',
                                                                    'action_items': t.action_items_list or []
                                                                }
                                                                for t in previous_transcriptions
                                                                if t.summary
                                                            ]
                                                        
                                                        nudge_result = generate_contextual_nudges_and_signals_with_groq(
                                                            transcript_text=transcript_text,
                                                            summary=summary,
                                                            action_items=action_items,
                                                            previous_meetings=previous_meetings
                                                        )
                                                        
                                                        if nudge_result:
                                                            contextual_nudges = nudge_result.get("contextual_nudges", [])
                                                            key_outcomes_signals = nudge_result.get("key_outcomes_signals") or []
                                                            
                                                            if existing_transcription:
                                                                existing_transcription.contextual_nudges = contextual_nudges
                                                                existing_transcription.key_outcomes_signals = key_outcomes_signals
                                                                
                                                                print(f'[bot-wh] [FALLBACK] ✓ Generated {len(contextual_nudges)} nudges and {len(key_outcomes_signals)} key outcome signals')
                                                    except Exception as nudge_error:
                                                        print(f'[bot-wh] [FALLBACK] ⚠ WARNING: Error generating nudges: {nudge_error}')
                                                    
                                                    # Update or create transcription record
                                                    if existing_transcription:
                                                        existing_transcription.summary = summary
                                                        existing_transcription.action_items = action_items
                                                        existing_transcription.meeting_gaps = meeting_gaps
                                                        existing_transcription.open_questions = open_questions
                                                        existing_transcription.status = 'completed'
                                                        transcript_data['summary'] = summary
                                                        transcript_data['action_items'] = action_items
                                                        existing_transcription.transcript_data = transcript_data
                                                        existing_transcription.save()
                                                        
                                                        # Update BotRecording.status to 'completed' to mark meeting as ended
                                                        bot_recording = BotRecording.objects.filter(bot_id=bot_id).first()
                                                        if bot_recording:
                                                            bot_recording.status = 'completed'
                                                            bot_recording.save()
                                                            print(f'[bot-wh] [FALLBACK] ✓ Updated BotRecording.status to "completed" for bot {bot_id}')
                                                        
                                                        print(f'[bot-wh] [FALLBACK] ✓ Updated transcription with summary, action items, nudges, gaps, and open questions')
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
                                                        
                                                        # Get BotRecording to copy workspace_id and folder_id
                                                        bot_recording = BotRecording.objects.filter(bot_id=bot_id).first()
                                                        workspace_id = bot_recording.workspace_id if bot_recording else None
                                                        folder_id = bot_recording.folder_id if bot_recording else None
                                                        
                                                        MeetingTranscription.objects.create(
                                                            calendar_event_id=calendar_event.id,
                                                            bot_id=bot_id,
                                                            backend_user_id=backend_user_id,  # Set backend_user_id
                                                            workspace_id=workspace_id,  # Copy from BotRecording
                                                            folder_id=folder_id,  # Copy from BotRecording (None = unresolved)
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
                        from app.models import CalendarEvent, BotRecording
                        from app.services.groq.summary_generator import generate_summary_and_action_items_with_groq
                        from app.services.recall.service import get_service
                        
                        # CRITICAL: Update BotRecording.status to 'completed' when bot.done is received
                        # This ensures contextual nudges API won't treat this bot as live
                        bot_recording = BotRecording.objects.filter(bot_id=bot_id).first()
                        if bot_recording:
                            bot_recording.status = 'completed'
                            bot_recording.save()
                            print(f'[bot-wh] ✓ Updated BotRecording.status to "completed" for bot {bot_id}')
                        else:
                            print(f'[bot-wh] ⚠ WARNING: BotRecording not found for bot {bot_id}, cannot update status')
                        
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
                                                    meeting_gaps = groq_result.get("meeting_gaps") or []
                                                    open_questions = groq_result.get("open_questions") or []
                                                    
                                                    print(f'[bot-wh] [BACKGROUND] ✓ Generated summary ({len(summary)} chars) and {len(action_items)} action items')
                                                    
                                                    transcript_data = existing_transcription.transcript_data.copy() if existing_transcription.transcript_data else {}
                                                    existing_transcription.impact_score = None
                                                    transcript_data.pop('impact_breakdown', None)
                                                    
                                                    # Step 4: Generate contextual nudges and key outcomes/signals
                                                    print(f'[bot-wh] [BACKGROUND] Step 4: Generating contextual nudges and key outcomes/signals with Groq...')
                                                    try:
                                                        from app.services.groq.nudge_analyzer import generate_contextual_nudges_and_signals_with_groq
                                                        from app.models import MeetingTranscription
                                                        
                                                        # Get previous meetings for context (last 5 meetings for this user)
                                                        previous_meetings = []
                                                        if existing_transcription.backend_user_id:
                                                            previous_transcriptions = MeetingTranscription.objects.filter(
                                                                backend_user_id=existing_transcription.backend_user_id
                                                            ).exclude(
                                                                id=existing_transcription.id
                                                            ).order_by('-created_at')[:5]
                                                            
                                                            previous_meetings = [
                                                                {
                                                                    'summary': t.summary or '',
                                                                    'action_items': t.action_items_list or []
                                                                }
                                                                for t in previous_transcriptions
                                                                if t.summary
                                                            ]
                                                        
                                                        nudge_result = generate_contextual_nudges_and_signals_with_groq(
                                                            transcript_text=transcript_text,
                                                            summary=summary,
                                                            action_items=action_items,
                                                            previous_meetings=previous_meetings
                                                        )
                                                        
                                                        if nudge_result:
                                                            contextual_nudges = nudge_result.get("contextual_nudges", [])
                                                            key_outcomes_signals = nudge_result.get("key_outcomes_signals") or []
                                                            
                                                            print(f'[bot-wh] [BACKGROUND] ✓ Generated {len(contextual_nudges)} contextual nudges and {len(key_outcomes_signals)} key outcome signals')
                                                            
                                                            existing_transcription.contextual_nudges = contextual_nudges
                                                            existing_transcription.key_outcomes_signals = key_outcomes_signals
                                                        else:
                                                            print(f'[bot-wh] [BACKGROUND] ⚠ WARNING: Failed to generate contextual nudges/signals')
                                                    except Exception as nudge_error:
                                                        print(f'[bot-wh] [BACKGROUND] ⚠ WARNING: Error generating nudges: {nudge_error}')
                                                        import traceback
                                                        traceback.print_exc()
                                                    
                                                    transcript_data['summary'] = summary
                                                    transcript_data['action_items'] = action_items
                                                    
                                                    existing_transcription.summary = summary
                                                    existing_transcription.action_items = action_items
                                                    existing_transcription.meeting_gaps = meeting_gaps
                                                    existing_transcription.open_questions = open_questions
                                                    existing_transcription.status = 'completed'
                                                    existing_transcription.transcript_data = transcript_data
                                                    existing_transcription.save()
                                                    
                                                    # BotRecording.status is already updated at the beginning of bot.done handler
                                                    # So we don't need to update it again here
                                                    
                                                    print(f'[bot-wh] [BACKGROUND] ✓ Saved transcription with summary, action items, nudges, gaps, and open questions')
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
                                                        if groq_result.get("meeting_gaps") is not None:
                                                            assemblyai_transcript["meeting_gaps"] = groq_result.get("meeting_gaps")
                                                        if groq_result.get("open_questions") is not None:
                                                            assemblyai_transcript["open_questions"] = groq_result.get("open_questions")
                                                        print(f'[bot-wh] ✓ Generated summary and action items using Groq')
                                                    else:
                                                        print(f'[bot-wh] ⚠ WARNING: Failed to generate summary/action_items with Groq')
                                                else:
                                                    print(f'[bot-wh] ⚠ WARNING: No transcript text available for Groq processing')
                                            
                                            if assemblyai_transcript:
                                                from app.models import MeetingTranscription
                                                # Extract action items
                                                action_items = assemblyai_transcript.get('action_items', [])
                                                
                                                # Get BotRecording to copy workspace_id and folder_id
                                                from app.models import BotRecording
                                                bot_recording = BotRecording.objects.filter(bot_id=bot_id).first()
                                                workspace_id = bot_recording.workspace_id if bot_recording else None
                                                folder_id = bot_recording.folder_id if bot_recording else None
                                                
                                                transcription, created = MeetingTranscription.objects.get_or_create(
                                                    calendar_event_id=calendar_event.id,
                                                    bot_id=bot_id,
                                                    defaults={
                                                        'backend_user_id': backend_user_id,
                                                        'workspace_id': workspace_id,  # Copy from BotRecording
                                                        'folder_id': folder_id,  # Copy from BotRecording (None = unresolved)
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
                                                    mg = assemblyai_transcript.get('meeting_gaps')
                                                    oq = assemblyai_transcript.get('open_questions')
                                                    if mg is not None:
                                                        transcription.meeting_gaps = mg
                                                    if oq is not None:
                                                        transcription.open_questions = oq
                                                    transcription.status = 'completed' if assemblyai_transcript.get('status') == 'completed' else 'processing'
                                                    
                                                    # Update workspace_id and folder_id if not set
                                                    if not transcription.workspace_id and workspace_id:
                                                        transcription.workspace_id = workspace_id
                                                    if transcription.folder_id is None and folder_id is not None:
                                                        transcription.folder_id = folder_id
                                                    
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

