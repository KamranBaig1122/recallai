"""
Helper functions to create meeting bots for calendar events
Uses Recall.ai API directly with join_at for scheduled bot joining
"""
from django.utils import timezone
from app.models import CalendarEvent
from app.services.recall.service import get_service
import os
import traceback


def get_user_name_from_backend(backend_user_id: str) -> str | None:
    """
    Fetch user name from Invite-ellie-backend API (OPTIONAL - returns None if unavailable)
    
    Args:
        backend_user_id: User ID (UUID)
        
    Returns:
        User's full name (first_name + last_name) or None if not available
    """
    try:
        import requests
        import os
        
        # Use the correct environment variable name
        api_base_url = os.environ.get('INVITE_ELLIE_BACKEND_API_URL', 'http://localhost:8000')
        
        if not api_base_url:
            print(f'[bot_creator] ⚠ INVITE_ELLIE_BACKEND_API_URL not set, skipping user name fetch')
            return None
        
        # Use the same endpoint format as auth.py: /api/accounts/me/
        from app.logic.backend_auth import get_backend_api_headers
        api_url = f'{api_base_url}/api/accounts/me/'
        headers = get_backend_api_headers({
            'X-User-ID': backend_user_id,  # Still include X-User-ID for user context
        })
        
        print(f'[bot_creator] Fetching user name from: {api_url}')
        print(f'[bot_creator] Headers: X-User-ID={backend_user_id}')
        
        response = requests.get(
            api_url,
            headers=headers,
            timeout=5  # Increased timeout slightly
        )
        
        print(f'[bot_creator] API response status: {response.status_code}')
        
        if response.status_code == 200:
            data = response.json()
            print(f'[bot_creator] API response data: {data}')
            
            first_name = data.get('first_name', '').strip() if data.get('first_name') else ''
            last_name = data.get('last_name', '').strip() if data.get('last_name') else ''
            full_name = f'{first_name} {last_name}'.strip()
            
            if full_name:
                print(f'[bot_creator] ✓ Successfully fetched user name: {full_name}')
                return full_name
            else:
                print(f'[bot_creator] ⚠ User name fields are empty in API response')
        else:
            print(f'[bot_creator] ⚠ API returned status {response.status_code}: {response.text[:200]}')
            
    except requests.exceptions.Timeout:
        print(f'[bot_creator] ⚠ Request timeout while fetching user name (optional, continuing)')
    except requests.exceptions.RequestException as e:
        print(f'[bot_creator] ⚠ Request error while fetching user name (optional): {e}')
    except Exception as e:
        print(f'[bot_creator] ⚠ Could not fetch user name (optional): {e}')
        import traceback
        traceback.print_exc()
    
    return None


