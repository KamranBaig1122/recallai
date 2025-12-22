"""
Service to generate contextual nudges and impact score from transcript using Groq API
"""
import os
import requests
import json
from typing import Dict, Any, Optional, List


def generate_contextual_nudges_and_impact_score_with_groq(
    transcript_text: str,
    summary: str = "",
    action_items: List[Dict] = None,
    previous_meetings: List[Dict] = None
) -> Optional[Dict[str, Any]]:
    """
    Generate contextual nudges and impact score from transcript using Groq API
    
    Contextual nudges are actionable prompts based on:
    - What is being said in the meeting
    - Who is speaking
    - What was discussed in previous meetings
    - Missing decisions, vague commitments, forgotten context, poor follow-through
    
    Impact score (0-100) measures:
    - Decision-making effectiveness
    - Action item clarity
    - Stakeholder engagement
    - Meeting productivity
    
    Args:
        transcript_text: The transcript text from the meeting
        summary: The meeting summary (if available)
        action_items: List of action items from the meeting
        previous_meetings: List of previous meeting summaries for context
        
    Returns:
        Dict with contextual_nudges and impact_score, or None if failed
    """
    api_key = os.getenv('GROQ_API_KEY', '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')
    
    if not api_key:
        print('[Groq Nudges] ⚠ WARNING: GROQ_API_KEY not set')
        return None
    
    if not transcript_text or len(transcript_text.strip()) < 10:
        print('[Groq Nudges] ⚠ WARNING: Transcript text is too short or empty')
        return None
    
    endpoint = "https://api.groq.com/openai/v1/chat/completions"
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    # Build context from previous meetings
    previous_context = ""
    if previous_meetings and len(previous_meetings) > 0:
        previous_context = "\n\nPrevious Meeting Context:\n"
        for meeting in previous_meetings[:5]:  # Limit to last 5 meetings
            if meeting.get('summary'):
                previous_context += f"- {meeting.get('summary', '')[:200]}...\n"
    
    # Create comprehensive prompt for contextual nudges and impact score
    prompt = f"""Analyze the following meeting transcript and provide:

1. CONTEXTUAL NUDGES: Identify actionable prompts based on:
   - Missing decisions (e.g., "Release timeline mentioned, but no owner assigned")
   - Vague commitments (e.g., "Vague change mentioned. Ask for specifics?")
   - Potential conflicts with previous meetings (e.g., "Potential mismatch with last agreed scope")
   - Unanswered questions (e.g., "Pricing question raised but not answered")
   - Missing stakeholders (e.g., "Marketing stakeholder not present")
   - Missing follow-ups (e.g., "Dependency identified but no follow-up discussed")
   - Meeting ending without recap (e.g., "Meeting ending without confirmed next steps")

2. IMPACT SCORE: Rate the meeting's impact from 0-100 based on:
   - Decision-making effectiveness (0-25 points)
   - Action item clarity and ownership (0-25 points)
   - Stakeholder engagement and coverage (0-25 points)
   - Meeting productivity and follow-through potential (0-25 points)

Each nudge should be:
- Short and actionable (max 100 characters)
- Linked to a specific moment in the transcript (include timestamp or speaker context)
- Explainable (why this nudge is relevant)
- Non-blocking (suggestive, not demanding)

Format your response as JSON:
{{
  "contextual_nudges": [
    {{
      "text": "Release timeline mentioned, but no owner assigned. Assign responsibility?",
      "type": "missing_owner",
      "timestamp": "15:32",
      "speaker": "Participant 1",
      "explanation": "A timeline was discussed but no one was assigned to own the release"
    }},
    {{
      "text": "Vague change mentioned. Ask for specifics or acceptance criteria?",
      "type": "vague_commitment",
      "timestamp": "22:15",
      "speaker": "Participant 2",
      "explanation": "A change was mentioned without specific details or criteria"
    }}
  ],
  "impact_score": 75.5,
  "impact_breakdown": {{
    "decision_making": 20,
    "action_clarity": 18,
    "stakeholder_engagement": 19,
    "productivity": 18.5
  }}
}}

Meeting Summary:
{summary[:1000] if summary else "No summary available"}

Action Items:
{json.dumps(action_items[:10], indent=2) if action_items else "No action items"}

Meeting Transcript (first 6000 chars):
{transcript_text[:6000]}{previous_context}

Analyze this meeting and provide contextual nudges and impact score."""
    
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": 0.4,  # Slightly higher for more creative nudges
        "max_tokens": 3000
    }
    
    try:
        print(f'[Groq Nudges] ==========================================')
        print(f'[Groq Nudges] 🤖 GENERATING CONTEXTUAL NUDGES & IMPACT SCORE')
        print(f'[Groq Nudges] Model: llama-3.3-70b-versatile')
        print(f'[Groq Nudges] Transcript length: {len(transcript_text)} chars')
        print(f'[Groq Nudges] ==========================================')
        
        response = requests.post(endpoint, json=payload, headers=headers, timeout=45)
        response.raise_for_status()
        
        result = response.json()
        
        # Extract the content from the response
        choices = result.get('choices', [])
        if not choices:
            print(f'[Groq Nudges] ❌ ERROR: No choices in response')
            return None
        
        content = choices[0].get('message', {}).get('content', '')
        
        if not content:
            print(f'[Groq Nudges] ❌ ERROR: No content in response')
            return None
        
        print(f'[Groq Nudges] ✅ Received response from Groq')
        print(f'[Groq Nudges] Response length: {len(content)} chars')
        
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
            
            contextual_nudges = parsed.get('contextual_nudges', [])
            impact_score = parsed.get('impact_score', None)
            impact_breakdown = parsed.get('impact_breakdown', {})
            
            # Ensure contextual_nudges is a list
            if contextual_nudges and isinstance(contextual_nudges, list):
                # Validate and format nudges
                formatted_nudges = []
                for nudge in contextual_nudges:
                    if isinstance(nudge, dict):
                        formatted_nudges.append({
                            "text": nudge.get('text', '').strip(),
                            "type": nudge.get('type', 'general'),
                            "timestamp": nudge.get('timestamp', ''),
                            "speaker": nudge.get('speaker', ''),
                            "explanation": nudge.get('explanation', '')
                        })
                    elif isinstance(nudge, str):
                        formatted_nudges.append({
                            "text": nudge.strip(),
                            "type": "general",
                            "timestamp": "",
                            "speaker": "",
                            "explanation": ""
                        })
                
                contextual_nudges = formatted_nudges
            
            # Validate impact score
            if impact_score is not None:
                try:
                    impact_score = float(impact_score)
                    # Clamp to 0-100
                    impact_score = max(0, min(100, impact_score))
                except (ValueError, TypeError):
                    impact_score = None
            
            print(f'[Groq Nudges] ✅ Parsed contextual nudges and impact score')
            print(f'[Groq Nudges] Nudges: {len(contextual_nudges)} items')
            print(f'[Groq Nudges] Impact score: {impact_score}')
            print(f'[Groq Nudges] ==========================================')
            
            return {
                "contextual_nudges": contextual_nudges,
                "impact_score": impact_score,
                "impact_breakdown": impact_breakdown
            }
            
        except json.JSONDecodeError as e:
            print(f'[Groq Nudges] ⚠ WARNING: Could not parse JSON from response')
            print(f'[Groq Nudges] Response content: {content[:500]}...')
            print(f'[Groq Nudges] Error: {e}')
            
            # Fallback: Try to extract nudges and score manually
            contextual_nudges = []
            impact_score = None
            
            # Try to find impact score
            if 'impact_score' in content.lower():
                import re
                score_match = re.search(r'"impact_score"\s*:\s*(\d+\.?\d*)', content)
                if score_match:
                    try:
                        impact_score = float(score_match.group(1))
                        impact_score = max(0, min(100, impact_score))
                    except:
                        pass
            
            # Try to find nudges
            if 'contextual_nudges' in content.lower() or 'nudge' in content.lower():
                # Look for list items or JSON array
                lines = content.split('\n')
                in_nudges = False
                for line in lines:
                    if 'nudge' in line.lower() and 'contextual' in line.lower():
                        in_nudges = True
                        continue
                    if in_nudges and ('"' in line or '-' in line or '*' in line):
                        # Extract text
                        text_match = re.search(r'"text"\s*:\s*"([^"]+)"', line)
                        if text_match:
                            contextual_nudges.append({
                                "text": text_match.group(1),
                                "type": "general",
                                "timestamp": "",
                                "speaker": "",
                                "explanation": ""
                            })
            
            print(f'[Groq Nudges] ⚠ Using fallback extraction')
            print(f'[Groq Nudges] Nudges: {len(contextual_nudges)} items')
            print(f'[Groq Nudges] Impact score: {impact_score}')
            print(f'[Groq Nudges] ==========================================')
            
            return {
                "contextual_nudges": contextual_nudges if contextual_nudges else [],
                "impact_score": impact_score,
                "impact_breakdown": {}
            }
            
    except requests.exceptions.RequestException as e:
        print(f'[Groq Nudges] ❌ ERROR: Failed to generate nudges: {e}')
        if hasattr(e, 'response') and e.response is not None:
            print(f'[Groq Nudges] Response status: {e.response.status_code}')
            print(f'[Groq Nudges] Response body: {e.response.text[:500]}')
        return None
    except Exception as e:
        print(f'[Groq Nudges] ❌ ERROR: Unexpected error: {e}')
        import traceback
        traceback.print_exc()
        return None

