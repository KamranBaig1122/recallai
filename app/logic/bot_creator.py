"""
Helper functions to create meeting bots for calendar events
Uses Recall.ai API directly with join_at for scheduled bot joining
"""
from django.utils import timezone
from app.models import CalendarEvent
from app.services.recall.service import get_service
import os
import traceback


def create_bot_for_event(event: CalendarEvent, force: bool = False) -> dict:
    """
    Create a meeting bot for a calendar event with scheduled join time
    
    Args:
        event: CalendarEvent instance
        force: If True, create bot even if one already exists
        
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
    if start_time <= timezone.now():
        return {
            'success': False,
            'error': 'Event start time is in the past'
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
                BotRecording.objects.update_or_create(
                    bot_id=bot_id,
                    defaults={
                        'recall_data': bot_data,
                        'status': 'pending',
                        'calendar_event_id': event.id
                    }
                )
            except Exception as e:
                print(f'WARNING: Could not create BotRecording placeholder: {e}')
            
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


def _detect_platform(meeting_url):
    """Detect platform from meeting URL"""
    url_lower = meeting_url.lower()
    if "zoom.us" in url_lower or "zoom.com" in url_lower:
        return "zoom"
    elif "meet.google.com" in url_lower or "google.com/calendar" in url_lower:
        return "google_meet"
    elif "teams.microsoft.com" in url_lower or "teams.live.com" in url_lower:
        return "microsoft_teams"
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
        # Use AssemblyAI async chunked for realtime transcription
        # IMPORTANT: AssemblyAI credentials must be configured in Recall.ai dashboard
        # Go to: https://us-west-2.recall.ai/dashboard/transcription (or your region)
        transcript_provider = {
            "assembly_ai_async_chunked": {
                "language_code": "en_us",  # Default to US English
                "auto_highlights": False,
                "auto_chapters": False,
                "entity_detection": False,
                "sentiment_analysis": False,
                "speaker_labels": True,  # Enable speaker diarization
                "punctuate": True,
                "format_text": True,
                # Enable summarization
                "summarization": True,
                "summary_model": "informative",  # Options: "informative", "conversational", "catchy"
                "summary_type": "paragraph"  # Options: "bullets", "bullets_verbose", "gist", "headline", "paragraph"
            }
        }
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
    
    return recording_config