def create_bot_for_event(event: CalendarEvent, force: bool = False, workspace_id: str = None, folder_id: str = None) -> dict:
    """
    Create a meeting bot for a calendar event with scheduled join time
    
    Args:
        event: CalendarEvent instance
        force: If True, create bot even if one already exists
        workspace_id: Optional workspace ID from Invite-ellie-backend (if None, will try to get from event)
        folder_id: Optional folder ID from Invite-ellie-backend (if None, meeting goes to unresolved)
        
    Returns:
        dict with 'success', 'bot_id', 'join_at', and 'error' keys
    """
    # Check if event has meeting URL
    meeting_url = event.meeting_url
    if not meeting_url:
        return {
            'success': False,
            'error': 'Event has no meeting_url'
        }
    
    # Check start time
    start_time = event.start_time
    if not start_time:
        return {
            'success': False,
            'error': 'Event has no start_time'
        }
    
    # Convert to timezone-aware if needed
    if timezone.is_naive(start_time):
        start_time = timezone.make_aware(start_time)
    
    # Check if event is in the past
    # Allow creating bots for past events if force=True (manual creation for synced meetings)
    if start_time <= timezone.now() and not force:
        return {
            'success': False,
            'error': 'Event start time is in the past. Use force=True to create bot for past meetings.'
        }
    
    # Check if already has a bot (unless force=True)
    if not force:
        bots = event.bots
        if bots and len(bots) > 0:
            return {
                'success': False,
                'error': f'Event already has {len(bots)} bot(s)',
                'bot_id': bots[0].get('bot_id') if bots else None
            }
    
    try:
        recall_service = get_service()
        
        # Detect platform from URL
        platform = _detect_platform(meeting_url)
        
        # Build recording config
        recording_config = _build_recording_config()
        
        # Format join_at as ISO 8601
        join_at = start_time.isoformat()
        
        # Get region from environment
        region = os.getenv('RECALL_REGION', 'us-west-2')
        
        # Create the bot with join_at
        # Bot name is "Ellie" as requested
        bot_data = recall_service.create_bot(
            meeting_url=meeting_url,
            bot_name="Ellie",
            join_at=join_at,
            platform=platform,
            recording_config=recording_config,
            region=region
        )
        
        bot_id = bot_data.get('id') or bot_data.get('bot_id') or bot_data.get('uuid')
        if bot_id:
            # Fetch owner name (OPTIONAL - will be None if unavailable)
            owner_name = None
            if event.backend_user_id:
                owner_name = get_user_name_from_backend(str(event.backend_user_id))
                if owner_name:
                    print(f'[BotCreator] Fetched owner name: {owner_name}')
                else:
                    print(f'[BotCreator] ⚠ Owner name not available (optional, will continue without it)')
            
            # Update event's recall_data to include bot info
            recall_data = event.recall_data.copy()
            if 'bots' not in recall_data:
                recall_data['bots'] = []
            
            # Add bot info
            recall_data['bots'].append({
                'bot_id': bot_id,
                'join_at': join_at,
                'created_at': timezone.now().isoformat(),
                'status': 'scheduled',
            })
            
            event.recall_data = recall_data
            event.save()
            
            # Schedule auto-retrieve (will check periodically)
            # For immediate retrieval, we'll use a background task or management command
            # For now, we'll create a placeholder BotRecording that will be updated when retrieved
            try:
                from app.models import BotRecording
                # Initialize recall_data with owner_name if available
                recall_data_dict = bot_data.copy() if isinstance(bot_data, dict) else {}
                if owner_name:
                    if not recall_data_dict:
                        recall_data_dict = {}
                    recall_data_dict['owner_name'] = owner_name
                
                # If workspace_id not provided, try to get from event's calendar
                # For scheduled bots, workspace_id might come from calendar connection
                final_workspace_id = workspace_id
                if not final_workspace_id and event.backend_user_id:
                    # Try to get workspace from user's email domain (future enhancement)
                    # For now, we'll require workspace_id to be passed
                    pass
                
                bot_recording, created = BotRecording.objects.update_or_create(
                    bot_id=bot_id,
                    defaults={
                        'recall_data': recall_data_dict,
                        'status': 'pending',
                        'calendar_event_id': event.id,
                        'backend_user_id': event.backend_user_id,
                        'workspace_id': final_workspace_id,  # Required - None means unresolved
                        'folder_id': folder_id,  # Optional - None means unresolved
                    }
                )
                
                # If bot_recording already exists, update owner_name if available
                if not created and owner_name:
                    if not bot_recording.recall_data:
                        bot_recording.recall_data = {}
                    bot_recording.recall_data['owner_name'] = owner_name
                    bot_recording.save(update_fields=['recall_data'])
                    print(f'[BotCreator] ✓ Stored owner name in existing BotRecording: {owner_name}')
                elif created and owner_name:
                    print(f'[BotCreator] ✓ Stored owner name in BotRecording: {owner_name}')
            except Exception as e:
                print(f'WARNING: Could not create BotRecording placeholder: {e}')
            
            # Send previous meeting summary email (background task, don't block)
            try:
                if event.backend_user_id:
                    from app.services.email_service import send_previous_meeting_summary_email
                    # Call in background (fire and forget)
                    import threading
                    def send_email_async():
                        try:
                            send_previous_meeting_summary_email(
                                backend_user_id=str(event.backend_user_id),
                                current_event_start_time=start_time,
                                new_meeting_title=event.title
                            )
                        except Exception as e:
                            print(f'[BotCreator] Error sending previous meeting email (non-blocking): {e}')
                    
                    # Start email in background thread
                    email_thread = threading.Thread(target=send_email_async, daemon=True)
                    email_thread.start()
                    print(f'[BotCreator] Started background thread to send previous meeting summary email')
            except Exception as e:
                print(f'[BotCreator] Could not send previous meeting email (non-blocking): {e}')
            
            return {
                'success': True,
                'bot_id': bot_id,
                'join_at': join_at,
                'bot_data': bot_data
            }
        else:
            return {
                'success': False,
                'error': f'Failed to get bot_id from response: {bot_data}'
            }
            
    except Exception as e:
        error_msg = str(e)
        traceback.print_exc()
        return {
            'success': False,
            'error': error_msg
        }


