"""
Email service for sending notifications about unresolved meetings.

This service sends emails to users when meetings remain unresolved,
including a list of available folders and direct assignment links.
"""
import os
import logging
import requests
from datetime import timedelta
from urllib.parse import quote
from django.core.mail import send_mail
from django.conf import settings
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.core.signing import Signer
from app.models import MeetingTranscription, CalendarEvent, BotRecording
from app.logic.backend_auth import get_backend_api_headers
from django.utils import timezone

logger = logging.getLogger(__name__)

# Initialize signer for secure token generation
# Use a salt to ensure tokens are specific to assignment links
signer = Signer(salt='assignment-token')


def get_user_email_from_backend(user_id: str) -> str | None:
    """
    Get user email from Invite-ellie-backend.
    Tries multiple approaches:
    1. Try /api/accounts/me/ with X-User-ID header (like bot_creator does)
    2. Try /api/accounts/{user_id}/ endpoint
    3. Try /api/accounts/profile/?user_id={user_id}
    4. Fallback: return None (will use calendar email as fallback)
    
    Args:
        user_id: Backend user ID (UUID string)
    
    Returns:
        User email or None if not found
    """
    try:
        api_base_url = os.environ.get('INVITE_ELLIE_BACKEND_API_URL', 'http://localhost:8000')
        
        # Try /api/accounts/me/ with X-User-ID header first (most reliable)
        try:
            headers = get_backend_api_headers({
                'X-User-ID': user_id,  # Include user ID in header
            })
            if headers:
                me_endpoint = f'{api_base_url}/api/accounts/me/'
                response = requests.get(me_endpoint, headers=headers, timeout=5)
                
                if response.status_code == 200:
                    profile_data = response.json()
                    if isinstance(profile_data, dict):
                        email = profile_data.get('email')
                        if email:
                            logger.info(f'[EmailService] Found user email via /api/accounts/me/ with X-User-ID header')
                            return email
        except Exception as e:
            logger.warning(f'[EmailService] Error trying /api/accounts/me/: {e}')
        
        # Fallback: Try other endpoints
        headers = get_backend_api_headers()
        if not headers:
            logger.error('[EmailService] Cannot get backend API headers')
            return None
        
        # Try endpoint with user_id in URL path
        endpoints_to_try = [
            f'{api_base_url}/api/accounts/{user_id}/',
            f'{api_base_url}/api/accounts/profile/?user_id={user_id}',
            f'{api_base_url}/api/users/{user_id}/',
        ]
        
        for endpoint in endpoints_to_try:
            try:
                response = requests.get(endpoint, headers=headers, timeout=5)
                
                if response.status_code == 200:
                    profile_data = response.json()
                    # Handle both single object and list responses
                    if isinstance(profile_data, list) and len(profile_data) > 0:
                        email = profile_data[0].get('email')
                        if email:
                            logger.info(f'[EmailService] Found user email via {endpoint}')
                            return email
                    elif isinstance(profile_data, dict):
                        email = profile_data.get('email')
                        if email:
                            logger.info(f'[EmailService] Found user email via {endpoint}')
                            return email
                elif response.status_code == 404:
                    # Try next endpoint
                    continue
                else:
                    logger.warning(f'[EmailService] Endpoint {endpoint} returned {response.status_code}: {response.text[:200]}')
            except requests.exceptions.RequestException as e:
                logger.warning(f'[EmailService] Error trying {endpoint}: {e}')
                continue
        
        logger.warning(f'[EmailService] Could not find user email for user_id {user_id} via any endpoint')
        return None
        
    except Exception as e:
        logger.error(f'[EmailService] Error getting user email: {e}')
        return None


