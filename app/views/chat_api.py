"""
Chat API endpoint for Ellie bot
Uses Groq API with meeting context
Optimized to reduce API calls with caching
"""
import os
import re
import json
import hashlib
from datetime import timedelta
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from app.views.calendar_api import add_cors_headers, get_backend_user_id_from_request
from app.logic.chat_context import (
    analyze_question_intent,
    build_meeting_context,
    calculate_context_confidence,
    find_relevant_transcript_segments
)

# Simple in-memory response cache (to reduce Groq API calls)
_response_cache = {}
_cache_expiry = timedelta(minutes=5)  # Cache responses for 5 minutes
_cache_max_size = 50  # Maximum cached responses

try:
    from groq import Groq
except ImportError:
    print('[ChatAPI] ⚠ WARNING: groq package not installed. Install with: pip install groq')
    Groq = None


# Base system prompt for Ellie
BASE_SYSTEM_PROMPT = """You are "Ellie", an AI-powered meeting assistant of "INVITE ELLIE" designed to help users manage, transcribe, summarize, and organize their meetings in a smart and human-friendly way. Your tone is warm, conversational, and approachable, making users feel understood and supported. Use natural, everyday language with clear and simple explanations, showing empathy and enthusiasm in your responses.

CRITICAL RESPONSE LENGTH RULES (MUST FOLLOW STRICTLY):
- Keep ALL responses to 2-3 sentences maximum (approximately 20-40 words)
- ABSOLUTE MAXIMUM: 4 lines or 50 words - if you exceed this, you're writing too much
- Be extremely concise - get straight to the point immediately
- One clear answer is better than multiple explanations
- If information is longer, use bullet points (•) but still keep total response short
- Never write long paragraphs or multiple sentences explaining the same thing
- Think: "What's the shortest way to answer this?" and then make it even shorter

CRITICAL FORMATTING RULES:
- NEVER use markdown formatting like asterisks (*), hashes (#), underscores (_), or any special markdown characters
- NEVER use bold, italic, or code formatting
- Use plain text only with bullet points using the bullet character (•)
- Each bullet point should be on its own separate line
- Write like a human colleague would - natural, professional, and friendly
- Use line breaks between ideas for clarity

IMPORTANT: You are a GENERAL-PURPOSE assistant. You can answer:
- Questions about Invite Ellie features and workflow
- Questions about the user's meetings (if meeting context is provided)
- General knowledge questions
- Calculations, explanations, etc.

When meeting context is provided below, use it to answer questions about meetings. 
When no meeting context is provided, answer from your general knowledge.
Always be helpful and concise."""


def clean_response(text):
    """Remove markdown formatting and special characters from response"""
    if not text:
        return text
    
    # Remove markdown bold/italic
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)  # Remove **bold**
    text = re.sub(r'\*(.*?)\*', r'\1', text)  # Remove *italic*
    text = re.sub(r'_(.*?)_', r'\1', text)  # Remove _italic_
    text = re.sub(r'__(.*?)__', r'\1', text)  # Remove __bold__
    
    # Remove markdown headers
    text = re.sub(r'^#+\s*', '', text, flags=re.MULTILINE)
    
    # Remove markdown code blocks
    text = re.sub(r'```[\s\S]*?```', '', text)
    text = re.sub(r'`([^`]+)`', r'\1', text)
    
    # Remove markdown links but keep text
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    
    # Convert dashes and markdown lists to bullet points (•)
    lines = text.split('\n')
    cleaned_lines = []
    prev_was_bullet = False
    
    for line in lines:
        trimmed_line = line.strip()
        if not trimmed_line:
            if prev_was_bullet:
                cleaned_lines.append('')
            continue
            
        # Convert markdown list items with dashes or asterisks to bullet points
        if re.match(r'^\s*[-*]\s+', trimmed_line):
            cleaned_line = re.sub(r'^\s*[-*]\s+', '• ', trimmed_line)
            cleaned_lines.append(cleaned_line)
            prev_was_bullet = True
        elif re.match(r'^\s*\d+\.\s+', trimmed_line):
            cleaned_line = re.sub(r'^\s*\d+\.\s+', '• ', trimmed_line)
            cleaned_lines.append(cleaned_line)
            prev_was_bullet = True
        elif trimmed_line.startswith('•'):
            cleaned_lines.append(trimmed_line)
            prev_was_bullet = True
        else:
            if cleaned_lines and not prev_was_bullet and cleaned_lines[-1] and not cleaned_lines[-1].startswith('•'):
                cleaned_lines[-1] = cleaned_lines[-1].rstrip() + ' ' + trimmed_line
            else:
                cleaned_lines.append(trimmed_line)
            prev_was_bullet = False
    
    text = '\n'.join(cleaned_lines)
    
    # Remove extra whitespace
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = text.strip()
    
    # Fix incorrect single or double bullet points - convert to regular sentences
    lines = text.split('\n')
    bullet_count = sum(1 for line in lines if line.strip().startswith('•'))
    
    if 1 <= bullet_count <= 2:
        fixed_lines = []
        for line in lines:
            if line.strip().startswith('•'):
                cleaned = line.strip().replace('•', '').strip()
                if cleaned and not cleaned[0].isupper():
                    cleaned = cleaned[0].upper() + cleaned[1:] if len(cleaned) > 1 else cleaned.upper()
                fixed_lines.append(cleaned)
            else:
                fixed_lines.append(line)
        text = '\n'.join(fixed_lines)
        text = re.sub(r'([^\n])\n([^\n•])', r'\1 \2', text)
    
    # Ensure response ends with proper punctuation
    if text and not text.endswith(('.', '!', '?', ':', '•')):
        last_line = text.split('\n')[-1].strip()
        if last_line and not last_line.startswith('•'):
            text = text.rstrip('.!?') + '.'
    
    return text


