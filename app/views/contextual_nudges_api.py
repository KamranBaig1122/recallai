"""
API endpoint for fetching contextual nudges from previous meetings
with matching participants to the current live meeting
"""
import json
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.db import OperationalError, DatabaseError
from datetime import timedelta
from app.models import MeetingTranscription, CalendarEvent, BotRecording
from app.views.calendar_api import add_cors_headers, get_backend_user_id_from_request


def extract_participants_from_transcription(transcription: MeetingTranscription):
    """
    Extract unique participant names from a transcription (case-insensitive matching)
    Excludes bot names as they're not real participants for matching purposes
    
    Uses two sources (in priority order):
    1. Stored participants from webhook events (real-time, most accurate)
    2. Utterances from transcript (fallback if webhook data not available)
    
    Args:
        transcription: MeetingTranscription instance
        
    Returns:
        Set of participant names (normalized - whitespace trimmed, case-insensitive for matching)
        Note: Returns original case for display, but matching uses lowercase
    """
    participants = set()
    
    # Exclude bot names (they're not real participants for matching purposes)
    bot_names = {'bot', 'ellie', 'recall', 'recall.ai', 'recall bot', 'ellie bot'}
    
    # Priority 1: Get participants from webhook events (stored in transcript_data.participants)
    # This is the most accurate source as it's updated in real-time when participants join
    stored_participants = transcription.transcript_data.get('participants', [])
    if stored_participants and isinstance(stored_participants, list):
        for participant in stored_participants:
            if isinstance(participant, dict):
                name = participant.get('name')
                
                if name and isinstance(name, str):
                    # Normalize: trim whitespace, preserve original case for display
                    normalized_name = name.strip()
                    # Exclude bots (not real participants for matching)
                    if normalized_name and normalized_name.lower() not in bot_names:
                        participants.add(normalized_name)
    
    # Priority 2: Fallback to utterances (if no webhook participant data available)
    if not participants:
        utterances = transcription.utterances
        if utterances and isinstance(utterances, list):
            for utterance in utterances:
                speaker = utterance.get('speaker')
                
                if speaker and isinstance(speaker, str):
                    # Normalize: trim whitespace, preserve original case for display
                    normalized_name = speaker.strip()
                    # Exclude bots (not real participants for matching)
                    if normalized_name and normalized_name.lower() not in bot_names:
                        participants.add(normalized_name)
    
    return participants