def get_available_folders_for_user(user_id: str, workspace_id: str | None = None) -> list[dict]:
    """
    Get available folders for a user from Invite-ellie-backend.
    
    Args:
        user_id: Backend user ID (UUID string)
        workspace_id: Optional workspace ID to filter folders
    
    Returns:
        List of folder dictionaries with id, name, workspace_id
    """
    try:
        api_base_url = os.environ.get('INVITE_ELLIE_BACKEND_API_URL', 'http://localhost:8000')
        headers = get_backend_api_headers()
        
        if not headers:
            logger.error('[EmailService] Cannot get backend API headers')
            return []
        
        # Build URL with optional workspace filter
        url = f'{api_base_url}/api/folders/'
        params = {'page_size': 100}
        if workspace_id:
            params['workspace'] = workspace_id
        
        response = requests.get(url, headers=headers, params=params)
        
        if response.status_code == 200:
            data = response.json()
            folders = data.get('results', [])
            return [
                {
                    'id': folder.get('id'),
                    'name': folder.get('name'),
                    'workspace_id': folder.get('workspace'),
                    'workspace_name': folder.get('workspace_name', ''),
                }
                for folder in folders
            ]
        else:
            logger.error(f'[EmailService] Failed to get folders: {response.status_code}')
            return []
    except Exception as e:
        logger.error(f'[EmailService] Error getting folders: {e}')
        return []


def generate_assignment_token(meeting_id: str, user_id: str) -> str:
    """
    Generate a secure token for folder assignment link.
    
    Args:
        meeting_id: Meeting transcription ID
        user_id: Backend user ID
    
    Returns:
        Signed token string
    """
    # Create payload with expiry
    from datetime import datetime, timedelta
    from django.utils import timezone
    expiry = timezone.now() + timedelta(days=settings.ASSIGNMENT_TOKEN_EXPIRY_DAYS)
    payload = f'{meeting_id}:{user_id}:{expiry.isoformat()}'
    
    # Sign the payload
    token = signer.sign(payload)
    logger.debug(f'[EmailService] Generated token for meeting {meeting_id}, token length: {len(token)}')
    return token