def build_system_prompt(
    meeting_context: str,
    question_intent: dict,
    confidence_score: float = 1.0,
    relevant_segments: list = None
) -> str:
    """Build system prompt with optional meeting context and confidence-aware instructions"""
    prompt = BASE_SYSTEM_PROMPT
    
    # Add confidence-aware instructions
    if meeting_context and question_intent.get('needs_meeting_context'):
        if confidence_score < 0.5:
            prompt += """

CRITICAL: You have LOW CONFIDENCE context for this question. You MUST:
- Only answer if you are CERTAIN the information is in the provided context
- If uncertain, respond with: "I don't have enough information from the current meeting to answer that. Could you provide more details?"
- NEVER guess or make up information
- NEVER provide irrelevant information from other meetings"""
        elif confidence_score < 0.7:
            prompt += """

IMPORTANT: You have MODERATE confidence context. You should:
- Start your answer with "Based on what's discussed so far..." if referring to live meeting
- Only answer if the information is reasonably clear in the context
- If uncertain, ask for clarification rather than guessing"""
        else:
            prompt += """

You have HIGH confidence context. You can answer confidently, but still:
- Ground your answer in specific transcript segments when possible
- Reference what was actually said, not assumptions"""
        
        # Add grounding requirement
        if relevant_segments:
            prompt += """

GROUNDING REQUIREMENT: You MUST ground your answer in specific transcript segments.
Reference what was actually said, by whom, and when possible."""
    
    if meeting_context:
        # Add specific instructions based on question type
        if question_intent.get('live_meeting_only'):
            prompt += f"""

\n\n=== LIVE MEETING CONTEXT (Currently happening) ===
{meeting_context}
=== END LIVE MEETING CONTEXT ===

The user is asking about the CURRENTLY LIVE meeting. Use the live meeting transcript above to answer.
Focus on what's happening right now in the live meeting.
CRITICAL: Only answer if the information is clearly present in the transcript above."""
        elif question_intent.get('person_filter'):
            person_name = question_intent['person_filter']
            prompt += f"""

\n\n=== MEETING CONTEXT (Filtered by participant: {person_name}) ===
{meeting_context}
=== END MEETING CONTEXT ===

The user is asking about meetings with {person_name}. Use the filtered meetings above.
Reference meetings by title, date, and participants."""
        elif question_intent.get('date_filter'):
            date_info = question_intent['date_filter']
            prompt += f"""

\n\n=== MEETING CONTEXT (Filtered by date: {date_info.get('type', 'date')}) ===
{meeting_context}
=== END MEETING CONTEXT ===

The user is asking about meetings on a specific date/time. Use the filtered meetings above.
Reference meetings by title, date, and what was discussed."""
        else:
            prompt += f"""

\n\n=== MEETING CONTEXT (All relevant meetings) ===
{meeting_context}
=== END MEETING CONTEXT ===

When asked about meetings, use the context above. Reference meetings by title, date, or participants.
For general questions, ignore the meeting context and answer from your knowledge."""
    
    return prompt


