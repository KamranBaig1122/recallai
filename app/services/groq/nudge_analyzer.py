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
    
    # Use full transcript (no truncation for 128k context window support)
    full_transcript = transcript_text.strip()
    transcript_length = len(full_transcript)
    
    # Log transcript length for monitoring
    print(f'[Groq Nudges] Transcript length: {transcript_length:,} characters (full transcript will be processed)')
    
    # Warn if transcript is extremely long (though we'll still process it with 128k context)
    if transcript_length > 100000:
        print(f'[Groq Nudges] ℹ INFO: Very long transcript ({transcript_length:,} chars). Using full transcript with 128k context window.')
    
    endpoint = "https://api.groq.com/openai/v1/chat/completions"
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    # Build context from previous meetings
    previous_context = ""
    if previous_meetings and len(previous_meetings) > 0:
        previous_context = "\n\n=== PREVIOUS MEETING CONTEXT ===\n"
        for i, meeting in enumerate(previous_meetings[:5], 1):  # Limit to last 5 meetings
            if meeting.get('summary'):
                prev_summary = meeting.get('summary', '')
                prev_date = meeting.get('date', meeting.get('created_at', 'Unknown date'))
                previous_context += f"\nMeeting {i} ({prev_date}):\n{prev_summary}\n"
    
    # Create comprehensive prompt aligned with real-world use cases
    prompt = f"""You are an intelligent meeting assistant that observes live meetings and proactively surfaces short, actionable prompts to prevent common meeting failures: missed decisions, vague commitments, forgotten context, and poor follow-through.

Analyze the ENTIRE meeting transcript below and identify contextual nudges based on these real-world scenarios:

1. MISSING OWNERSHIP / UNASSIGNED DECISIONS
   Example: Someone says "Let's ship this in two weeks" but no owner is assigned.
   Nudge: "Release timeline mentioned, but no owner assigned. Assign responsibility?"

2. CONFLICTS WITH PREVIOUS MEETINGS
   Example: Client says "This isn't what we discussed last time."
   Nudge: "Potential mismatch with last agreed scope (Nov 3). Review previous decision?"

3. UNANSWERED QUESTIONS
   Example: Prospect asks about pricing, but conversation moves on without answer.
   Nudge: "Pricing question raised but not answered. Circle back?"

4. MISSING FOLLOW-UPS / DEPENDENCIES
   Example: Engineer says "We'll need approval from security first" but no follow-up discussed.
   Nudge: "Dependency identified: Security approval. Track as blocker?"

5. VAGUE COMMITMENTS
   Example: Someone says "We'll tweak this later" without specifics.
   Nudge: "Vague change mentioned. Ask for specifics or acceptance criteria?"

6. MISSING STAKEHOLDERS
   Example: Decision made about marketing launch dates, but marketing lead not present.
   Nudge: "Marketing stakeholder not present. Loop them in before finalizing?"

7. MEETING ENDING WITHOUT RECAP
   Example: Call ending with multiple discussion threads but no confirmed next steps.
   Nudge: "Meeting ending without confirmed next steps. Generate summary + action items?"

CRITICAL REQUIREMENTS FOR EACH NUDGE:
- Short and actionable (max 100 characters)
- Linked to exact transcript moment (include timestamp or speaker name if available)
- Explainable (provide clear explanation of why this nudge is relevant)
- Non-blocking (suggestive question format, not demanding)
- Time-sensitive (only surface if action is still relevant)

ANALYSIS INSTRUCTIONS:
1. Read the ENTIRE transcript carefully from start to finish
2. Compare current discussion with previous meeting context (if provided)
3. Identify moments where decisions lack owners, questions go unanswered, commitments are vague, or follow-ups are missing
4. Check if key stakeholders are missing when important decisions are being made
5. Detect conflicts or inconsistencies with previous meeting outcomes
6. Note if meeting is ending without clear next steps or recap

IMPACT SCORE: Rate the meeting's impact from 0-100 based on:
- Decision-making effectiveness (0-25 points): Were clear decisions made with owners?
- Action item clarity and ownership (0-25 points): Are action items specific and assigned?
- Stakeholder engagement and coverage (0-25 points): Were right people present for decisions?
- Meeting productivity and follow-through potential (0-25 points): Will outcomes be actionable?

Format your response as JSON:
{{
  "contextual_nudges": [
    {{
      "text": "Release timeline mentioned, but no owner assigned. Assign responsibility?",
      "type": "missing_owner",
      "timestamp": "15:32",
      "speaker": "John Doe",
      "explanation": "At 15:32, John mentioned shipping in two weeks, but no one was assigned ownership of this timeline"
    }},
    {{
      "text": "Pricing question raised but not answered. Circle back?",
      "type": "unanswered_question",
      "timestamp": "22:15",
      "speaker": "Client",
      "explanation": "Client asked about pricing at 22:15, but the conversation moved on without addressing it"
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

=== MEETING SUMMARY ===
{summary if summary else "No summary available"}

=== ACTION ITEMS ===
{json.dumps(action_items[:20], indent=2) if action_items else "No action items"}

{previous_context}

=== FULL MEETING TRANSCRIPT ===
{full_transcript}

Analyze this complete meeting transcript and provide contextual nudges and impact score. Ensure accuracy by reading the entire transcript carefully."""
    
    payload = {
        "model": "llama-3.3-70b-versatile",  # Supports large context windows
        "messages": [
            {
                "role": "system",
                "content": "You are an expert meeting analyst specializing in identifying actionable insights, missed opportunities, and follow-up items from meeting transcripts. Be precise, contextual, and practical."
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": 0.3,  # Lower temperature for higher accuracy and consistency
        "max_tokens": 4000  # Increased for detailed analysis of longer transcripts
    }
    
    try:
        print(f'[Groq Nudges] ==========================================')
        print(f'[Groq Nudges] 🤖 GENERATING CONTEXTUAL NUDGES & IMPACT SCORE')
        print(f'[Groq Nudges] Model: llama-3.3-70b-versatile')
        print(f'[Groq Nudges] Transcript length: {transcript_length:,} chars (full transcript)')
        print(f'[Groq Nudges] Context window: 128k tokens (full transcript processing)')
        print(f'[Groq Nudges] Previous meetings context: {len(previous_meetings) if previous_meetings else 0} meetings')
        print(f'[Groq Nudges] ==========================================')
        
        # Increased timeout for processing full transcripts with 128k context window
        response = requests.post(endpoint, json=payload, headers=headers, timeout=120)
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

