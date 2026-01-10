"""
Build meeting context for chat bot
Includes previous meetings and live meeting data
Optimized to reduce API calls and improve accuracy
"""
import re
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple
from django.utils import timezone
from app.models import Calendar, CalendarEvent, MeetingTranscription, BotRecording


# Simple in-memory cache for question intent analysis (to avoid repeated processing)
_intent_cache = {}
_cache_max_size = 100


def extract_person_name(question: str) -> Optional[str]:
    """
    Extract person name from question
    Examples: "meeting with John", "discussed with Sarah", "talked to Mike"
    """
    question_lower = question.lower()
    
    # Patterns for person mentions
    patterns = [
        r'(?:with|to|from)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)',  # "with John" or "with John Smith"
        r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+(?:said|mentioned|discussed)',  # "John said"
        r'meeting\s+([A-Z][a-z]+)',  # "meeting John"
    ]
    
    for pattern in patterns:
        match = re.search(pattern, question)
        if match:
            name = match.group(1).strip()
            # Filter out common words that might be capitalized
            if name.lower() not in ['the', 'this', 'that', 'meeting', 'today', 'yesterday', 'tomorrow']:
                return name
    
    return None


def extract_date_reference(question: str) -> Optional[Dict[str, Any]]:
    """
    Extract date/timestamp from question
    Returns: {'type': 'today'|'yesterday'|'date'|'timestamp', 'value': date or timestamp}
    """
    question_lower = question.lower()
    now = timezone.now()
    
    # Relative dates
    if 'today' in question_lower:
        return {'type': 'today', 'value': now.date()}
    if 'yesterday' in question_lower:
        return {'type': 'yesterday', 'value': (now - timedelta(days=1)).date()}
    if 'last week' in question_lower:
        return {'type': 'last_week', 'value': now - timedelta(days=7)}
    if 'last month' in question_lower:
        return {'type': 'last_month', 'value': now - timedelta(days=30)}
    
    # Date patterns: "on 2024-12-27", "December 27", "12/27/2024"
    date_patterns = [
        r'(\d{4}-\d{2}-\d{2})',  # YYYY-MM-DD
        r'(\d{2}/\d{2}/\d{4})',  # MM/DD/YYYY
        r'(\d{1,2}/\d{1,2}/\d{4})',  # M/D/YYYY
        r'(january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{1,2})(?:,?\s+(\d{4}))?',  # Month Day, Year
    ]
    
    for pattern in date_patterns:
        match = re.search(pattern, question_lower)
        if match:
            try:
                if pattern.startswith('(january'):
                    month_name = match.group(1)
                    day = int(match.group(2))
                    year = int(match.group(3)) if match.group(3) else now.year
                    month_map = {
                        'january': 1, 'february': 2, 'march': 3, 'april': 4,
                        'may': 5, 'june': 6, 'july': 7, 'august': 8,
                        'september': 9, 'october': 10, 'november': 11, 'december': 12
                    }
                    date_value = datetime(year, month_map[month_name], day).date()
                else:
                    date_str = match.group(1)
                    if '-' in date_str:
                        date_value = datetime.strptime(date_str, '%Y-%m-%d').date()
                    elif '/' in date_str:
                        parts = date_str.split('/')
                        if len(parts) == 3:
                            month, day, year = map(int, parts)
                            date_value = datetime(year, month, day).date()
                
                return {'type': 'date', 'value': date_value}
            except (ValueError, AttributeError):
                continue
    
    # Timestamp patterns: "at 2pm", "at 14:30", "at 2:30 PM"
    time_patterns = [
        r'at\s+(\d{1,2}):(\d{2})\s*(?:am|pm)?',
        r'at\s+(\d{1,2})\s*(?:am|pm)',
    ]
    
    for pattern in time_patterns:
        match = re.search(pattern, question_lower)
        if match:
            # Could extract time, but for now just mark as time-based query
            return {'type': 'timestamp', 'value': None}
    
    return None