def get_live_meeting_participants(bot_id: str, backend_user_id: str):
    """
    Get current participants from a live meeting transcription
    
    SIMPLIFIED APPROACH: Uses BotRecording.status as the single source of truth.
    - If BotRecording.status is 'completed', meeting is NOT live
    - If BotRecording.status is 'joining' or 'processing', meeting is live
    - BotRecording.status is updated by webhook handler when bot.done is received
    
    Args:
        bot_id: Bot ID of the live meeting (optional - will find most recent if not provided)
        backend_user_id: User ID
        
    Returns:
        Tuple of (participant_names_list, transcription_object, participant_id_to_name_dict)
        - participant_names_list: List of participant names
        - transcription_object: MeetingTranscription object or None
        - participant_id_to_name_dict: Dict mapping participant_id -> name (for disambiguation)
    """
    
    transcription = None
    
    if bot_id:
        # SIMPLIFIED: Check BotRecording.status as single source of truth
        bot_recording = BotRecording.objects.filter(
            bot_id=bot_id,
            backend_user_id=backend_user_id
        ).first()
        
        if not bot_recording:
            print(f'[ContextualNudgesAPI] No BotRecording found for bot_id {bot_id}')
            return [], None, {}
        
        # Re-fetch to ensure we get latest data
        bot_recording = BotRecording.objects.get(id=bot_recording.id)
        bot_status = bot_recording.status
        
        print(f'[ContextualNudgesAPI] Bot {bot_id}: status={bot_status}')
        
        # Find transcription for this bot
        transcription = MeetingTranscription.objects.filter(
            bot_id=bot_id,
            backend_user_id=backend_user_id
        ).order_by('-updated_at').first()
        
        # Check if transcription was recently updated (within last 3 minutes)
        # This handles cases where bot.done was received but meeting is still "live" for nudges
        is_recently_updated = False
        if transcription and transcription.updated_at:
            three_minutes_ago = timezone.now() - timedelta(minutes=3)
            is_recently_updated = transcription.updated_at >= three_minutes_ago
            if is_recently_updated:
                print(f'[ContextualNudgesAPI] Transcription for bot {bot_id} was updated recently ({transcription.updated_at}), considering as potentially live')
        
        # If bot status is 'completed' but transcription was updated very recently (within 3 min),
        # still consider it live if transcription has participants and status is not 'completed'
        if bot_status == 'completed':
            if is_recently_updated and transcription:
                # Check if transcription has participants and is not marked as completed
                if transcription.status != 'completed':
                    participants = extract_participants_from_transcription(transcription)
                    if participants:
                        print(f'[ContextualNudgesAPI] Bot status is completed but transcription was updated recently with participants - treating as live')
                        # Continue to return transcription (will be handled below)
                    else:
                        print(f'[ContextualNudgesAPI] Bot status is completed and no participants found - meeting is NOT live')
                        return [], None, {}
                else:
                    print(f'[ContextualNudgesAPI] Bot status is completed and transcription status is completed - meeting is NOT live')
                    return [], None, {}
            else:
                print(f'[ContextualNudgesAPI] Bot status is completed and transcription not recently updated - meeting is NOT live')
                return [], None, {}
        
        # CRITICAL CHECK: If transcription exists and is completed AND not recently updated, meeting is NOT live
        if transcription and transcription.status == 'completed' and not is_recently_updated:
            print(f'[ContextualNudgesAPI] Transcription status is completed for bot {bot_id} and not recently updated, meeting is NOT live')
            return [], None, {}
        
        # STRICT CHECK: Only consider meeting live if bot_status is 'joining' or 'processing' AND transcription exists AND was recently updated
        if bot_status in ['joining', 'processing']:
            # Require transcription to exist - if no transcription, meeting is not live
            if not transcription:
                print(f'[ContextualNudgesAPI] Bot status is {bot_status} but no transcription found - meeting is NOT live')
                return [], None, {}
            
            # CRITICAL: Check if transcription was recently updated (within last 5 minutes)
            # This is the primary indicator that the meeting is live - transcription should be updating regularly
            if transcription.updated_at:
                five_minutes_ago = timezone.now() - timedelta(minutes=5)
                if transcription.updated_at < five_minutes_ago:
                    print(f'[ContextualNudgesAPI] Transcription for bot {bot_id} was last updated {transcription.updated_at} (more than 5 min ago), treating as NOT live (stale)')
                    return [], None, {}
            else:
                # If transcription has no updated_at timestamp, it's likely old/incomplete - not live
                print(f'[ContextualNudgesAPI] Transcription for bot {bot_id} has no updated_at timestamp - treating as NOT live')
                return [], None, {}
            
            # Also check if bot recording was recently updated (within last 10 minutes)
            # This is a secondary check - bot status should be updated during active meetings
            if bot_recording.updated_at:
                ten_minutes_ago = timezone.now() - timedelta(minutes=10)
                if bot_recording.updated_at < ten_minutes_ago:
                    print(f'[ContextualNudgesAPI] Bot {bot_id} status is {bot_status} but last updated {bot_recording.updated_at} (more than 10 min ago), treating as NOT live (stale)')
                    return [], None, {}
        else:
            print(f'[ContextualNudgesAPI] Bot status is {bot_status}, meeting is NOT live')
            transcription = None
    else:
        # SIMPLIFIED: Find most recent live meeting by checking BotRecording.status
        # Get all bot recordings for this user, find one with status='joining' or 'processing'
        bot_recordings = BotRecording.objects.filter(
            backend_user_id=backend_user_id
        ).order_by('-created_at')
        
        # Reset transcription to None - only set it when we find a valid live meeting
        transcription = None
        
        for bot_recording in bot_recordings[:5]:  # Check up to 5 most recent
            # Re-fetch to ensure we get latest data
            bot_recording = BotRecording.objects.get(id=bot_recording.id)
            bot_status = bot_recording.status
            
            print(f'[ContextualNudgesAPI] Checking bot {bot_recording.bot_id}: status={bot_status}')
            
            # Find transcription for this bot
            current_transcription = MeetingTranscription.objects.filter(
                bot_id=bot_recording.bot_id,
                backend_user_id=backend_user_id
            ).order_by('-updated_at').first()
            
            # Check if transcription was recently updated (within last 3 minutes)
            # This handles cases where bot.done was received but meeting is still "live" for nudges
            is_recently_updated = False
            if current_transcription and current_transcription.updated_at:
                three_minutes_ago = timezone.now() - timedelta(minutes=3)
                is_recently_updated = current_transcription.updated_at >= three_minutes_ago
                if is_recently_updated:
                    print(f'[ContextualNudgesAPI] Transcription for bot {bot_recording.bot_id} was updated recently ({current_transcription.updated_at}), considering as potentially live')
            
            # If bot status is 'completed' but transcription was updated very recently (within 3 min),
            # still consider it live if transcription has participants and status is not 'completed'
            if bot_status == 'completed':
                if is_recently_updated and current_transcription:
                    # Check if transcription has participants and is not marked as completed
                    if current_transcription.status != 'completed':
                        participants_check = extract_participants_from_transcription(current_transcription)
                        if participants_check:
                            print(f'[ContextualNudgesAPI] Bot {bot_recording.bot_id} status is completed but transcription was updated recently with participants - treating as live')
                            # Set transcription and break - this is a live meeting
                            transcription = current_transcription
                            print(f'[ContextualNudgesAPI] Found live meeting (bot_id: {bot_recording.bot_id}, bot_status: {bot_status}, recently updated)')
                            break
                        else:
                            print(f'[ContextualNudgesAPI] Bot {bot_recording.bot_id} status is completed and no participants found - skipping')
                            continue
                    else:
                        print(f'[ContextualNudgesAPI] Bot {bot_recording.bot_id} status is completed and transcription status is completed - skipping')
                        continue
                else:
                    print(f'[ContextualNudgesAPI] Bot {bot_recording.bot_id} status is completed and transcription not recently updated - skipping')
                    continue
            
            # CRITICAL CHECK: If transcription exists and is completed AND not recently updated, skip this bot
            if current_transcription and current_transcription.status == 'completed' and not is_recently_updated:
                print(f'[ContextualNudgesAPI] Transcription status is completed for bot {bot_recording.bot_id} and not recently updated, skipping')
                continue
            
            # STRICT CHECK: Only consider meeting live if bot_status is 'joining' or 'processing' AND transcription exists AND was recently updated
            if bot_status in ['joining', 'processing']:
                # Require transcription to exist - if no transcription, skip this bot
                if not current_transcription:
                    print(f'[ContextualNudgesAPI] Bot {bot_recording.bot_id} status is {bot_status} but no transcription found - skipping')
                    continue
                
                # CRITICAL: Check if transcription was recently updated (within last 5 minutes)
                # This is the primary indicator that the meeting is live - transcription should be updating regularly
                if current_transcription.updated_at:
                    five_minutes_ago = timezone.now() - timedelta(minutes=5)
                    if current_transcription.updated_at < five_minutes_ago:
                        print(f'[ContextualNudgesAPI] Transcription for bot {bot_recording.bot_id} was last updated {current_transcription.updated_at} (more than 5 min ago), skipping (stale)')
                        continue
                else:
                    # If transcription has no updated_at timestamp, it's likely old/incomplete - skip
                    print(f'[ContextualNudgesAPI] Transcription for bot {bot_recording.bot_id} has no updated_at timestamp - skipping')
                    continue
                
                # Also check if bot recording was recently updated (within last 10 minutes)
                # This is a secondary check - bot status should be updated during active meetings
                if bot_recording.updated_at:
                    ten_minutes_ago = timezone.now() - timedelta(minutes=10)
                    if bot_recording.updated_at < ten_minutes_ago:
                        print(f'[ContextualNudgesAPI] Bot {bot_recording.bot_id} status is {bot_status} but last updated {bot_recording.updated_at} (more than 10 min ago), skipping (stale)')
                        continue
                
                # All checks passed - this is a live meeting
                # Set transcription to the current transcription only when we've confirmed it's live
                transcription = current_transcription
                print(f'[ContextualNudgesAPI] Found live meeting (bot_id: {bot_recording.bot_id}, bot_status: {bot_status})')
                break
        
        # Only print this if we actually found a live meeting (transcription is not None)
        if transcription:
            print(f'[ContextualNudgesAPI] Found most recent live meeting (bot_id: {transcription.bot_id})')
    
    # If no transcription found, return empty (no live meeting)
    if not transcription:
        print(f'[ContextualNudgesAPI] No live meeting transcription found')
        return [], None, {}
    
    participants = extract_participants_from_transcription(transcription)
    participant_list = sorted(list(participants))
    
    print(f'[ContextualNudgesAPI] Found {len(participant_list)} participants in live meeting: {participant_list}')
    
    return participant_list, transcription, {}  # Return empty dict for backward compatibility