@require_http_methods(["POST", "OPTIONS"])
@csrf_exempt
def api_chat(request):
    """
    Chat API endpoint for Ellie bot
    General-purpose bot with meeting context when relevant
    """
    if request.method == 'OPTIONS':
        response = JsonResponse({})
        return add_cors_headers(response, request)
    
    try:
        # Parse request
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            data = {}
        
        user_message = data.get('message', '')
        conversation_history = data.get('history', [])
        userId = data.get('userId')  # From frontend
        
        if not user_message:
            response = JsonResponse({'error': 'Message is required'}, status=400)
            return add_cors_headers(response, request)
        
        # Authenticate user
        backend_user_id = get_backend_user_id_from_request(request)
        if not backend_user_id and userId:
            # Fallback to userId param
            backend_user_id = userId
        
        print(f'[ChatAPI] ==========================================')
        print(f'[ChatAPI] Chat request received')
        print(f'[ChatAPI] User ID: {backend_user_id}')
        print(f'[ChatAPI] Message: {user_message[:100]}...')
        
        # Analyze question intent
        question_intent = analyze_question_intent(user_message)
        print(f'[ChatAPI] Question type: {question_intent["question_type"]}')
        print(f'[ChatAPI] Needs meeting context: {question_intent["needs_meeting_context"]}')
        if question_intent.get('person_filter'):
            print(f'[ChatAPI] Person filter: {question_intent["person_filter"]}')
        if question_intent.get('date_filter'):
            print(f'[ChatAPI] Date filter: {question_intent["date_filter"]}')
        
        # Build meeting context (only if needed)
        meeting_context_data = {
            'context_text': '',
            'has_live_meetings': False,
            'live_meeting_count': 0,
            'live_transcription': None,
            'relevant_segments': []
        }
        
        if question_intent['needs_meeting_context'] and backend_user_id:
            meeting_context_data = build_meeting_context(backend_user_id, question_intent, user_message)
            print(f'[ChatAPI] Meeting context built (length: {len(meeting_context_data["context_text"])} chars)')
            print(f'[ChatAPI] Has live meetings: {meeting_context_data["has_live_meetings"]}')
            print(f'[ChatAPI] Live meeting count: {meeting_context_data["live_meeting_count"]}')
            print(f'[ChatAPI] Relevant segments found: {len(meeting_context_data["relevant_segments"])}')
        
        # Calculate context confidence
        confidence_data = calculate_context_confidence(
            user_message,
            meeting_context_data,
            meeting_context_data.get('relevant_segments', [])
        )
        confidence_score = confidence_data['confidence_score']
        has_sufficient_context = confidence_data['has_sufficient_context']
        
        print(f'[ChatAPI] Context confidence: {confidence_score:.2f} (sufficient: {has_sufficient_context})')
        print(f'[ChatAPI] Confidence reasoning: {confidence_data["reasoning"]}')
        
        # Build system prompt with confidence-aware instructions
        system_prompt = build_system_prompt(
            meeting_context_data['context_text'],
            question_intent,
            confidence_score,
            meeting_context_data.get('relevant_segments', [])
        )
        
        # Determine response state based on confidence
        if confidence_score < 0.5 and question_intent['needs_meeting_context']:
            # Low confidence - should not answer or ask for clarification
            response_state = 'no_answer'
        elif confidence_score < 0.7 and question_intent['needs_meeting_context']:
            # Moderate confidence - tentative answer
            response_state = 'tentative'
        else:
            # High confidence or general question - confident answer
            response_state = 'confident'
        
        print(f'[ChatAPI] Response state: {response_state}')
        
        # Check if Groq is available
        if Groq is None:
            response = JsonResponse({
                'error': 'Groq API not available. Please install groq package.',
                'response': "I'm having trouble connecting right now. Please try again in a moment!"
            }, status=500)
            return add_cors_headers(response, request)
        
        # Initialize Groq client
        groq_api_key = os.getenv('GROQ_API_KEY', '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')
        if not groq_api_key:
            response = JsonResponse({
                'error': 'GROQ_API_KEY not configured',
                'response': "I'm having trouble connecting right now. Please try again in a moment!"
            }, status=500)
            return add_cors_headers(response, request)
        
        groq_client = Groq(api_key=groq_api_key)
        
        # Check cache first (to reduce API calls)
        cache_key = None
        if backend_user_id:
            # Create cache key from user_id, message, and context hash
            context_hash = hashlib.md5(meeting_context_data['context_text'].encode()).hexdigest()[:8]
            cache_key_data = f"{backend_user_id}:{user_message}:{context_hash}"
            cache_key = hashlib.md5(cache_key_data.encode()).hexdigest()
            
            # Check if cached response exists and is still valid
            if cache_key in _response_cache:
                cached_data = _response_cache[cache_key]
                cache_age = timezone.now() - cached_data['timestamp']
                if cache_age < _cache_expiry:
                    print(f'[ChatAPI] Using cached response (age: {cache_age.total_seconds():.1f}s)')
                    response_text = cached_data['response']
                else:
                    # Expired cache entry
                    del _response_cache[cache_key]
                    cache_key = None
        
        # Initialize formatted_segments
        formatted_segments = []
        
        # If confidence is too low and question needs meeting context, skip API call and return clarification request
        if response_state == 'no_answer' and question_intent['needs_meeting_context']:
            print(f'[ChatAPI] Confidence too low ({confidence_score:.2f}) - returning clarification request')
            response_text = "I don't have enough information from the current meeting to answer that. Could you provide more details or rephrase your question?"
            
            # Format relevant segments for response (even if low confidence, show what we found)
            for seg in meeting_context_data.get('relevant_segments', [])[:3]:
                start_time = seg.get('start_time', 0)
                minutes = int(start_time // 60)
                seconds = int(start_time % 60)
                time_str = f"{minutes}:{seconds:02d}"
                formatted_segments.append({
                    'text': seg.get('text', '')[:200],  # Truncate long segments
                    'speaker': seg.get('speaker', 'Unknown'),
                    'timestamp': time_str,
                    'start_time': start_time,
                    'relevance_score': seg.get('relevance_score', 0)
                })
        # Call Groq API only if not cached
        elif cache_key is None or cache_key not in _response_cache:
            # Build messages for Groq
            messages = [{"role": "system", "content": system_prompt}]
            
            # Add conversation history (last 5 messages to reduce token usage)
            for msg in conversation_history[-5:]:
                if msg.get('sender') == 'user':
                    messages.append({"role": "user", "content": msg.get('text', '')})
                elif msg.get('sender') == 'ellie':
                    messages.append({"role": "assistant", "content": msg.get('text', '')})
            
            # Add current message
            messages.append({"role": "user", "content": user_message})
            
            print(f'[ChatAPI] Calling Groq API (messages: {len(messages)}, context length: {len(meeting_context_data["context_text"])})...')
            
            # Call Groq API
            chat_completion = groq_client.chat.completions.create(
                messages=messages,
                model="llama-3.3-70b-versatile",
                temperature=0.6,  # Slightly lower for more consistent responses
                max_tokens=150,  # Limited to enforce concise responses
            )
            
            # Extract response
            response_text = chat_completion.choices[0].message.content
            
            # Clean response
            response_text = clean_response(response_text)
            
            # Add tentative prefix if needed
            if response_state == 'tentative' and question_intent.get('live_meeting_only'):
                if not response_text.lower().startswith('based on'):
                    response_text = f"Based on what's discussed so far, {response_text.lower()}"
            
            # Cache the response
            if backend_user_id and cache_key:
                # Limit cache size
                if len(_response_cache) >= _cache_max_size:
                    # Remove oldest entries (simple approach: clear 20% oldest)
                    sorted_entries = sorted(_response_cache.items(), key=lambda x: x[1]['timestamp'])
                    for old_key, _ in sorted_entries[:_cache_max_size // 5]:
                        del _response_cache[old_key]
                
                _response_cache[cache_key] = {
                    'response': response_text,
                    'timestamp': timezone.now()
                }
                print(f'[ChatAPI] Response cached')
        
        print(f'[ChatAPI] Response generated: {response_text[:100]}...')
        print(f'[ChatAPI] ==========================================')
        
        # Get bot_id from live meeting if available (for contextual nudges)
        bot_id = None
        live_transcription = meeting_context_data.get('live_transcription')
        if live_transcription:
            bot_id = live_transcription.bot_id
        
        # Format relevant segments for response (with timestamps) if not already done
        if not formatted_segments:
            for seg in meeting_context_data.get('relevant_segments', [])[:5]:
                start_time = seg.get('start_time', 0)
                minutes = int(start_time // 60)
                seconds = int(start_time % 60)
                time_str = f"{minutes}:{seconds:02d}"
                
                formatted_segments.append({
                    'text': seg.get('text', '')[:300],  # Truncate for response
                    'speaker': seg.get('speaker', 'Unknown'),
                    'timestamp': time_str,
                    'start_time': start_time,
                    'relevance_score': seg.get('relevance_score', 0)
                })
        
        response = JsonResponse({
            'response': response_text,
            'success': True,
            'has_live_meetings': meeting_context_data['has_live_meetings'],
            'live_meeting_count': meeting_context_data['live_meeting_count'],
            'bot_id': bot_id,  # Include bot_id for contextual nudges
            # Context confidence data
            'confidence_score': confidence_score,
            'response_state': response_state,  # 'confident', 'tentative', or 'no_answer'
            'has_sufficient_context': has_sufficient_context,
            'grounded_segments': formatted_segments,  # Relevant transcript segments with timestamps
            'confidence_reasoning': confidence_data.get('reasoning', '')
        })
        return add_cors_headers(response, request)
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f'[ChatAPI] Error: {str(e)}')
        response = JsonResponse({
            'error': 'An error occurred while processing your request',
            'details': str(e),
            'response': "I'm having trouble connecting right now. Please try again in a moment!"
        }, status=500)
        return add_cors_headers(response, request)