def analyze_question_intent(question: str) -> Dict[str, Any]:
    """
    Determine if question needs meeting context and extract filters
    
    Returns:
        {
            'needs_meeting_context': bool,
            'question_type': 'meeting' | 'ellie' | 'general' | 'live_meeting',
            'person_filter': str | None,  # Person name if mentioned
            'date_filter': dict | None,  # Date reference if mentioned
            'live_meeting_only': bool  # True if asking specifically about live meeting
        }
    """
    # Simple cache check
    cache_key = question.lower().strip()
    if cache_key in _intent_cache:
        return _intent_cache[cache_key]
    
    question_lower = question.lower()
    
    # Meeting-related keywords
    meeting_keywords = [
        'meeting', 'transcript', 'summary', 'action item', 'discussion',
        'decided', 'agreed', 'participant', 'zoom', 'teams', 'meet',
        'calendar', 'scheduled', 'yesterday', 'today', 'last week',
        'what did we', 'what was discussed', 'who said', 'what happened',
        'decisions', 'outcomes', 'takeaways'
    ]
    
    # Live meeting keywords
    live_meeting_keywords = [
        'current meeting', 'live meeting', 'ongoing meeting', 'right now',
        'happening now', 'current discussion', 'ongoing discussion'
    ]
    
    # Ellie-related keywords
    ellie_keywords = [
        'ellie', 'invite ellie', 'how does', 'how to', 'workflow',
        'feature', 'integration', 'export', 'workspace', 'transcription'
    ]
    
    has_meeting_keyword = any(kw in question_lower for kw in meeting_keywords)
    has_live_keyword = any(kw in question_lower for kw in live_meeting_keywords)
    has_ellie_keyword = any(kw in question_lower for kw in ellie_keywords)
    
    needs_context = has_meeting_keyword or has_ellie_keyword or has_live_keyword
    
    # Determine question type
    if has_live_keyword:
        question_type = 'live_meeting'
    elif has_meeting_keyword:
        question_type = 'meeting'
    elif has_ellie_keyword:
        question_type = 'ellie'
    else:
        question_type = 'general'
    
    # Extract person name
    person_filter = extract_person_name(question)
    
    # Extract date reference
    date_filter = extract_date_reference(question)
    
    result = {
        'needs_meeting_context': needs_context,
        'question_type': question_type,
        'person_filter': person_filter,
        'date_filter': date_filter,
        'live_meeting_only': has_live_keyword
    }
    
    # Cache result (with size limit)
    if len(_intent_cache) >= _cache_max_size:
        # Clear oldest entries (simple approach: clear all)
        _intent_cache.clear()
    _intent_cache[cache_key] = result
    
    return result


def extract_participants_from_transcription(transcription: MeetingTranscription) -> set:
    """Extract participant names from a transcription"""
    participants = set()
    
    # Priority 1: Stored participants from webhook events
    stored_participants = transcription.transcript_data.get('participants', [])
    if stored_participants and isinstance(stored_participants, list):
        for participant in stored_participants:
            if isinstance(participant, dict):
                name = participant.get('name')
                if name and isinstance(name, str):
                    participants.add(name.strip())
    
    # Priority 2: From utterances
    if not participants:
        utterances = transcription.utterances
        if utterances and isinstance(utterances, list):
            for utterance in utterances:
                speaker = utterance.get('speaker')
                if speaker and isinstance(speaker, str):
                    participants.add(speaker.strip())
    
    return participants