def find_previous_meetings_with_participants(
    backend_user_id: str,
    current_participants: list,
    current_participant_ids: dict = None,  # Not used, kept for backward compatibility
    min_matching_participants: int = 1  # Not used, kept for backward compatibility
) -> list[MeetingTranscription]:
    """
    Find previous completed meetings where ALL current participants were present.
    
    DYNAMIC MATCHING STRATEGY:
    1. If only 1 participant → return empty (no nudges for solo meetings)
    2. If 2+ participants → find meetings where ALL of them were present
    3. Uses case-insensitive name matching for better matching
    4. When a new participant joins, automatically updates to show meetings with ALL participants
    
    Args:
        backend_user_id: User ID
        current_participants: List of current meeting participant names
        current_participant_ids: Not used, kept for backward compatibility
        min_matching_participants: Not used, kept for backward compatibility
        
    Returns:
        List of MeetingTranscription objects with matching participants
    """
    if not current_participants:
        print(f'[ContextualNudgesAPI] No current participants provided - returning empty')
        return []
    
    # Normalize current participants (trim whitespace, case-insensitive matching)
    # Store both original case (for display) and lowercase (for matching)
    current_participants_normalized = {p.strip().lower(): p.strip() for p in current_participants if p.strip()}
    current_participants_lower = set(current_participants_normalized.keys())
    
    # If only 1 participant → return empty (no nudges for solo meetings)
    if len(current_participants_lower) <= 1:
        print(f'[ContextualNudgesAPI] Only {len(current_participants_lower)} participant(s) - returning empty (no nudges for solo meetings)')
        return []
    
    print(f'[ContextualNudgesAPI] ==========================================')
    print(f'[ContextualNudgesAPI] 🔍 SEARCHING FOR MATCHING MEETINGS')
    print(f'[ContextualNudgesAPI] Current meeting has {len(current_participants_lower)} participants: {sorted([current_participants_normalized[p] for p in current_participants_lower])}')
    print(f'[ContextualNudgesAPI] Will show meetings where ALL of these participants were present')
    print(f'[ContextualNudgesAPI] ==========================================')
    
    # Get all completed transcriptions for this user that have contextual nudges
    transcriptions = MeetingTranscription.objects.filter(
        backend_user_id=backend_user_id,
        status='completed',
        contextual_nudges__isnull=False
    ).exclude(
        contextual_nudges=[]  # Exclude empty arrays
    ).order_by('-created_at')  # Most recent first
    
    print(f'[ContextualNudgesAPI] Checking {len(transcriptions)} completed meetings with contextual nudges')
    
    matching_transcriptions = []
    
    for transcription in transcriptions:
        # Extract participants from this meeting
        meeting_participants = extract_participants_from_transcription(transcription)
        
        # Normalize meeting participants to lowercase for case-insensitive matching
        meeting_participants_lower = {p.lower() for p in meeting_participants}
        
        # Check if ALL current participants (case-insensitive) are present in this meeting
        if current_participants_lower.issubset(meeting_participants_lower):
            matching_transcriptions.append(transcription)
            print(f'[ContextualNudgesAPI] ✅ MATCH FOUND: Meeting {transcription.id}')
            print(f'[ContextualNudgesAPI]   Meeting participants: {sorted(list(meeting_participants))}')
            print(f'[ContextualNudgesAPI]   Current participants: {sorted([current_participants_normalized[p] for p in current_participants_lower])}')
            print(f'[ContextualNudgesAPI]   All current participants were present in this meeting')
        else:
            # Debug: Show why it didn't match (only for first few non-matches to avoid spam)
            if len(matching_transcriptions) == 0 and len([t for t in transcriptions[:3] if t.id == transcription.id]) > 0:
                missing = current_participants_lower - meeting_participants_lower
                if missing:
                    print(f'[ContextualNudgesAPI] ❌ No match: Meeting {transcription.id} missing participants: {sorted([current_participants_normalized[p] for p in missing])}')
    
    print(f'[ContextualNudgesAPI] ==========================================')
    print(f'[ContextualNudgesAPI] Found {len(matching_transcriptions)} meetings where all participants were present')
    print(f'[ContextualNudgesAPI] ==========================================')
    
    return matching_transcriptions


