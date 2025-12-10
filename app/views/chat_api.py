"""
Chat API endpoint for Ellie bot
Uses Groq API with meeting context
"""
import os
import re
import json
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from app.views.calendar_api import add_cors_headers, get_backend_user_id_from_request
from app.logic.chat_context import analyze_question_intent, build_meeting_context

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


def build_system_prompt(meeting_context: str) -> str:
    """Build system prompt with optional meeting context"""
    prompt = BASE_SYSTEM_PROMPT
    
    if meeting_context:
        prompt += f"""

\n\n=== MEETING CONTEXT (Use this when questions are about meetings) ===
{meeting_context}
=== END MEETING CONTEXT ===

When asked about meetings, use the context above. Reference meetings by title or date.
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
        
        # Build meeting context (only if needed)
        meeting_context_data = {
            'context_text': '',
            'has_live_meetings': False,
            'live_meeting_count': 0
        }
        
        if question_intent['needs_meeting_context'] and backend_user_id:
            meeting_context_data = build_meeting_context(backend_user_id, question_intent)
            print(f'[ChatAPI] Meeting context built')
            print(f'[ChatAPI] Has live meetings: {meeting_context_data["has_live_meetings"]}')
            print(f'[ChatAPI] Live meeting count: {meeting_context_data["live_meeting_count"]}')
        
        # Build system prompt
        system_prompt = build_system_prompt(meeting_context_data['context_text'])
        
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
        
        # Build messages for Groq
        messages = [{"role": "system", "content": system_prompt}]
        
        # Add conversation history (last 10 messages)
        for msg in conversation_history[-10:]:
            if msg.get('sender') == 'user':
                messages.append({"role": "user", "content": msg.get('text', '')})
            elif msg.get('sender') == 'ellie':
                messages.append({"role": "assistant", "content": msg.get('text', '')})
        
        # Add current message
        messages.append({"role": "user", "content": user_message})
        
        print(f'[ChatAPI] Calling Groq API...')
        
        # Call Groq API
        chat_completion = groq_client.chat.completions.create(
            messages=messages,
            model="llama-3.3-70b-versatile",
            temperature=0.7,
            max_tokens=150,  # Limited to enforce concise responses
        )
        
        # Extract response
        response_text = chat_completion.choices[0].message.content
        
        # Clean response
        response_text = clean_response(response_text)
        
        print(f'[ChatAPI] Response generated: {response_text[:100]}...')
        print(f'[ChatAPI] ==========================================')
        
        response = JsonResponse({
            'response': response_text,
            'success': True,
            'has_live_meetings': meeting_context_data['has_live_meetings'],
            'live_meeting_count': meeting_context_data['live_meeting_count']
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