def send_unresolved_meeting_email(meeting_transcription: MeetingTranscription):
    """
    Send email notification for unresolved meeting.
    
    Args:
        meeting_transcription: MeetingTranscription instance
    """
    if not meeting_transcription.backend_user_id:
        logger.error(f'[EmailService] Cannot send email: no backend_user_id for meeting {meeting_transcription.id}')
        return
    
    try:
        user_id = str(meeting_transcription.backend_user_id)
        
        # Get user email - try backend API first, then fallback to calendar/bot email
        user_email = get_user_email_from_backend(user_id)
        
        # Get meeting details and try to get email from calendar/bot as fallback
        event = None
        meeting_title = 'Untitled Meeting'
        meeting_date = 'Unknown date'
        meeting_time = 'Unknown time'
        
        try:
            event = CalendarEvent.objects.get(id=meeting_transcription.calendar_event_id)
            meeting_title = event.title or 'Untitled Meeting'
            meeting_date = event.start_time.strftime('%B %d, %Y') if event.start_time else 'Unknown date'
            meeting_time = event.start_time.strftime('%I:%M %p') if event.start_time else 'Unknown time'
        except CalendarEvent.DoesNotExist:
            logger.warning(f'[EmailService] CalendarEvent not found for meeting {meeting_transcription.id}, using defaults')
            # Meeting title remains 'Untitled Meeting' as set above
        
        # Fallback: try to get email from calendar associated with the meeting
        if not user_email and event:
            try:
                from app.models import Calendar
                if event.calendar_id:
                    calendar = Calendar.objects.get(id=event.calendar_id)
                    if calendar.email:
                        user_email = calendar.email
                        logger.info(f'[EmailService] Using calendar email as fallback: {user_email}')
            except Exception as e:
                logger.warning(f'[EmailService] Could not get email from calendar: {e}')
        
        # Fallback: try to get email from BotRecording
        if not user_email:
            try:
                from app.models import BotRecording
                bot_recording = BotRecording.objects.filter(
                    bot_id=meeting_transcription.bot_id
                ).first()
                if bot_recording and hasattr(bot_recording, 'calendar_email') and bot_recording.calendar_email:
                    user_email = bot_recording.calendar_email
                    logger.info(f'[EmailService] Using bot recording calendar_email as fallback: {user_email}')
            except Exception as e:
                logger.warning(f'[EmailService] Could not get email from bot recording: {e}')
        
        # Final fallback: try to get email from any calendar associated with this user
        if not user_email:
            try:
                from app.models import Calendar
                # Try to find any calendar for this user
                user_calendars = Calendar.objects.filter(
                    backend_user_id=user_id
                ).exclude(email__isnull=True).exclude(email='')
                
                if user_calendars.exists():
                    user_email = user_calendars.first().email
                    logger.info(f'[EmailService] Using first available calendar email as fallback: {user_email}')
            except Exception as e:
                logger.warning(f'[EmailService] Could not get email from user calendars: {e}')
        
        if not user_email:
            logger.error(f'[EmailService] Cannot send email: no email found for user {user_id} after all attempts')
            logger.error(f'[EmailService] Meeting ID: {meeting_transcription.id}, Bot ID: {meeting_transcription.bot_id}')
            return
        
        # Get available folders
        folders = get_available_folders_for_user(user_id, meeting_transcription.workspace_id)
        
        # Get workspace name - try from folders first, then fetch from API
        workspace_name = 'Your Workspace'
        if folders and folders[0].get('workspace_name'):
            workspace_name = folders[0]['workspace_name']
        elif meeting_transcription.workspace_id:
            # Fetch workspace name from API
            try:
                api_base_url = os.environ.get('INVITE_ELLIE_BACKEND_API_URL', 'http://localhost:8000')
                headers = get_backend_api_headers()
                if headers:
                    workspace_response = requests.get(
                        f'{api_base_url}/api/workspaces/{meeting_transcription.workspace_id}/',
                        headers=headers,
                        timeout=5
                    )
                    if workspace_response.status_code == 200:
                        workspace_data = workspace_response.json()
                        workspace_name = workspace_data.get('name', 'Your Workspace')
                        logger.info(f'[EmailService] Fetched workspace name: {workspace_name}')
            except Exception as e:
                logger.warning(f'[EmailService] Could not fetch workspace name: {e}')
        
        # Generate assignment token and link
        token = generate_assignment_token(str(meeting_transcription.id), user_id)
        frontend_url = settings.FRONTEND_URL.rstrip('/')
        # URL encode the token to handle special characters
        encoded_token = quote(token, safe='')
        assignment_url = f'{frontend_url}/assign-folder/{meeting_transcription.id}?token={encoded_token}'
        
        # Generate folder-specific assignment links
        folder_links = []
        for folder in folders:
            folder_token = generate_assignment_token(str(meeting_transcription.id), user_id)
            # URL encode the token to handle special characters
            encoded_folder_token = quote(folder_token, safe='')
            folder_url = f'{frontend_url}/assign-folder/{meeting_transcription.id}?token={encoded_folder_token}&folder_id={folder["id"]}'
            folder_links.append({
                'name': folder['name'],
                'workspace_name': folder.get('workspace_name', workspace_name),
                'url': folder_url,
            })
        
        # Prepare email context
        context = {
            'meeting_title': meeting_title,
            'meeting_date': meeting_date,
            'meeting_time': meeting_time,
            'assignment_url': assignment_url,
            'folders': folder_links,
            'has_folders': len(folders) > 0,
            'workspace_name': workspace_name,
        }
        
        # Render email template
        html_message = render_to_string('emails/unresolved_meeting.html', context)
        plain_message = strip_tags(html_message)
        
        # Send email
        subject = f'Action Required: Assign Folder to "{meeting_title}"'
        
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user_email],
            html_message=html_message,
            fail_silently=False,
        )
        
        logger.info(f'[EmailService] Successfully sent email to {user_email} for meeting {meeting_transcription.id}')
        
    except Exception as e:
        logger.error(f'[EmailService] Error sending email for meeting {meeting_transcription.id}: {e}')
        raise