def extract_nudges_from_meetings(
    matching_transcriptions: list[MeetingTranscription]
) -> list[dict]:
    """
    Extract contextual nudges from matching meetings with metadata
    
    Args:
        matching_transcriptions: List of MeetingTranscription objects
        
    Returns:
        List of nudge dictionaries with meeting context
    """
    all_nudges = []
    
    for transcription in matching_transcriptions:
        # Get meeting title from calendar event
        meeting_title = "Unknown Meeting"
        meeting_date = transcription.created_at.isoformat() if transcription.created_at else None
        
        try:
            event = CalendarEvent.objects.get(id=transcription.calendar_event_id)
            meeting_title = event.title or "Unknown Meeting"
            meeting_date = event.start_time.isoformat() if event.start_time else meeting_date
        except CalendarEvent.DoesNotExist:
            print(f'[ContextualNudgesAPI] Calendar event not found for transcription {transcription.id}')
        
        # Get participants from this meeting
        meeting_participants = extract_participants_from_transcription(transcription)
        participants_list = sorted(list(meeting_participants))
        
        # Get contextual nudges
        nudges = transcription.contextual_nudges
        if nudges and isinstance(nudges, list):
            for nudge in nudges:
                if isinstance(nudge, dict):
                    nudge_with_context = {
                        "id": f"{transcription.id}-{len(all_nudges)}",
                        "text": nudge.get("text", "").strip(),
                        "type": nudge.get("type", "general"),
                        "timestamp": nudge.get("timestamp", ""),
                        "speaker": nudge.get("speaker", ""),
                        "explanation": nudge.get("explanation", ""),
                        "meeting_context": {
                            "meeting_id": str(transcription.id),
                            "meeting_title": meeting_title,
                            "meeting_date": meeting_date,
                            "participants": participants_list
                        }
                    }
                    all_nudges.append(nudge_with_context)
    
    return all_nudges