def find_relevant_transcript_segments(
    question: str,
    transcription: MeetingTranscription,
    max_segments: int = 5
) -> List[Dict[str, Any]]:
    """
    Find relevant transcript segments that relate to the question
    Returns segments with timestamps and speaker info
    
    Args:
        question: User's question
        transcription: MeetingTranscription object
        max_segments: Maximum number of segments to return
        
    Returns:
        List of dicts with keys: 'text', 'speaker', 'start_time', 'end_time', 'relevance_score'
    """
    if not transcription or not transcription.utterances:
        return []
    
    question_lower = question.lower()
    question_words = set(re.findall(r'\b\w+\b', question_lower))
    
    # Remove common stop words
    stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'what', 'when', 'where', 'who', 'why', 'how', 'is', 'are', 'was', 'were', 'did', 'do', 'does', 'can', 'could', 'should', 'would', 'will', 'this', 'that', 'these', 'those'}
    question_words = {w for w in question_words if w not in stop_words and len(w) > 2}
    
    if not question_words:
        return []
    
    segments = []
    utterances = transcription.utterances
    
    # If no structured utterances, try to extract from transcript_text (for live meetings)
    if not utterances and transcription.transcript_text:
        # Split transcript_text into sentences and create segments
        sentences = re.split(r'[.!?]+', transcription.transcript_text)
        for i, sentence in enumerate(sentences[:max_segments * 2]):  # Check more sentences to find relevant ones
            sentence = sentence.strip()
            if not sentence or len(sentence) < 10:
                continue
            
            sentence_lower = sentence.lower()
            sentence_words = set(re.findall(r'\b\w+\b', sentence_lower))
            
            # Calculate relevance
            matching_words = question_words.intersection(sentence_words)
            relevance_score = len(matching_words) / max(len(question_words), 1)
            
            if relevance_score > 0:
                segments.append({
                    'text': sentence,
                    'speaker': 'Unknown',
                    'start_time': i * 10,  # Approximate timestamp
                    'end_time': (i + 1) * 10,
                    'relevance_score': relevance_score
                })
    else:
        # Use structured utterances
        for utterance in utterances:
            if not isinstance(utterance, dict):
                continue
            
            text = utterance.get('text', '') or utterance.get('words', '')
            if isinstance(text, list):
                # If words is a list, extract text from word objects
                text = ' '.join([w.get('text', '') if isinstance(w, dict) else str(w) for w in text])
            
            if not text or not isinstance(text, str):
                continue
            
            text_lower = text.lower()
            text_words = set(re.findall(r'\b\w+\b', text_lower))
            
            # Calculate relevance: count matching words
            matching_words = question_words.intersection(text_words)
            relevance_score = len(matching_words) / max(len(question_words), 1)
            
            # Only include segments with some relevance
            if relevance_score > 0:
                segment = {
                    'text': text.strip(),
                    'speaker': utterance.get('speaker') or utterance.get('speaker_name') or 'Unknown',
                    'start_time': utterance.get('start') or utterance.get('start_time') or 0,
                    'end_time': utterance.get('end') or utterance.get('end_time') or 0,
                    'relevance_score': relevance_score
                }
                segments.append(segment)
    
    # Sort by relevance score (highest first) and return top segments
    segments.sort(key=lambda x: x['relevance_score'], reverse=True)
    return segments[:max_segments]