def create_bot_immediately(meeting_url: str, meeting_password: str = None, backend_user_id: str = None, meeting_name: str = None, workspace_id: str = None, folder_id: str = None) -> dict:
    """
    Create a meeting bot that joins immediately (without join_at)
    
    Args:
        meeting_url: Full meeting URL (Zoom/Google Meet/Teams/GoTo Meeting)
        meeting_password: Optional meeting password if required
        backend_user_id: Optional backend user ID to associate with the bot
        meeting_name: Optional meeting name/title to use for the CalendarEvent
        workspace_id: Required workspace ID from Invite-ellie-backend
        folder_id: Optional folder ID from Invite-ellie-backend (if None, meeting goes to unresolved)
        
    Returns:
        dict with 'success', 'bot_id', and 'error' keys
    """
    if not meeting_url:
        return {
            'success': False,
            'error': 'meeting_url is required'
        }
    
    try:
        recall_service = get_service()
        
        # Detect platform from URL
        platform = _detect_platform(meeting_url)
        
        # Note: GoTo Meeting doesn't support password-protected meetings
        # If platform is gotomeeting and password is provided, warn but still try
        if platform == "gotomeeting" and meeting_password:
            print(f'WARNING: GoTo Meeting doesn\'t support password-protected meetings. Password will be ignored.')
        
        # Build recording config (same as scheduled bots)
        recording_config = _build_recording_config()
        
        # Get region from environment
        region = os.getenv('RECALL_REGION', 'us-west-2')
        
        # Create the bot without join_at (joins immediately)
        # Bot name is "Ellie" as requested
        bot_data = recall_service.create_bot(
            meeting_url=meeting_url,
            bot_name="Ellie",
            join_at=None,  # No join_at means join immediately
            platform=platform,
            meeting_password=meeting_password,
            recording_config=recording_config,
            region=region
        )
        
        bot_id = bot_data.get('id') or bot_data.get('bot_id') or bot_data.get('uuid')
        if bot_id:
            print(f'[BotCreator] Bot created successfully: {bot_id}')
            print(f'[BotCreator] backend_user_id: {backend_user_id}')
            print(f'[BotCreator] workspace_id: {workspace_id}')
            if folder_id:
                print(f'[BotCreator] folder_id: {folder_id}')
            else:
                print(f'[BotCreator] No folder_id - meeting will go to unresolved')
            
            # Create a CalendarEvent for manually joined bots so transcriptions can be processed
            # This allows the webhook to find the event and process transcriptions properly
            calendar_event = None
            if backend_user_id:
                print(f'[BotCreator] Creating CalendarEvent for manual meeting...')
                try:
                    from app.models import CalendarEvent, Calendar
                    from datetime import datetime
                    import uuid
                    
                    # Find or create a "manual" calendar for this user (for manually joined meetings)
                    # We'll use a special calendar_id that represents manual meetings
                    # First, try to find an existing manual calendar for this user
                    manual_calendar = Calendar.objects.filter(
                        backend_user_id=backend_user_id,
                        recall_data__is_manual=True
                    ).first()
                    
                    if not manual_calendar:
                        # Create a manual calendar for this user
                        manual_calendar = Calendar.objects.create(
                            user_id=backend_user_id,  # For backward compatibility
                            backend_user_id=backend_user_id,
                            platform='google_calendar',  # Default platform (not really used for manual meetings)
                            recall_id=f'manual-{backend_user_id}',
                            recall_data={
                                'is_manual': True,
                                'platform_email': None,
                            },
                            status='connected',
                        )
                        print(f'[BotCreator] Created manual calendar for user {backend_user_id}')
                    
                    # Create a CalendarEvent for this manual meeting
                    # Use provided meeting_name if available, otherwise extract from URL or use default
                    if meeting_name and meeting_name.strip():
                        # Use the provided meeting name
                        meeting_title = meeting_name.strip()
                        print(f'[BotCreator] Using provided meeting name: {meeting_title}')
                    else:
                        # Fallback: Extract meeting title from URL if possible
                        meeting_title = f'Manual Meeting - {datetime.now().strftime("%Y-%m-%d %H:%M")}'
                        if 'zoom.us' in meeting_url.lower():
                            # Try to extract meeting ID from Zoom URL
                            import re
                            zoom_match = re.search(r'zoom\.us/j/(\d+)', meeting_url)
                            if zoom_match:
                                meeting_title = f'Zoom Meeting {zoom_match.group(1)}'
                        print(f'[BotCreator] Using auto-generated meeting title: {meeting_title}')
                    
                    calendar_event = CalendarEvent.objects.create(
                        calendar_id=manual_calendar.id,
                        backend_user_id=backend_user_id,
                        platform=platform or 'google_calendar',
                        recall_id=f'manual-event-{uuid.uuid4()}',
                        recall_data={
                            'meeting_url': meeting_url,
                            'title': meeting_title,
                            'start_time': datetime.now().isoformat(),
                            'end_time': None,  # Will be set when meeting ends
                            'bots': [{
                                'bot_id': bot_id,
                                'join_at': None,  # Joined immediately
                                'created_at': datetime.now().isoformat(),
                                'status': 'joining',
                            }],
                            'is_manual': True,  # Mark as manually created
                        },
                        should_record_manual=True,  # Mark as manual recording
                    )
                    print(f'[BotCreator] ✓ Created CalendarEvent {calendar_event.id} for manual meeting')
                    print(f'[BotCreator]   Bot ID: {bot_id}')
                    print(f'[BotCreator]   Calendar ID: {manual_calendar.id}')
                    print(f'[BotCreator]   Backend User ID: {backend_user_id}')
                except Exception as e:
                    print(f'[BotCreator] ❌ ERROR: Could not create CalendarEvent for manual meeting: {e}')
                    traceback.print_exc()
                    calendar_event = None
            
            # Fetch owner name (OPTIONAL - will be None if unavailable)
            owner_name = get_user_name_from_backend(backend_user_id) if backend_user_id else None
            if owner_name:
                print(f'[BotCreator] Fetched owner name: {owner_name}')
            else:
                print(f'[BotCreator] ⚠ Owner name not available (optional, will continue without it)')
            
            # Create BotRecording placeholder - MUST link to calendar_event if it exists
            try:
                from app.models import BotRecording
                # Initialize recall_data with owner_name if available
                recall_data_dict = bot_data.copy() if isinstance(bot_data, dict) else {}
                if owner_name:
                    if not recall_data_dict:
                        recall_data_dict = {}
                    recall_data_dict['owner_name'] = owner_name
                
                bot_recording, created = BotRecording.objects.update_or_create(
                    bot_id=bot_id,
                    defaults={
                        'recall_data': recall_data_dict,
                        'status': 'joining',  # Bot is joining immediately
                        'calendar_event_id': calendar_event.id if calendar_event else None,
                        'backend_user_id': backend_user_id,
                        'workspace_id': workspace_id,  # Required - always set
                        'folder_id': folder_id,  # Optional - None means unresolved
                    }
                )
                
                # If bot_recording already exists, update owner_name if available
                if not created and owner_name:
                    if not bot_recording.recall_data:
                        bot_recording.recall_data = {}
                    bot_recording.recall_data['owner_name'] = owner_name
                    bot_recording.save(update_fields=['recall_data'])
                    print(f'[BotCreator] ✓ Stored owner name in existing BotRecording: {owner_name}')
                elif created and owner_name:
                    print(f'[BotCreator] ✓ Stored owner name in BotRecording: {owner_name}')
                
                if calendar_event:
                    print(f'[BotCreator] ✓ Created/Updated BotRecording {bot_recording.id} linked to CalendarEvent {calendar_event.id}')
                else:
                    print(f'[BotCreator] ⚠ WARNING: Created BotRecording {bot_recording.id} but NO CalendarEvent (transcriptions may not be saved)')
            except Exception as e:
                print(f'[BotCreator] ❌ ERROR: Could not create BotRecording: {e}')
                traceback.print_exc()
            
            return {
                'success': True,
                'bot_id': bot_id,
                'bot_data': bot_data
            }
        else:
            return {
                'success': False,
                'error': f'Failed to get bot_id from response: {bot_data}'
            }
            
    except Exception as e:
        error_msg = str(e)
        traceback.print_exc()
        return {
            'success': False,
            'error': error_msg
        }