@require_http_methods(["GET", "OPTIONS"])
@csrf_exempt
def api_get_contextual_nudges(request):
    """
    API endpoint to get contextual nudges for the current live meeting.
    
    Query Parameters:
        - userId: User ID (optional if JWT token is provided)
        - botId: Bot ID of current live meeting (optional, but required for live meeting)
    
    Returns:
        JSON response with:
        - success: bool
        - has_live_meeting: bool
        - live_meeting_bot_id: str | None
        - current_participants: list[str]
        - nudges: list[dict]
        - total_nudges: int
    """
    if request.method == 'OPTIONS':
        response = JsonResponse({})
        return add_cors_headers(response, request)
    
    try:
        # Get backend_user_id from request
        backend_user_id = get_backend_user_id_from_request(request)
        if not backend_user_id:
            response = JsonResponse({
                'success': False,
                'error': 'Authentication required. Provide JWT token or userId parameter'
            }, status=400)
            return add_cors_headers(response, request)
        
        # Get bot_id from query params (optional)
        bot_id = request.GET.get('botId') or request.GET.get('bot_id')
        
        print(f'[ContextualNudgesAPI] ==========================================')
        print(f'[ContextualNudgesAPI] 📋 GET CONTEXTUAL NUDGES REQUEST')
        print(f'[ContextualNudgesAPI] User ID: {backend_user_id}')
        print(f'[ContextualNudgesAPI] Bot ID: {bot_id or "Not provided (will find most recent)"}')
        print(f'[ContextualNudgesAPI] ==========================================')
        
        # Step 1: Get current live meeting participants
        # bot_id is optional - will find most recent live meeting if not provided
        current_participants, live_transcription, current_participant_ids = get_live_meeting_participants(
            bot_id, backend_user_id
        )
        
        # Check if we have a live meeting (either via transcription or via live bot)
        has_live_meeting = live_transcription is not None
        live_bot_id = None
        
        if live_transcription:
            live_bot_id = live_transcription.bot_id
            has_live_meeting = True
        else:
            # No transcription found - this means no live meeting
            # Don't check BotRecording alone - we need both bot AND transcription to be live
            print(f'[ContextualNudgesAPI] No transcription found - meeting is NOT live (requires both bot and transcription to be active)')
            has_live_meeting = False
        
        if not has_live_meeting:
            print(f'[ContextualNudgesAPI] No live meeting found or bot_id not provided')
            response = JsonResponse({
                'success': True,
                'has_live_meeting': False,
                'live_meeting_bot_id': None,
                'current_participants': [],
                'nudges': [],
                'total_nudges': 0,
                'message': 'No live meeting detected. Contextual nudges are only available during live meetings.'
            })
            return add_cors_headers(response, request)
        
        if not current_participants:
            print(f'[ContextualNudgesAPI] No participants found in live meeting yet (bot is live but waiting for transcripts)')
            response = JsonResponse({
                'success': True,
                'has_live_meeting': True,
                'live_meeting_bot_id': live_bot_id,
                'current_participants': [],
                'nudges': [],
                'total_nudges': 0,
                'message': 'No participants detected in live meeting yet. Waiting for transcripts...'
            })
            return add_cors_headers(response, request)
        
        # Step 2: Find previous meetings where ALL current participants were present
        matching_meetings = find_previous_meetings_with_participants(
            backend_user_id,
            current_participants
        )
        
        if not matching_meetings:
            print(f'[ContextualNudgesAPI] No previous meetings found with matching participants')
            response = JsonResponse({
                'success': True,
                'has_live_meeting': True,
                'live_meeting_bot_id': live_bot_id,
                'current_participants': current_participants,
                'nudges': [],
                'total_nudges': 0,
                'message': 'No previous meetings found with matching participants.'
            })
            return add_cors_headers(response, request)
        
        # Step 3: Extract nudges from matching meetings
        all_nudges = extract_nudges_from_meetings(matching_meetings)
        
        print(f'[ContextualNudgesAPI] ✅ Successfully retrieved {len(all_nudges)} contextual nudges')
        print(f'[ContextualNudgesAPI] ==========================================')
        
        # Include bot_id in response for frontend to use in polling
        response_data = {
            'success': True,
            'has_live_meeting': True,
            'live_meeting_bot_id': live_bot_id,
            'current_participants': current_participants,
            'nudges': all_nudges,
            'total_nudges': len(all_nudges)
        }
        
        response = JsonResponse(response_data)
        return add_cors_headers(response, request)
        
    except (OperationalError, DatabaseError) as e:
        print(f'[ContextualNudgesAPI] ❌ Database error: {e}')
        response = JsonResponse({
            'success': False,
            'error': 'Database connection error. Please try again later.'
        }, status=500)
        return add_cors_headers(response, request)
    except Exception as e:
        print(f'[ContextualNudgesAPI] ❌ ERROR: {e}')
        import traceback
        traceback.print_exc()
        response = JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
        return add_cors_headers(response, request)
