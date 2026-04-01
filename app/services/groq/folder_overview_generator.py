"""
Synthesize a single folder-level summary and merged action items from multiple meetings (Groq).
"""
import json
import os
from typing import Any, Dict, List, Optional

import requests


def _fallback_from_bundle(meetings_bundle: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Deterministic merge when Groq returns invalid JSON or is unavailable.
    Keeps the UI working and matches what users expect (combined text + all actions).
    """
    parts: List[str] = []
    action_items: List[Dict[str, str]] = []
    for m in meetings_bundle:
        title = (m.get('title') or 'Untitled meeting').strip()
        when = (m.get('date_label') or '').strip()
        summary = (m.get('summary') or '').strip()
        header = f"{title}" + (f" ({when})" if when else "")
        if summary:
            parts.append(f"{header}\n\n{summary}")
        else:
            parts.append(f"{header}\n\n(No summary yet for this meeting.)")
        for a in (m.get('action_items') or [])[:40]:
            if isinstance(a, str) and a.strip():
                action_items.append({'text': a.strip(), 'meeting_title': title})
    overview = '\n\n────────────────────\n\n'.join(parts) if parts else ''
    return {'summary': overview, 'action_items': action_items}


def _extract_json_object(text: str) -> str:
    """Pull the first balanced {...} block from model output."""
    text = text.strip()
    if text.startswith('```'):
        start = text.find('{')
        end = text.rfind('}') + 1
        if start >= 0 and end > start:
            text = text[start:end]
    start = text.find('{')
    if start < 0:
        return text
    depth = 0
    for i in range(start, len(text)):
        if text[i] == '{':
            depth += 1
        elif text[i] == '}':
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return text[start:]


def _strip_invalid_json_controls(s: str) -> str:
    """Remove chars that break json.loads (unescaped controls inside LLM output)."""
    return ''.join(ch for ch in s if ord(ch) >= 32 or ch in '\n\r\t')


def _parse_overview_json(content: str) -> Optional[Dict[str, Any]]:
    """Try several strategies to parse Groq JSON."""
    candidates = [content.strip(), _extract_json_object(content)]
    for raw in candidates:
        if not raw:
            continue
        for attempt in (raw, _strip_invalid_json_controls(raw)):
            try:
                return json.loads(attempt)
            except json.JSONDecodeError:
                continue
    return None


def _normalize_parsed(parsed: Dict[str, Any]) -> Dict[str, Any]:
    summary = (parsed.get('summary') or '').strip()
    raw_items = parsed.get('action_items') or []
    action_items: List[Dict[str, str]] = []
    if isinstance(raw_items, list):
        for item in raw_items:
            if isinstance(item, dict):
                text = (item.get('text') or item.get('action') or '').strip()
                mt = (item.get('meeting_title') or item.get('source_meeting') or '').strip()
                if text:
                    action_items.append({'text': text, 'meeting_title': mt or 'General'})
            elif isinstance(item, str) and item.strip():
                action_items.append({'text': item.strip(), 'meeting_title': 'General'})
    return {'summary': summary, 'action_items': action_items}


def _repair_json_with_groq(api_key: str, broken_content: str, timeout: int) -> Optional[Dict[str, Any]]:
    """One short follow-up to coerce invalid JSON into valid JSON."""
    snippet = broken_content[:12000]
    repair_prompt = f"""The text below was meant to be valid JSON with keys "summary" (string) and "action_items" (array of objects with "text" and "meeting_title").
It may contain markdown, extra prose, or bad escaping. Return ONLY a single valid JSON object with those keys and nothing else.

---BEGIN---
{snippet}
---END---"""

    endpoint = 'https://api.groq.com/openai/v1/chat/completions'
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {api_key}',
    }
    payload = {
        'model': 'llama-3.3-70b-versatile',
        'messages': [
            {
                'role': 'system',
                'content': 'You output only valid JSON. No markdown fences, no commentary.',
            },
            {'role': 'user', 'content': repair_prompt},
        ],
        'temperature': 0.1,
        'max_tokens': 4096,
    }
    try:
        response = requests.post(endpoint, json=payload, headers=headers, timeout=timeout)
        response.raise_for_status()
        result = response.json()
        choices = result.get('choices') or []
        if not choices:
            return None
        content = (choices[0].get('message') or {}).get('content') or ''
        content = content.strip()
        parsed = _parse_overview_json(content)
        if parsed is None:
            return None
        return _normalize_parsed(parsed)
    except Exception as e:
        print(f'[Groq][folder_overview] Repair attempt failed: {e}')
        return None


def generate_folder_meetings_overview_with_groq(meetings_bundle: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    Args:
        meetings_bundle: each item has keys title, date_label, summary (str), action_items (list of str)

    Returns:
        {"summary": str, "action_items": [{"text": str, "meeting_title": str}]} or None only if GROQ_API_KEY missing
    """
    api_key = os.getenv('GROQ_API_KEY', '').strip()
    if not api_key:
        print('[Groq][folder_overview] GROQ_API_KEY not set')
        return None

    if not meetings_bundle:
        return {'summary': '', 'action_items': []}

    lines: List[str] = []
    for i, m in enumerate(meetings_bundle, start=1):
        title = m.get('title') or 'Untitled meeting'
        when = m.get('date_label') or ''
        summary = (m.get('summary') or '').strip() or '(No summary yet for this meeting.)'
        actions = m.get('action_items') or []
        action_block = '\n'.join(f'  - {a}' for a in actions[:25]) if actions else '  (none listed)'
        lines.append(
            f'### Meeting {i}: {title}\n'
            f'Date: {when}\n'
            f'Summary:\n{summary}\n'
            f'Action items from this meeting:\n{action_block}\n'
        )

    bundle_text = '\n'.join(lines)

    prompt = f"""You are an expert account manager assistant. Multiple meetings belong to the same client folder.

Below is structured data from each meeting (title, date, per-meeting summary, and per-meeting action items).

Your tasks:
1. Write ONE cohesive executive summary (2–6 short paragraphs) covering the whole relationship across these meetings: themes, decisions, progress, risks. Do not paste each meeting summary separately — synthesize.
2. Produce a merged list of action items: deduplicate near-duplicates, keep important specifics, and attribute each item to the most relevant meeting title in "meeting_title".

Respond with VALID JSON only (no markdown fences):
{{
  "summary": "single synthesized overview as plain text, paragraphs separated by blank lines if needed",
  "action_items": [
    {{"text": "clear action", "meeting_title": "Meeting title this relates to"}}
  ]
}}

Rules for JSON:
- Escape any double quotes inside string values as \\".
- Do not put raw line breaks inside JSON string values; use \\n instead.
- No trailing commas.

If there is almost no content, still return valid JSON with a brief summary explaining that detail is limited.

--- MEETING DATA ---
{bundle_text}"""

    endpoint = 'https://api.groq.com/openai/v1/chat/completions'
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {api_key}',
    }
    payload = {
        'model': 'llama-3.3-70b-versatile',
        'messages': [
            {
                'role': 'system',
                'content': (
                    'You synthesize multi-meeting client folders into one JSON object. '
                    'Output only valid JSON. Escape quotes and newlines inside strings.'
                ),
            },
            {'role': 'user', 'content': prompt},
        ],
        'temperature': 0.2,
        'max_tokens': 4096,
    }

    timeout = max(90, len(bundle_text) // 800)

    try:
        response = requests.post(endpoint, json=payload, headers=headers, timeout=timeout)
        response.raise_for_status()
        result = response.json()
        choices = result.get('choices') or []
        if not choices:
            print('[Groq][folder_overview] No choices in response; using fallback')
            return _fallback_from_bundle(meetings_bundle)

        content = (choices[0].get('message') or {}).get('content') or ''
        content = content.strip()

        parsed = _parse_overview_json(content)
        if parsed is not None:
            return _normalize_parsed(parsed)

        print('[Groq][folder_overview] JSON parse failed; attempting repair')
        repaired = _repair_json_with_groq(api_key, content, timeout=min(120, timeout + 30))
        if repaired is not None:
            return repaired

        print('[Groq][folder_overview] Repair failed; using deterministic fallback')
        return _fallback_from_bundle(meetings_bundle)

    except requests.exceptions.RequestException as e:
        print(f'[Groq][folder_overview] HTTP error: {e}')
        return _fallback_from_bundle(meetings_bundle)
    except Exception as e:
        print(f'[Groq][folder_overview] Error: {e}')
        import traceback
        traceback.print_exc()
        return _fallback_from_bundle(meetings_bundle)