def _detect_platform(meeting_url):
    """Detect platform from meeting URL"""
    url_lower = meeting_url.lower()
    if "zoom.us" in url_lower or "zoom.com" in url_lower:
        return "zoom"
    elif "meet.google.com" in url_lower or "google.com/calendar" in url_lower:
        return "google_meet"
    elif "teams.microsoft.com" in url_lower or "teams.live.com" in url_lower:
        return "microsoft_teams"
    elif "gotomeeting.com" in url_lower or "gotomeet.com" in url_lower or "g2m.com" in url_lower:
        return "gotomeeting"
    return None


def _build_recording_config():
    """
    Build recording configuration similar to meeting-bot implementation
    """
    # Get public URL for webhooks (from PUBLIC_URL env var)
    public_url = os.getenv('PUBLIC_URL', '')
    ws_token = os.getenv('WS_TOKEN', 'dev-secret')
    
    # Build webhook endpoint
    endpoints = []
    
    if public_url:
        # Add webhook endpoint
        endpoints.append({
            "type": "webhook",
            "url": f"{public_url}/wh",
            "events": [
                "transcript.data",
                "participant_events.join",
                "participant_events.leave",
                "participant_events.update",
                "participant_events.speech_on",
                "participant_events.speech_off",
                "participant_events.webcam_on",
                "participant_events.webcam_off",
                "participant_events.screenshare_on",
                "participant_events.screenshare_off",
                "participant_events.chat_message"
            ],
        })
        
        # Add websocket endpoint if configured
        ws_url = None
        if public_url.startswith('https://'):
            ws_url = public_url.replace('https://', 'wss://') + f'/ws/rt?token={ws_token}'
        elif public_url.startswith('http://'):
            ws_url = public_url.replace('http://', 'ws://') + f'/ws/rt?token={ws_token}'
        
        if ws_url:
            endpoints.append({
                "type": "websocket",
                "url": ws_url,
                "events": ["audio_mixed_raw.data", "transcript.data"]
            })
    
    # Get logo URL (if PUBLIC_URL is set, serve logo from static files)
    logo_url = None
    if public_url:
        logo_url = f"{public_url}/static/ellie-logo.svg"
    
    # Build recording config
    # Use AssemblyAI for realtime transcription if configured in Recall.ai dashboard
    # Note: AssemblyAI credentials must be configured in Recall.ai dashboard first
    # https://us-west-2.recall.ai/dashboard/transcription
    # Check if USE_ASSEMBLY_AI is set to 'true' (case-insensitive)
    # IMPORTANT: The API key itself should be configured in Recall.ai dashboard, not here
    use_assembly_ai_env = os.getenv('USE_ASSEMBLY_AI', '').strip()
    use_assembly_ai = use_assembly_ai_env.lower() == 'true'
    
    if use_assembly_ai_env and use_assembly_ai_env.lower() != 'true' and use_assembly_ai_env.lower() != 'false':
        # If it's set but not 'true' or 'false', it might be an API key - warn user
        print(f'WARNING: USE_ASSEMBLY_AI is set to "{use_assembly_ai_env[:10]}..." but should be "true" or "false"')
        print('WARNING: AssemblyAI API key should be configured in Recall.ai dashboard, not in .env file')
        print('WARNING: Setting USE_ASSEMBLY_AI=true to enable AssemblyAI (assuming you want it enabled)')
        use_assembly_ai = True
    
    transcript_provider = {}
    if use_assembly_ai:
        # Use AssemblyAI v3 streaming for realtime transcription (as per demo project)
        # IMPORTANT: AssemblyAI credentials must be configured in Recall.ai dashboard
        # Go to: https://us-west-2.recall.ai/dashboard/transcription (or your region)
        # This matches the assemblyai-recallai-zoom-bot demo implementation
        # IMPORTANT: As per demo project, we only set format_turns here
        # Summarization and action_items are NOT set in bot creation
        # They need to be requested when we SUBMIT audio to AssemblyAI for final processing
        # However, with streaming transcription, we get real-time transcripts via webhooks
        # For final transcript with summary/action_items, we need to check if AssemblyAI
        # creates a transcript that can be fetched, or we need to submit the audio separately
        transcript_provider = {
            "assembly_ai_v3_streaming": {
                # Enable formatted text with punctuation and proper casing (as per demo)
                "format_turns": True
            }
        }
        print(f'[BotCreator] Using AssemblyAI v3 streaming transcription (as per demo project)')
        print(f'[BotCreator] Configuration matches demo: only format_turns enabled')
        print(f'[BotCreator] Real-time transcripts will come via webhook (transcript.data events)')
        print(f'[BotCreator] For final transcript with summary/action_items, we will fetch from AssemblyAI API after meeting ends')
    else:
        # Default: Use Recall.ai streaming transcription
        # This works out of the box without additional configuration
        transcript_provider = {
            "recallai_streaming": {
                "language_code": "en",
                "filter_profanity": False,
                "mode": "prioritize_low_latency"
            }
        }
    
    recording_config = {
        "transcript": {
            "provider": transcript_provider,
            # Add logo URL to metadata (custom metadata field)
            "metadata": {
                "bot_avatar_url": logo_url
            } if logo_url else {}
        },
        "participant_events": {},
        "meeting_metadata": {
            "bot_name": "Ellie",
            "bot_avatar_url": logo_url
        } if logo_url else {
            "bot_name": "Ellie"
        },
        "start_recording_on": "participant_join",
        "audio_mixed_raw": {},
    }
    
    # Add realtime endpoints if configured
    if endpoints:
        recording_config["realtime_endpoints"] = endpoints
    
    # Add webhook endpoint for real-time transcripts (as per demo project)
    # This allows us to receive transcript.data and transcript.partial_data events
    if public_url:
        webhook_url = f"{public_url}/wh"
        if "realtime_endpoints" not in recording_config:
            recording_config["realtime_endpoints"] = []
        
        # Add webhook endpoint for transcript events (matching demo project)
        # Check if webhook endpoint already exists to avoid duplicates
        webhook_exists = any(
            ep.get("type") == "webhook" and ep.get("url") == webhook_url
            for ep in recording_config["realtime_endpoints"]
        )
        
        if not webhook_exists:
            recording_config["realtime_endpoints"].append({
                "type": "webhook",
                "events": [
                    "transcript.data",  # Final transcript segments
                    "transcript.partial_data"  # Real-time partial transcripts
                ],
                "url": webhook_url
            })
            print(f'[BotCreator] Added webhook endpoint for real-time transcripts: {webhook_url}')
    
    return recording_config

