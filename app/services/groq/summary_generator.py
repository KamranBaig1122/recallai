"""
Service to generate meeting intelligence from transcript using Groq API:
what changed, structured action items, gaps, and open questions.
"""
import json
import os
import requests
from typing import Any, Dict, List, Optional


def _normalize_action_items(raw: Any) -> List[Dict[str, Any]]:
    if not raw or not isinstance(raw, list):
        return []
    out: List[Dict[str, Any]] = []
    for item in raw:
        if isinstance(item, str) and item.strip():
            out.append({
                "text": item.strip(),
                "owner": None,
                "deadline": None,
                "clarity": "clear",
                "blockers": None,
            })
            continue
        if not isinstance(item, dict):
            continue
        text = (
            item.get("text")
            or item.get("action")
            or item.get("item")
            or ""
        )
        if isinstance(text, str):
            text = text.strip()
        else:
            text = str(text).strip()
        if not text:
            continue
        owner = item.get("owner") or item.get("assignee") or item.get("responsible") or item.get("speaker")
        if owner is not None and not isinstance(owner, str):
            owner = str(owner)
        deadline = item.get("deadline")
        if deadline is not None and not isinstance(deadline, str):
            deadline = str(deadline)
        clarity_raw = item.get("clarity") or item.get("status")
        if isinstance(clarity_raw, str) and clarity_raw.lower() in ("clear", "vague"):
            clarity = clarity_raw.lower()
        else:
            clarity = "vague" if item.get("vague") else "clear"
        blockers = item.get("blockers") or item.get("blocker")
        if blockers is not None and not isinstance(blockers, str):
            blockers = str(blockers)
        out.append({
            "text": text,
            "owner": owner.strip() if isinstance(owner, str) and owner.strip() else None,
            "deadline": deadline.strip() if isinstance(deadline, str) and deadline.strip() else None,
            "clarity": clarity,
            "blockers": blockers.strip() if isinstance(blockers, str) and blockers.strip() else None,
        })
    return out


def _normalize_string_list(raw: Any, max_items: int = 25) -> List[str]:
    if not raw:
        return []
    if isinstance(raw, str) and raw.strip():
        return [raw.strip()][:max_items]
    if not isinstance(raw, list):
        return []
    out: List[str] = []
    for x in raw[:max_items]:
        if isinstance(x, str) and x.strip():
            out.append(x.strip())
        elif x is not None:
            s = str(x).strip()
            if s:
                out.append(s)
    return out


def _parse_groq_payload(parsed: Dict[str, Any]) -> Dict[str, Any]:
    summary = (parsed.get("summary") or "").strip()
    action_items = _normalize_action_items(parsed.get("action_items"))
    gaps = _normalize_string_list(parsed.get("gaps_identified") or parsed.get("meeting_gaps"))
    open_q = _normalize_string_list(parsed.get("open_questions") or parsed.get("still_unclear"))
    return {
        "summary": summary,
        "action_items": action_items,
        "meeting_gaps": gaps,
        "open_questions": open_q,
    }


def generate_summary_and_action_items_with_groq(transcript_text: str) -> Optional[Dict[str, Any]]:
    """
    Generate decision/impact summary, execution-style action items, gaps, and open questions.

    Returns:
        Dict with summary, action_items, meeting_gaps, open_questions; or None if failed
    """
    api_key = os.getenv("GROQ_API_KEY", "").strip()

    if not api_key:
        print("[Groq] ⚠ WARNING: GROQ_API_KEY not set")
        return None

    if not transcript_text or len(transcript_text.strip()) < 10:
        print("[Groq] ⚠ WARNING: Transcript text is too short or empty")
        return None

    endpoint = "https://api.groq.com/openai/v1/chat/completions"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    prompt = f"""You are an expert meeting analyst. Read the COMPLETE transcript and produce structured intelligence for someone who did NOT attend. They need immediate clarity: what changed, what is blocked, what needs action — not a chronological play-by-play.

OUTPUT RULES:
1. "summary" — 2–5 short paragraphs titled in spirit "what changed": decisions made, impact on timeline/scope/delivery, ownership where clear, and what remains at risk. Do NOT narrate the meeting minute-by-minute.

2. "action_items" — every commitment or task. For EACH item include:
   - "text": the task in one line
   - "owner": person/role if mentioned, else null
   - "deadline": explicit date/time if mentioned; if none say null (do not invent dates)
   - "clarity": "clear" or "vague" (vague = missing owner, deadline, or scope)
   - "blockers": dependency or blocker if mentioned, else null

3. "gaps_identified" — bullet strings: missing owners, missing deadlines, contradictions (e.g. timeline 2 vs 3 weeks), unassigned dependencies, undefined next steps. Empty list if none.

4. "open_questions" — bullet strings: questions left unanswered or ambiguous. Empty list if none.

Respond with VALID JSON only (no markdown fences):
{{
  "summary": "…",
  "action_items": [
    {{
      "text": "…",
      "owner": "… or null",
      "deadline": "… or null",
      "clarity": "clear",
      "blockers": "… or null"
    }}
  ],
  "gaps_identified": ["…"],
  "open_questions": ["…"]
}}

Meeting transcript:
{transcript_text}"""

    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {
                "role": "system",
                "content": "You extract decision-focused meeting intelligence and return only valid JSON.",
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
        "max_tokens": 4000,
    }

    content = ""
    try:
        estimated_tokens = len(transcript_text) // 4
        print("[Groq] ==========================================")
        print("[Groq] 🤖 GENERATING MEETING INTELLIGENCE (summary, actions, gaps, questions)")
        print(f"[Groq] Transcript length: {len(transcript_text):,} chars (~{estimated_tokens} tokens input)")
        print("[Groq] ==========================================")

        timeout_seconds = max(60, len(transcript_text) // 1000)
        response = requests.post(endpoint, json=payload, headers=headers, timeout=timeout_seconds)
        response.raise_for_status()

        result = response.json()
        choices = result.get("choices", [])
        if not choices:
            print("[Groq] ❌ ERROR: No choices in response")
            return None

        content = choices[0].get("message", {}).get("content", "") or ""
        if not content:
            print("[Groq] ❌ ERROR: No content in response")
            return None

        json_str = content.strip()
        if json_str.startswith("```"):
            json_start = json_str.find("{")
            json_end = json_str.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                json_str = json_str[json_start:json_end]

        parsed = json.loads(json_str)
        if not isinstance(parsed, dict):
            return None

        normalized = _parse_groq_payload(parsed)
        print(f"[Groq] ✅ Summary length: {len(normalized['summary'])} chars; "
              f"actions: {len(normalized['action_items'])}; "
              f"gaps: {len(normalized['meeting_gaps'])}; "
              f"open_questions: {len(normalized['open_questions'])}")
        print("[Groq] ==========================================")
        return normalized

    except json.JSONDecodeError as e:
        print(f"[Groq] ⚠ WARNING: Could not parse JSON: {e}")
        print(f"[Groq] Content preview: {content[:500]}...")
        return None
    except requests.exceptions.RequestException as e:
        print(f"[Groq] ❌ ERROR: Failed to generate summary: {e}")
        if hasattr(e, "response") and e.response is not None:
            print(f"[Groq] Response status: {e.response.status_code}")
            print(f"[Groq] Response body: {e.response.text[:500]}")
        return None
    except Exception as e:
        print(f"[Groq] ❌ ERROR: Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return None
