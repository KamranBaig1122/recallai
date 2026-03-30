"""
Contextual nudges and key outcomes/signals from transcript using Groq (replaces legacy impact score).
"""
import json
import os
import re
import requests
from typing import Any, Dict, List, Optional


def generate_contextual_nudges_and_signals_with_groq(
    transcript_text: str,
    summary: str = "",
    action_items: List[Dict] = None,
    previous_meetings: List[Dict] = None,
) -> Optional[Dict[str, Any]]:
    """
    Generate contextual nudges and key outcome/signal bullets (not abstract scores).

    Returns:
        Dict with contextual_nudges and key_outcomes_signals, or None if failed
    """
    api_key = os.getenv("GROQ_API_KEY", "").strip()

    if not api_key:
        print("[Groq Nudges] ⚠ WARNING: GROQ_API_KEY not set")
        return None

    if not transcript_text or len(transcript_text.strip()) < 10:
        print("[Groq Nudges] ⚠ WARNING: Transcript text is too short or empty")
        return None

    full_transcript = transcript_text.strip()
    transcript_length = len(full_transcript)
    print(f"[Groq Nudges] Transcript length: {transcript_length:,} characters")

    endpoint = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    previous_context = ""
    if previous_meetings and len(previous_meetings) > 0:
        previous_context = "\n\n=== PREVIOUS MEETING CONTEXT ===\n"
        for i, meeting in enumerate(previous_meetings[:5], 1):
            if meeting.get("summary"):
                prev_summary = meeting.get("summary", "")
                prev_date = meeting.get("date", meeting.get("created_at", "Unknown date"))
                previous_context += f"\nMeeting {i} ({prev_date}):\n{prev_summary}\n"

    prompt = f"""You analyze meetings for someone who missed the call. They do not want a "quality score" — they want concrete signals: what changed, what is broken, what needs action.

Produce:
1) contextual_nudges — short actionable prompts (same style as before): missed ownership, conflicts with prior context, unanswered questions, vague commitments, missing stakeholders, end-of-call without recap. Each object: text, type, timestamp, speaker, explanation.

2) key_outcomes_signals — 4–12 SHORT bullet strings (not paragraphs) capturing outcomes and signals, e.g. "Timeline extended from 2 → 3 weeks", "Safety approval named as blocker", "Task X assigned with no deadline". No numbering in the strings unless part of a quote.

Do NOT output impact_score or any numeric meeting score.

JSON shape:
{{
  "contextual_nudges": [
    {{
      "text": "…",
      "type": "missing_owner",
      "timestamp": "",
      "speaker": "",
      "explanation": ""
    }}
  ],
  "key_outcomes_signals": [
    "Signal or outcome one",
    "Signal or outcome two"
  ]
}}

=== MEETING SUMMARY (from prior analysis) ===
{summary if summary else "No summary available"}

=== ACTION ITEMS ===
{json.dumps(action_items[:30] if action_items else [], indent=2)}

{previous_context}

=== FULL MEETING TRANSCRIPT ===
{full_transcript}
"""

    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {
                "role": "system",
                "content": "You extract actionable nudges and concrete outcome signals from transcripts. Output only valid JSON. Never output impact scores.",
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.3,
        "max_tokens": 4000,
    }

    try:
        print("[Groq Nudges] 🤖 GENERATING CONTEXTUAL NUDGES & KEY OUTCOMES/SIGNALS")
        response = requests.post(endpoint, json=payload, headers=headers, timeout=120)
        response.raise_for_status()

        result = response.json()
        choices = result.get("choices", [])
        if not choices:
            print("[Groq Nudges] ❌ ERROR: No choices in response")
            return None

        content = choices[0].get("message", {}).get("content", "")
        if not content:
            print("[Groq Nudges] ❌ ERROR: No content in response")
            return None

        json_str = content.strip()
        if json_str.startswith("```"):
            json_start = json_str.find("{")
            json_end = json_str.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                json_str = json_str[json_start:json_end]

        parsed = json.loads(json_str)
        contextual_nudges = parsed.get("contextual_nudges", [])
        key_signals = parsed.get("key_outcomes_signals", [])

        if key_signals and isinstance(key_signals, list):
            key_signals = [s.strip() for s in key_signals if isinstance(s, str) and s.strip()][:20]
        else:
            key_signals = []

        if contextual_nudges and isinstance(contextual_nudges, list):
            formatted_nudges = []
            for nudge in contextual_nudges:
                if isinstance(nudge, dict):
                    formatted_nudges.append({
                        "text": nudge.get("text", "").strip(),
                        "type": nudge.get("type", "general"),
                        "timestamp": nudge.get("timestamp", ""),
                        "speaker": nudge.get("speaker", ""),
                        "explanation": nudge.get("explanation", ""),
                    })
                elif isinstance(nudge, str):
                    formatted_nudges.append({
                        "text": nudge.strip(),
                        "type": "general",
                        "timestamp": "",
                        "speaker": "",
                        "explanation": "",
                    })
            contextual_nudges = formatted_nudges
        else:
            contextual_nudges = []

        print(f"[Groq Nudges] ✅ Nudges: {len(contextual_nudges)}; key_outcomes_signals: {len(key_signals)}")
        return {
            "contextual_nudges": contextual_nudges,
            "key_outcomes_signals": key_signals,
        }

    except json.JSONDecodeError as e:
        print(f"[Groq Nudges] ⚠ WARNING: Could not parse JSON: {e}")
        return _fallback_nudge_parse(content if "content" in locals() else "")
    except requests.exceptions.RequestException as e:
        print(f"[Groq Nudges] ❌ ERROR: Failed to generate nudges: {e}")
        if hasattr(e, "response") and e.response is not None:
            print(f"[Groq Nudges] Response status: {e.response.status_code}")
            print(f"[Groq Nudges] Response body: {e.response.text[:500]}")
        return None
    except Exception as e:
        print(f"[Groq Nudges] ❌ ERROR: Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return None


def _fallback_nudge_parse(content: str) -> Dict[str, Any]:
    """Best-effort extraction if JSON parsing fails."""
    key_signals: List[str] = []
    m = re.search(r'"key_outcomes_signals"\s*:\s*\[(.*?)\]', content, re.DOTALL)
    if m:
        for line in m.group(1).split("\n"):
            q = re.search(r'"([^"]+)"', line)
            if q:
                key_signals.append(q.group(1).strip())
    return {
        "contextual_nudges": [],
        "key_outcomes_signals": key_signals[:20],
    }


# Backward-compatible name for imports
generate_contextual_nudges_and_impact_score_with_groq = generate_contextual_nudges_and_signals_with_groq