def get_previous_meeting_for_user(backend_user_id: str, current_event_start_time) -> MeetingTranscription | None:
    """
    Find the most recent completed meeting for a user before the current event.
    
    Args:
        backend_user_id: Backend user ID
        current_event_start_time: Start time of the current event (datetime)
    
    Returns:
        MeetingTranscription of the previous meeting, or None if not found
    """
    try:
        # Find the most recent completed meeting that ended before the current event starts
        previous_meeting = MeetingTranscription.objects.filter(
            backend_user_id=backend_user_id,
            status='completed',
        ).select_related().order_by('-updated_at').first()
        
        if not previous_meeting:
            logger.info(f'[EmailService] No previous meeting found for user {backend_user_id}')
            return None
        
        # Check if the previous meeting ended before the current event starts
        try:
            previous_event = CalendarEvent.objects.get(id=previous_meeting.calendar_event_id)
            previous_end_time = previous_event.end_time
            if previous_end_time and timezone.is_naive(previous_end_time):
                previous_end_time = timezone.make_aware(previous_end_time)
            
            # If current event start time is provided, verify previous meeting ended before it
            if current_event_start_time:
                if timezone.is_naive(current_event_start_time):
                    current_event_start_time = timezone.make_aware(current_event_start_time)
                if previous_end_time and previous_end_time >= current_event_start_time:
                    logger.info(f'[EmailService] Previous meeting ended after current event starts, skipping')
                    return None
        except CalendarEvent.DoesNotExist:
            # If no calendar event, use updated_at as completion time
            if previous_meeting.updated_at:
                if timezone.is_naive(current_event_start_time):
                    current_event_start_time = timezone.make_aware(current_event_start_time)
                if previous_meeting.updated_at >= current_event_start_time:
                    logger.info(f'[EmailService] Previous meeting updated after current event starts, skipping')
                    return None
        
        logger.info(f'[EmailService] Found previous meeting: {previous_meeting.id} (title: {previous_event.title if previous_event else "Unknown"})')
        return previous_meeting
        
    except Exception as e:
        logger.error(f'[EmailService] Error finding previous meeting: {e}', exc_info=True)
        return None


def get_meeting_participants(meeting_transcription: MeetingTranscription) -> list[dict]:
    """
    Extract participants from meeting transcription.
    Participants can be in transcript_data or BotRecording's recall_data.
    
    Args:
        meeting_transcription: MeetingTranscription instance
    
    Returns:
        List of participant dictionaries with name and email (if available)
    """
    participants = []
    
    try:
        # Try to get participants from transcript_data
        transcript_data = meeting_transcription.transcript_data or {}
        
        # Check for participants in various formats
        if isinstance(transcript_data, dict):
            # AssemblyAI format might have participants
            if 'participants' in transcript_data:
                participants_data = transcript_data['participants']
                if isinstance(participants_data, list):
                    for p in participants_data:
                        if isinstance(p, dict):
                            participants.append({
                                'name': p.get('name') or p.get('id') or 'Unknown',
                                'email': p.get('email', ''),
                            })
            
            # Check for utterances with participant info
            if 'utterances' in transcript_data:
                seen_participants = set()
                for utterance in transcript_data.get('utterances', []):
                    if isinstance(utterance, dict):
                        speaker = utterance.get('speaker') or utterance.get('participant')
                        if speaker:
                            if isinstance(speaker, dict):
                                name = speaker.get('name') or speaker.get('id') or 'Unknown'
                                if name not in seen_participants:
                                    seen_participants.add(name)
                                    participants.append({
                                        'name': name,
                                        'email': speaker.get('email', ''),
                                    })
                            elif isinstance(speaker, str) and speaker not in seen_participants:
                                seen_participants.add(speaker)
                                participants.append({
                                    'name': speaker,
                                    'email': '',
                                })
        
        # Try to get from BotRecording
        if not participants:
            try:
                bot_recording = BotRecording.objects.filter(bot_id=meeting_transcription.bot_id).first()
                if bot_recording and bot_recording.recall_data:
                    recall_data = bot_recording.recall_data
                    if 'participants' in recall_data:
                        participants_data = recall_data['participants']
                        if isinstance(participants_data, list):
                            for p in participants_data:
                                if isinstance(p, dict):
                                    participants.append({
                                        'name': p.get('name') or p.get('id') or 'Unknown',
                                        'email': p.get('email', ''),
                                    })
            except Exception as e:
                logger.debug(f'[EmailService] Could not get participants from BotRecording: {e}')
        
        # Remove duplicates based on name
        seen_names = set()
        unique_participants = []
        for p in participants:
            name = p.get('name', '').strip()
            if name and name not in seen_names:
                seen_names.add(name)
                unique_participants.append(p)
        
        return unique_participants
        
    except Exception as e:
        logger.warning(f'[EmailService] Error extracting participants: {e}')
        return []


