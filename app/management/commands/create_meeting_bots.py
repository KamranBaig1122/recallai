"""
Django management command to automatically create meeting bots for calendar events.

This command:
1. Finds calendar events with meeting URLs that don't have bots yet
2. Creates bots with join_at set to the event's start_time
3. Bots will automatically join meetings at the scheduled time
4. Saves bot_id to event's recall_data

Usage:
    python manage.py create_meeting_bots
    
    # Create bots for events starting in next 24 hours
    python manage.py create_meeting_bots --hours-ahead 24
    
    # Create bots for specific calendar
    python manage.py create_meeting_bots --calendar-id <uuid>
    
    # Dry run (see what would be created)
    python manage.py create_meeting_bots --dry-run
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from app.models import CalendarEvent, Calendar
from app.services.recall.service import get_service
import os
import traceback


class Command(BaseCommand):
    help = 'Create meeting bots for calendar events with scheduled join times'

    def add_arguments(self, parser):
        parser.add_argument(
            '--hours-ahead',
            type=int,
            default=24,
            help='How many hours ahead to check for upcoming meetings (default: 24)',
        )
        parser.add_argument(
            '--calendar-id',
            type=str,
            help='Only process events for a specific calendar ID',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be created without actually creating bots',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Create bots even if event already has bots',
        )

    def handle(self, *args, **options):
        hours_ahead = options['hours_ahead']
        calendar_id = options.get('calendar_id')
        dry_run = options['dry_run']
        force = options['force']
        
        recall_service = get_service()
        now = timezone.now()
        check_until = now + timedelta(hours=hours_ahead)
        
        self.stdout.write(
            self.style.SUCCESS(
                f'Checking for meetings starting between {now} and {check_until}'
            )
        )
        
        # Get events to process
        events_query = CalendarEvent.objects.all()
        
        if calendar_id:
            events_query = events_query.filter(calendar_id=calendar_id)
            self.stdout.write(f'Filtering for calendar: {calendar_id}')
        
        events_to_process = []
        
        for event in events_query:
            try:
                # Check if event has meeting URL
                meeting_url = event.meeting_url
                if not meeting_url:
                    continue
                
                # Check start time
                start_time = event.start_time
                if not start_time:
                    continue
                
                # Convert to timezone-aware if needed
                if timezone.is_naive(start_time):
                    start_time = timezone.make_aware(start_time)
                
                # Check if starting in the future and within our time window
                if start_time <= now:
                    # Event already started or passed, skip
                    continue
                
                if start_time > check_until:
                    # Event is too far in the future
                    continue
                
                # Check if already has a bot (unless force=True)
                if not force:
                    bots = event.bots
                    if bots and len(bots) > 0:
                        self.stdout.write(
                            self.style.WARNING(
                                f'Event {event.id} ({event.title}) already has {len(bots)} bot(s). Skipping.'
                            )
                        )
                        continue
                
                events_to_process.append(event)
                
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(
                        f'Error processing event {event.id}: {e}'
                    )
                )
                traceback.print_exc()
                continue
        
        self.stdout.write(
            self.style.SUCCESS(
                f'Found {len(events_to_process)} event(s) to process'
            )
        )
        
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No bots will be created'))
            for event in events_to_process:
                self.stdout.write(
                    f'  Would create bot for: {event.title} at {event.start_time} ({event.meeting_url})'
                )
            return
        
        # Create bots for each event
        success_count = 0
        error_count = 0
        
        for event in events_to_process:
            try:
                self.stdout.write(
                    f'Creating bot for event: {event.title} at {event.start_time}'
                )
                
                # Detect platform from URL
                platform = self._detect_platform(event.meeting_url)
                
                # Build recording config (similar to meeting-bot implementation)
                recording_config = self._build_recording_config()
                
                # Format join_at as ISO 8601
                join_at = event.start_time.isoformat()
                
                # Get region from environment (default to us-west-2)
                region = os.getenv('RECALL_REGION', 'us-west-2')
                
                # Create the bot with join_at
                # Bot name is "Ellie - AI recording, memory and recall"
                bot_data = recall_service.create_bot(
                    meeting_url=event.meeting_url,
                    bot_name="Ellie - AI recording, memory and recall",
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
                    
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'✓ Created bot {bot_id} for event {event.id} (will join at {join_at})'
                        )
                    )
                    success_count += 1
                else:
                    self.stdout.write(
                        self.style.ERROR(
                            f'✗ Failed to get bot_id from response: {bot_data}'
                        )
                    )
                    error_count += 1
                    
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(
                        f'✗ Error creating bot for event {event.id}: {e}'
                    )
                )
                traceback.print_exc()
                error_count += 1
        
        # Summary
        self.stdout.write('')
        self.stdout.write(
            self.style.SUCCESS(
                f'Completed: {success_count} successful, {error_count} errors'
            )
        )
    
    def _detect_platform(self, meeting_url):
        """Detect platform from meeting URL"""
        url_lower = meeting_url.lower()
        if "zoom.us" in url_lower or "zoom.com" in url_lower:
            return "zoom"
        elif "meet.google.com" in url_lower or "google.com/calendar" in url_lower:
            return "google_meet"
        elif "teams.microsoft.com" in url_lower or "teams.live.com" in url_lower:
            return "microsoft_teams"
        return None
    
    def _build_recording_config(self):
        """
        Build recording configuration similar to meeting-bot implementation
        Based on official docs and meeting-bot/app/pythonHowToBuildABot.py
        """
        import os
        
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
        # Check if USE_ASSEMBLY_AI is set (can be 'true' or any non-empty value)
        use_assembly_ai_env = os.getenv('USE_ASSEMBLY_AI', '').strip()
        use_assembly_ai = use_assembly_ai_env.lower() == 'true' or (use_assembly_ai_env and use_assembly_ai_env.lower() != 'false')
        
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
                "bot_name": "Ellie - AI recording, memory and recall",
                "bot_avatar_url": logo_url
            } if logo_url else {
                "bot_name": "Ellie - AI recording, memory and recall"
            },
            "start_recording_on": "participant_join",
            "audio_mixed_raw": {},
        }
        
        # Add realtime endpoints if configured
        if endpoints:
            recording_config["realtime_endpoints"] = endpoints
        
        return recording_config

