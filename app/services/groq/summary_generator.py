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
    
    # Enhanced prompt for accurate summary and action items with participant names
    prompt = f"""You are an expert meeting analyst. Analyze the COMPLETE meeting transcript below and generate a comprehensive summary and action items.

INSTRUCTIONS:
1. Read the ENTIRE transcript carefully from start to finish
2. Identify all participants by their names as they appear in the transcript
3. Create a detailed, chronological summary that captures:
   - Key topics discussed
   - Important decisions made
   - Main points raised by each participant (use their actual names)
   - Outcomes and conclusions
   - Any deadlines or timelines mentioned
4. Extract ALL action items with:
   - The specific task or deliverable
   - Who is responsible (use participant names)
   - Any deadlines or timelines mentioned
   - Context about why the action item is needed

REQUIREMENTS:
- Be thorough and accurate - don't miss important details
- Include participant names in the summary when relevant
- For action items, always include the responsible person's name if mentioned
- Maintain chronological flow in the summary
- Capture nuances and context, not just surface-level information
- If an action item has a deadline, include it in the text

Format your response as VALID JSON only (no markdown, no code blocks, no explanations):
{{
  "summary": "A comprehensive, detailed summary of the meeting that includes participant names, key discussions, decisions, and outcomes. Write in clear paragraphs covering the entire meeting chronologically.",
  "action_items": [
    {{"text": "Complete action item description with responsible person name and deadline if mentioned"}},
    {{"text": "Another action item with full context"}}
  ]
}}

Meeting Transcript (COMPLETE - analyze all of it):
{transcript_text}"""
    
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {
                "role": "system",
                "content": "You are a professional meeting analyst. Your task is to analyze meeting transcripts and extract comprehensive summaries and action items. Always be thorough, accurate, and include participant names when relevant."
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": 0.2,  # Lower temperature for more accurate and consistent results
        "max_tokens": 4000  # Increased for longer, more detailed summaries
    }
    
    try:
        # Calculate transcript size in tokens (rough estimate: 1 token ≈ 4 characters)
        estimated_tokens = len(transcript_text) // 4
        estimated_total_tokens = estimated_tokens + 1000  # Add prompt tokens
        
        print(f'[Groq] ==========================================')
        print(f'[Groq] 🤖 GENERATING SUMMARY & ACTION ITEMS')
        print(f'[Groq] Model: llama-3.3-70b-versatile (128K context window)')
        print(f'[Groq] Full transcript length: {len(transcript_text):,} chars')
        print(f'[Groq] Estimated tokens: ~{estimated_tokens:,} (input)')
        print(f'[Groq] Total estimated: ~{estimated_total_tokens:,} tokens')
        print(f'[Groq] ✅ Sending COMPLETE transcript (no truncation)')
        print(f'[Groq] ==========================================')
        
        # Increased timeout for longer transcripts
        timeout_seconds = max(60, len(transcript_text) // 1000)  # At least 60s, more for longer transcripts
        response = requests.post(endpoint, json=payload, headers=headers, timeout=timeout_seconds)
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
            
            # Ensure action_items is a list of dicts with proper formatting
            if action_items and isinstance(action_items, list):
                formatted_action_items = []
                for item in action_items:
                    if isinstance(item, dict):
                        # Extract text - include speaker name in text if available
                        text = item.get('text', item.get('action', item.get('item', str(item)))).strip()
                        # If speaker/responsible person is separate, append to text
                        speaker = item.get('speaker') or item.get('responsible') or item.get('assignee') or item.get('owner')
                        if speaker and speaker.strip() and speaker.strip() not in text:
                            text = f"{text} (Responsible: {speaker.strip()})"
                        if text:  # Only add non-empty action items
                            formatted_action_items.append({"text": text})
                    elif isinstance(item, str) and item.strip():
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