def send_previous_meeting_summary_email(backend_user_id: str, current_event_start_time, new_meeting_title: str = None):
    """
    Send email with previous meeting summary when a new meeting is scheduled.
    
    This function:
    1. Finds the most recent completed meeting for the user
    2. Extracts meeting data (title, date, time, participants, summary, action items, contextual nudges)
    3. Sends an email with this information
    
    Args:
        backend_user_id: Backend user ID
        current_event_start_time: Start time of the newly scheduled meeting
        new_meeting_title: Optional title of the new meeting (for context in email)
    """
    try:
        # Get user email
        user_email = get_user_email_from_backend(backend_user_id)
        if not user_email:
            logger.warning(f'[EmailService] Cannot send previous meeting email: no email found for user {backend_user_id}')
            return
        
        # Find previous meeting
        previous_meeting = get_previous_meeting_for_user(backend_user_id, current_event_start_time)
        if not previous_meeting:
            logger.info(f'[EmailService] No previous meeting found, skipping email for user {backend_user_id}')
            return
        
        # Get meeting event details
        try:
            previous_event = CalendarEvent.objects.get(id=previous_meeting.calendar_event_id)
            meeting_title = previous_event.title or 'Untitled Meeting'
            meeting_date = previous_event.start_time.strftime('%B %d, %Y') if previous_event.start_time else 'Unknown date'
            meeting_time = previous_event.start_time.strftime('%I:%M %p') if previous_event.start_time else 'Unknown time'
            meeting_end_time = previous_event.end_time.strftime('%I:%M %p') if previous_event.end_time else None
            if meeting_end_time:
                meeting_time = f'{meeting_time} - {meeting_end_time}'
        except CalendarEvent.DoesNotExist:
            meeting_title = 'Untitled Meeting'
            meeting_date = previous_meeting.created_at.strftime('%B %d, %Y') if previous_meeting.created_at else 'Unknown date'
            meeting_time = previous_meeting.created_at.strftime('%I:%M %p') if previous_meeting.created_at else 'Unknown time'
            previous_event = None
        
        # Get participants
        participants = get_meeting_participants(previous_meeting)
        
        # Get summary
        summary = previous_meeting.summary or previous_meeting.transcript_data.get('summary', '') or 'No summary available'
        
        # Get action items
        action_items = previous_meeting.action_items_list if hasattr(previous_meeting, 'action_items_list') else (previous_meeting.action_items or [])
        if not action_items and isinstance(previous_meeting.transcript_data, dict):
            action_items = previous_meeting.transcript_data.get('action_items', [])
        
        # Get contextual nudges
        contextual_nudges = previous_meeting.contextual_nudges or []
        
        # Prepare email context
        context = {
            'previous_meeting_title': meeting_title,
            'previous_meeting_date': meeting_date,
            'previous_meeting_time': meeting_time,
            'participants': participants,
            'summary': summary,
            'action_items': action_items,
            'contextual_nudges': contextual_nudges,
            'new_meeting_title': new_meeting_title,
            'has_action_items': len(action_items) > 0,
            'has_contextual_nudges': len(contextual_nudges) > 0,
            'has_participants': len(participants) > 0,
        }
        
        # Render email template
        html_message = render_to_string('emails/previous_meeting_summary.html', context)
        plain_message = strip_tags(html_message)
        
        # Send email
        subject = f'Previous Meeting Summary: "{meeting_title}"'
        if new_meeting_title:
            subject = f'Before Your Next Meeting: Summary of "{meeting_title}"'
        
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user_email],
            html_message=html_message,
            fail_silently=False,
        )
        
        logger.info(f'[EmailService] Successfully sent previous meeting summary email to {user_email} for meeting {previous_meeting.id}')
        
    except Exception as e:
        logger.error(f'[EmailService] Error sending previous meeting summary email: {e}', exc_info=True)
        # Don't raise - this is a background notification, shouldn't break bot creation

