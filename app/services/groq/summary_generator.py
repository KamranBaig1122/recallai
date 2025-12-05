"""
Service to generate summary and action items from transcript using Groq API
"""
import os
import requests
import json
from typing import Dict, Any, Optional


def generate_summary_and_action_items_with_groq(transcript_text: str) -> Optional[Dict[str, Any]]:
    """
    Generate summary and action items from transcript text using Groq API
    
    Args:
        transcript_text: The transcript text from the meeting
        
    Returns:
        Dict with summary and action_items, or None if failed
    """
    api_key = os.getenv('GROQ_API_KEY', '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')
    
    if not api_key:
        print('[Groq] ⚠ WARNING: GROQ_API_KEY not set')
        return None
    
    if not transcript_text or len(transcript_text.strip()) < 10:
        print('[Groq] ⚠ WARNING: Transcript text is too short or empty')
        return None
    
    endpoint = "https://api.groq.com/openai/v1/chat/completions"
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    # Create prompt that asks for summary (without names) and action items
    prompt = f"""Analyze the following meeting transcript and provide:

1. A comprehensive summary of the meeting (DO NOT include any participant names or personal identifiers - use generic terms like "the speaker" or "participants")
2. A list of action items mentioned in the meeting

Format your response as JSON with the following structure:
{{
  "summary": "detailed summary here without any names",
  "action_items": [
    {{"text": "action item 1"}},
    {{"text": "action item 2"}}
  ]
}}

Meeting Transcript:
{transcript_text[:8000]}"""  # Limit to 8000 chars to stay within token limits
    
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": 0.3,  # Lower temperature for more consistent results
        "max_tokens": 2000
    }
    
    try:
        print(f'[Groq] ==========================================')
        print(f'[Groq] 🤖 GENERATING SUMMARY & ACTION ITEMS')
        print(f'[Groq] Model: llama-3.3-70b-versatile')
        print(f'[Groq] Transcript length: {len(transcript_text)} chars')
        print(f'[Groq] ==========================================')
        
        response = requests.post(endpoint, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        
        result = response.json()
        
        # Extract the content from the response
        choices = result.get('choices', [])
        if not choices:
            print(f'[Groq] ❌ ERROR: No choices in response')
            return None
        
        content = choices[0].get('message', {}).get('content', '')
        
        if not content:
            print(f'[Groq] ❌ ERROR: No content in response')
            return None
        
        print(f'[Groq] ✅ Received response from Groq')
        print(f'[Groq] Response length: {len(content)} chars')
        
        # Try to parse JSON from response
        try:
            # Extract JSON from response text (might be wrapped in markdown code blocks)
            json_str = content.strip()
            
            # Remove markdown code blocks if present
            if json_str.startswith('```'):
                # Find the first { and last }
                json_start = json_str.find('{')
                json_end = json_str.rfind('}') + 1
                if json_start >= 0 and json_end > json_start:
                    json_str = json_str[json_start:json_end]
            
            parsed = json.loads(json_str)
            
            summary = parsed.get('summary', '').strip()
            action_items = parsed.get('action_items', [])
            
            # Ensure action_items is a list of dicts
            if action_items and isinstance(action_items, list):
                # Convert to proper format if needed
                formatted_action_items = []
                for item in action_items:
                    if isinstance(item, dict):
                        formatted_action_items.append({
                            "text": item.get('text', str(item)).strip()
                        })
                    elif isinstance(item, str):
                        formatted_action_items.append({"text": item.strip()})
                
                action_items = formatted_action_items
            
            print(f'[Groq] ✅ Parsed summary and action items')
            print(f'[Groq] Summary length: {len(summary)} chars')
            print(f'[Groq] Action items: {len(action_items)} items')
            print(f'[Groq] ==========================================')
            
            return {
                "summary": summary,
                "action_items": action_items
            }
            
        except json.JSONDecodeError as e:
            print(f'[Groq] ⚠ WARNING: Could not parse JSON from response')
            print(f'[Groq] Response content: {content[:500]}...')
            print(f'[Groq] Error: {e}')
            
            # Fallback: Try to extract summary and action items manually
            # Look for "summary" and "action_items" in the text
            summary = ""
            action_items = []
            
            # Try to find summary section
            if '"summary"' in content.lower() or 'summary' in content.lower():
                # Extract text after "summary"
                summary_match = content.lower().find('summary')
                if summary_match >= 0:
                    # Get text after summary keyword
                    summary_text = content[summary_match + 7:summary_match + 500]
                    # Clean up
                    summary = summary_text.split('"')[1] if '"' in summary_text else summary_text.split('\n')[0]
                    summary = summary.strip()
            
            # Try to find action items
            if '"action_items"' in content.lower() or 'action items' in content.lower():
                # Look for list items
                lines = content.split('\n')
                in_action_items = False
                for line in lines:
                    if 'action' in line.lower() and 'item' in line.lower():
                        in_action_items = True
                        continue
                    if in_action_items and (line.strip().startswith('-') or line.strip().startswith('*') or line.strip().startswith('1.')):
                        action_text = line.strip().lstrip('-*0123456789. ').strip()
                        if action_text:
                            action_items.append({"text": action_text})
            
            # If we couldn't extract, use the full content as summary
            if not summary:
                summary = content[:1000]  # Limit summary length
            
            print(f'[Groq] ⚠ Using fallback extraction')
            print(f'[Groq] Summary length: {len(summary)} chars')
            print(f'[Groq] Action items: {len(action_items)} items')
            print(f'[Groq] ==========================================')
            
            return {
                "summary": summary,
                "action_items": action_items
            }
            
    except requests.exceptions.RequestException as e:
        print(f'[Groq] ❌ ERROR: Failed to generate summary: {e}')
        if hasattr(e, 'response') and e.response is not None:
            print(f'[Groq] Response status: {e.response.status_code}')
            print(f'[Groq] Response body: {e.response.text[:500]}')
        return None
    except Exception as e:
        print(f'[Groq] ❌ ERROR: Unexpected error: {e}')
        import traceback
        traceback.print_exc()
        return None

