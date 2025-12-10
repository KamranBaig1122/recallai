"""
Build meeting context for chat bot
Includes previous meetings and live meeting data
"""
from django.utils import timezone
from app.models import Calendar, CalendarEvent, MeetingTranscription


def analyze_question_intent(question: str) -> dict:
    """
    Determine if question needs meeting context
    
    Returns:
        {
            'needs_meeting_context': bool,
            'question_type': 'meeting' | 'ellie' | 'general'
        }
    """
    question_lower = question.lower()
    
    # Meeting-related keywords
    meeting_keywords = [
        'meeting', 'transcript', 'summary', 'action item', 'discussion',
        'decided', 'agreed', 'participant', 'zoom', 'teams', 'meet',
        'calendar', 'scheduled', 'yesterday', 'today', 'last week',
        'what did we', 'what was discussed', 'who said', 'what happened',
        'decisions', 'outcomes', 'takeaways'
    ]
    
    # Ellie-related keywords
    ellie_keywords = [
        'ellie', 'invite ellie', 'how does', 'how to', 'workflow',
        'feature', 'integration', 'export', 'workspace', 'transcription'
    ]
    
    has_meeting_keyword = any(kw in question_lower for kw in meeting_keywords)
    has_ellie_keyword = any(kw in question_lower for kw in ellie_keywords)
    
    needs_context = has_meeting_keyword or has_ellie_keyword
    
    question_type = 'meeting' if has_meeting_keyword else 'ellie' if has_ellie_keyword else 'general'
    
    return {
        'needs_meeting_context': needs_context,
        'question_type': question_type
    }


def build_meeting_context(backend_user_id: str, question_intent: dict) -> dict:
    """
    Build meeting context for chat bot
    
    Returns:
        {
            'context_text': str,  # Formatted context for prompt
            'has_live_meetings': bool,  # Whether there are live meetings
            'live_meeting_count': int  # Number of live meetings
        }
    """
    context_parts = []
    has_live_meetings = False
    live_meeting_count = 0
    
    if not question_intent['needs_meeting_context']:
        return {
            'context_text': '',
            'has_live_meetings': False,
            'live_meeting_count': 0
        }
    
    now = timezone.now()
    
    # 1. PREVIOUS MEETINGS (completed meetings with summaries)
    completed_transcriptions = list(MeetingTranscription.objects.filter(
        backend_user_id=backend_user_id,
        status='completed'
    ).order_by('-created_at')[:10])
    
    if completed_transcriptions:
        context_parts.append("PREVIOUS MEETINGS:")
        # Get all event IDs
        event_ids = [trans.calendar_event_id for trans in completed_transcriptions]
        # Fetch events in bulk
        events_dict = {}
        if event_ids:
            events = CalendarEvent.objects.filter(id__in=event_ids)
            events_dict = {str(event.id): event for event in events}
        
        for trans in completed_transcriptions:
            event = events_dict.get(str(trans.calendar_event_id))
            if not event:
                # Skip if event not found
                continue
                
            meeting_title = event.title or 'Untitled Meeting'
            meeting_date = event.start_time.strftime('%Y-%m-%d') if event.start_time else 'Unknown'
            
            # Get action items
            action_items = []
            if trans.action_items:
                if isinstance(trans.action_items, list):
                    for item in trans.action_items:
                        if isinstance(item, dict):
                            action_items.append(item.get('text', str(item)))
                        else:
                            action_items.append(str(item))
            
            action_items_str = ', '.join(action_items) if action_items else 'None'
            
            meeting_info = f"""
Meeting ID: {trans.id}
Title: {meeting_title}
Date: {meeting_date}
Summary: {trans.summary or 'No summary available'}
Action Items: {action_items_str}
Platform: {event.platform or 'Unknown'}
"""
            context_parts.append(meeting_info)
    
    # 2. LIVE MEETINGS (real-time transcripts)
    # Get events directly by backend_user_id (preferred method)
    all_user_events = CalendarEvent.objects.filter(
        backend_user_id=backend_user_id
    )
    
    # Also get events from user's calendars (for backward compatibility)
    user_calendars = list(Calendar.objects.filter(
        backend_user_id=backend_user_id
    ))
    calendar_ids = [cal.id for cal in user_calendars]  # Keep as UUID, not string
    
    events_by_calendar = CalendarEvent.objects.none()  # Empty queryset
    if calendar_ids:
        events_by_calendar = CalendarEvent.objects.filter(
            calendar_id__in=calendar_ids
        )
    
    # Combine both queries (remove duplicates)
    all_event_ids = set()
    all_events = []
    for event in all_user_events:
        if str(event.id) not in all_event_ids:
            all_event_ids.add(str(event.id))
            all_events.append(event)
    for event in events_by_calendar:
        if str(event.id) not in all_event_ids:
            all_event_ids.add(str(event.id))
            all_events.append(event)
    
    # Filter live events in Python (start_time and end_time are properties, not DB fields)
    live_events = []
    for event in all_events:
        try:
            start_time = event.start_time
            end_time = event.end_time
            meeting_url = event.meeting_url
            
            if start_time and end_time and meeting_url:
                # Check if meeting is currently live
                if start_time <= now <= end_time:
                    live_events.append(event)
        except Exception as e:
            # Skip events with invalid time data
            print(f'[ChatContext] Error processing event {event.id}: {e}')
            continue
    
    if live_events:
        has_live_meetings = True
        live_meeting_count = len(live_events)
        
        context_parts.append("\nCURRENTLY LIVE MEETINGS (Real-time):")
        for event in live_events:
            # Get latest transcription (updated in real-time via webhooks)
            transcription = MeetingTranscription.objects.filter(
                calendar_event_id=event.id,
                status='processing'  # Still in progress
            ).order_by('-updated_at').first()
            
            meeting_title = event.title or 'Untitled Meeting'
            start_time_str = event.start_time.strftime('%Y-%m-%d %H:%M') if event.start_time else 'Unknown'
            
            if transcription and transcription.transcript_text:
                # Get last 2000 characters (most recent transcript chunks)
                latest_transcript = transcription.transcript_text[-2000:]
                updated_at = transcription.updated_at.strftime('%H:%M:%S') if transcription.updated_at else 'Unknown'
                
                live_info = f"""
LIVE Meeting ID: {event.id}
Title: {meeting_title}
Started: {start_time_str}
Latest Real-time Transcript (last updated at {updated_at}):
{latest_transcript}
Status: Meeting in progress - transcript updating in real-time
Platform: {event.platform or 'Unknown'}
"""
            else:
                # Meeting is live but no transcript yet
                live_info = f"""
LIVE Meeting ID: {event.id}
Title: {meeting_title}
Started: {start_time_str}
Status: Meeting in progress - waiting for transcript
Platform: {event.platform or 'Unknown'}
"""
            context_parts.append(live_info)
    
    context_text = "\n".join(context_parts) if context_parts else ""
    
    return {
        'context_text': context_text,
        'has_live_meetings': has_live_meetings,
        'live_meeting_count': live_meeting_count
    }