def calculate_context_confidence(
    question: str,
    meeting_context_data: Dict[str, Any],
    relevant_segments: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Calculate confidence score for answering the question based on available context
    
    Returns:
        {
            'confidence_score': float (0.0-1.0),
            'has_sufficient_context': bool,
            'relevant_segments_count': int,
            'context_type': 'live' | 'previous' | 'none',
            'reasoning': str
        }
    """
    question_lower = question.lower()
    
    # Check if question is about live meeting
    live_keywords = ['current', 'live', 'ongoing', 'right now', 'happening now', 'current meeting', 'live meeting']
    is_live_question = any(kw in question_lower for kw in live_keywords)
    
    has_live_meetings = meeting_context_data.get('has_live_meetings', False)
    context_text = meeting_context_data.get('context_text', '')
    
    # Base confidence factors
    confidence_score = 0.0
    reasoning_parts = []
    
    # Factor 1: Context availability (0.3 weight)
    if context_text and len(context_text.strip()) > 50:
        context_confidence = 0.3
        reasoning_parts.append("Context available")
    else:
        context_confidence = 0.0
        reasoning_parts.append("No context available")
    
    # Factor 2: Relevant segments found (0.4 weight)
    if relevant_segments:
        # Higher confidence if more relevant segments found
        segment_confidence = min(0.4, len(relevant_segments) * 0.1)
        avg_relevance = sum(s.get('relevance_score', 0) for s in relevant_segments) / len(relevant_segments)
        segment_confidence *= avg_relevance  # Weight by average relevance
        reasoning_parts.append(f"Found {len(relevant_segments)} relevant transcript segments")
    else:
        segment_confidence = 0.0
        reasoning_parts.append("No relevant transcript segments found")
    
    # Factor 3: Question-context alignment (0.3 weight)
    if is_live_question and has_live_meetings:
        alignment_confidence = 0.3
        reasoning_parts.append("Question matches live meeting context")
    elif not is_live_question and context_text:
        # Check if context contains relevant keywords from question
        question_keywords = set(re.findall(r'\b\w+\b', question_lower))
        context_lower = context_text.lower()
        matching_keywords = [kw for kw in question_keywords if kw in context_lower and len(kw) > 3]
        if matching_keywords:
            alignment_confidence = min(0.3, len(matching_keywords) * 0.05)
            reasoning_parts.append(f"Context contains relevant keywords: {len(matching_keywords)}")
        else:
            alignment_confidence = 0.1
            reasoning_parts.append("Limited keyword alignment between question and context")
    else:
        alignment_confidence = 0.0
        reasoning_parts.append("Question-context mismatch")
    
    confidence_score = context_confidence + segment_confidence + alignment_confidence
    
    # Determine if context is sufficient (threshold: 0.5)
    has_sufficient_context = confidence_score >= 0.5
    
    # Determine context type
    if has_live_meetings and (is_live_question or not context_text):
        context_type = 'live'
    elif context_text and not has_live_meetings:
        context_type = 'previous'
    else:
        context_type = 'none'
    
    return {
        'confidence_score': min(1.0, max(0.0, confidence_score)),
        'has_sufficient_context': has_sufficient_context,
        'relevant_segments_count': len(relevant_segments),
        'context_type': context_type,
        'reasoning': '; '.join(reasoning_parts)
    }


def build_meeting_context(
    backend_user_id: str,
    question_intent: Dict[str, Any],
    question: Optional[str] = None
) -> Dict[str, Any]:
    """
    Build meeting context for chat bot with smart filtering
    
    Args:
        backend_user_id: User ID
        question_intent: Intent analysis result
        question: Original question (optional, for finding relevant segments)
    
    Returns:
        {
            'context_text': str,  # Formatted context for prompt
            'has_live_meetings': bool,
            'live_meeting_count': int,
            'live_transcription': MeetingTranscription | None,  # Most recent live transcription
            'relevant_segments': List[Dict],  # Relevant transcript segments with timestamps
        }
    """
    context_parts = []
    has_live_meetings = False
    live_meeting_count = 0
    live_transcription = None
    relevant_segments = []
    
    if not question_intent['needs_meeting_context']:
        return {
            'context_text': '',
            'has_live_meetings': False,
            'live_meeting_count': 0,
            'live_transcription': None,
            'relevant_segments': []
        }
    
    now = timezone.now()
    person_filter = question_intent.get('person_filter')
    date_filter = question_intent.get('date_filter')
    live_meeting_only = question_intent.get('live_meeting_only', False)
    
    # 1. LIVE MEETINGS (always check first, especially if live_meeting_only)
    if not live_meeting_only or True:  # Always include live meetings for context
        live_transcriptions = MeetingTranscription.objects.filter(
            backend_user_id=backend_user_id,
            status='processing'
        ).order_by('-updated_at')
        
        # Filter by staleness (must be updated within last 5 minutes)
        five_minutes_ago = now - timedelta(minutes=5)
        live_transcriptions = [t for t in live_transcriptions if t.updated_at and t.updated_at >= five_minutes_ago]
        
        if live_transcriptions:
            has_live_meetings = True
            live_meeting_count = len(live_transcriptions)
            live_transcription = live_transcriptions[0]  # Store most recent for segment extraction
            
            # Find relevant segments if question is provided
            if question and live_transcription:
                relevant_segments = find_relevant_transcript_segments(question, live_transcription)
            
            context_parts.append("CURRENTLY LIVE MEETINGS (Real-time):")
            for transcription in live_transcriptions[:3]:  # Limit to 3 live meetings
                event = CalendarEvent.objects.filter(id=transcription.calendar_event_id).first()
                if not event:
                    continue
                
                meeting_title = event.title or 'Untitled Meeting'
                start_time_str = event.start_time.strftime('%Y-%m-%d %H:%M') if event.start_time else 'Unknown'
                
                if transcription.transcript_text:
                    # Get last 3000 characters (more context for live meetings)
                    latest_transcript = transcription.transcript_text[-3000:]
                    updated_at = transcription.updated_at.strftime('%H:%M:%S') if transcription.updated_at else 'Unknown'
                    
                    # Get participants
                    participants = extract_participants_from_transcription(transcription)
                    participants_str = ', '.join(sorted(participants)) if participants else 'Unknown'
                    
                    live_info = f"""
LIVE Meeting ID: {transcription.id}
Title: {meeting_title}
Started: {start_time_str}
Participants: {participants_str}
Latest Real-time Transcript (last updated at {updated_at}):
{latest_transcript}
Status: Meeting in progress - transcript updating in real-time
"""
                else:
                    live_info = f"""
LIVE Meeting ID: {transcription.id}
Title: {meeting_title}
Started: {start_time_str}
Status: Meeting in progress - waiting for transcript
"""
                context_parts.append(live_info)
    
    # 2. PREVIOUS MEETINGS (completed meetings with summaries)
    if not live_meeting_only:  # Only if not asking specifically about live meeting
        completed_transcriptions_query = MeetingTranscription.objects.filter(
            backend_user_id=backend_user_id,
            status='completed'
        ).order_by('-created_at')
        
        # Apply date filter if provided
        if date_filter:
            date_value = date_filter.get('value')
            if date_value and isinstance(date_value, (datetime, type(now.date()))):
                if isinstance(date_value, datetime):
                    date_value = date_value.date()
                # Filter meetings on or around this date
                start_of_day = timezone.make_aware(datetime.combine(date_value, datetime.min.time()))
                end_of_day = start_of_day + timedelta(days=1)
                completed_transcriptions_query = completed_transcriptions_query.filter(
                    created_at__gte=start_of_day,
                    created_at__lt=end_of_day
                )
            elif date_filter.get('type') == 'yesterday':
                yesterday_start = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
                yesterday_end = yesterday_start + timedelta(days=1)
                completed_transcriptions_query = completed_transcriptions_query.filter(
                    created_at__gte=yesterday_start,
                    created_at__lt=yesterday_end
                )
            elif date_filter.get('type') == 'today':
                today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
                completed_transcriptions_query = completed_transcriptions_query.filter(
                    created_at__gte=today_start
                )
        
        completed_transcriptions = list(completed_transcriptions_query[:15])  # Increased limit for filtering
        
        # Get event data
        event_ids = [trans.calendar_event_id for trans in completed_transcriptions]
        events_dict = {}
        if event_ids:
            events = CalendarEvent.objects.filter(id__in=event_ids)
            events_dict = {str(event.id): event for event in events}
        
        # Filter by person if specified
        filtered_transcriptions = []
        if person_filter:
            person_name_lower = person_filter.lower()
            for trans in completed_transcriptions:
                participants = extract_participants_from_transcription(trans)
                # Check if person name matches any participant
                if any(person_name_lower in p.lower() for p in participants):
                    filtered_transcriptions.append(trans)
        else:
            filtered_transcriptions = completed_transcriptions
        
        # Limit to most recent 10 (after filtering)
        filtered_transcriptions = filtered_transcriptions[:10]
        
        if filtered_transcriptions:
            context_parts.append("\nPREVIOUS MEETINGS:")
            for trans in filtered_transcriptions:
                event = events_dict.get(str(trans.calendar_event_id))
                if not event:
                    continue
                
                meeting_title = event.title or 'Untitled Meeting'
                meeting_date = event.start_time.strftime('%Y-%m-%d %H:%M') if event.start_time else 'Unknown'
                
                # Get participants
                participants = extract_participants_from_transcription(trans)
                participants_str = ', '.join(sorted(participants)) if participants else 'Unknown'
                
                # Get action items (limit to 3 most important)
                action_items = []
                if trans.action_items:
                    if isinstance(trans.action_items, list):
                        for item in trans.action_items[:3]:  # Limit to 3
                            if isinstance(item, dict):
                                action_items.append(item.get('text', str(item)))
                            else:
                                action_items.append(str(item))
                
                action_items_str = '; '.join(action_items) if action_items else 'None'
                summary = (trans.summary or 'No summary available')[:500]  # Limit summary length
                
                meeting_info = f"""
Meeting ID: {trans.id}
Title: {meeting_title}
Date: {meeting_date}
Participants: {participants_str}
Summary: {summary}
Action Items: {action_items_str}
"""
                context_parts.append(meeting_info)
    
    context_text = "\n".join(context_parts) if context_parts else ""
    
    return {
        'context_text': context_text,
        'has_live_meetings': has_live_meetings,
        'live_meeting_count': live_meeting_count,
        'live_transcription': live_transcription,
        'relevant_segments': relevant_segments
    }
