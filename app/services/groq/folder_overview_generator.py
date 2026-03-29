"""
Synthesize a single folder-level summary and merged action items from multiple meetings (Groq).
"""
import json
import os
from typing import Any, Dict, List, Optional

import requests


def generate_folder_meetings_overview_with_groq(meetings_bundle: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    Args:
        meetings_bundle: each item has keys title, date_label, summary (str), action_items (list of str)

    Returns:
        {"summary": str, "action_items": [{"text": str, "meeting_title": str}]} or None
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
                'content': 'You synthesize multi-meeting client folders into one JSON object. Output only valid JSON.',
            },
            {'role': 'user', 'content': prompt},
        ],
        'temperature': 0.25,
        'max_tokens': 4096,
    }

    try:
        timeout = max(90, len(bundle_text) // 800)
        response = requests.post(endpoint, json=payload, headers=headers, timeout=timeout)
        response.raise_for_status()
        result = response.json()
        choices = result.get('choices') or []
        if not choices:
            return None
        content = (choices[0].get('message') or {}).get('content') or ''
        content = content.strip()
        if content.startswith('```'):
            start = content.find('{')
            end = content.rfind('}') + 1
            if start >= 0 and end > start:
                content = content[start:end]
        parsed = json.loads(content)
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
    except Exception as e:
        print(f'[Groq][folder_overview] Error: {e}')
        import traceback
        traceback.print_exc()
        return None
