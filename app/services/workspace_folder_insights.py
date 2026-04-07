"""
Compute folder-level workspace insights: status, aggregated gaps, repeated themes, action rows.
Used by GET /api/folders/<folder_id>/workspace-insights
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from collections import defaultdict
from typing import Any, Dict, List, Set, Tuple

import requests

from app.models import CalendarEvent, MeetingTranscription


def _absent(val: Any) -> bool:
    if val is None:
        return True
    s = str(val).strip().lower()
    return s in ("", "null", "none", "n/a", "undefined")


def _action_text(item: Any) -> str:
    if isinstance(item, str):
        return item.strip()
    if isinstance(item, dict):
        t = item.get("text") or item.get("item") or item.get("action") or ""
        if isinstance(t, str) and t.strip():
            return t.strip()
    return ""


def _is_critical_gap(text: str) -> bool:
    t = (text or "").lower()
    return any(
        k in t
        for k in (
            "block",
            "blocked",
            "dependency",
            "mismatch",
            "contradiction",
            "risk",
            "critical",
        )
    )


def _norm_phrase(s: str) -> str:
    s = re.sub(r"[^\w\s]", " ", (s or "").lower())
    return " ".join(s.split())


def _signature(transcriptions: List[MeetingTranscription]) -> str:
    parts = []
    for t in sorted(transcriptions, key=lambda x: str(x.id)):
        ts = t.updated_at.isoformat() if t.updated_at else ""
        parts.append(f"{t.id}:{ts}")
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _gap_theme_icon_and_label(theme: str) -> Tuple[str, str]:
    """Map rough theme to icon."""
    t = theme.lower()
    if "owner" in t or "assign" in t:
        return "❌", "tasks_without_owners"
    if "deadline" in t or "timeline" in t or "date" in t:
        return "⚠️", "deadline_pressure"
    if "approval" in t or "sign off" in t or "signoff" in t:
        return "⚠️", "approval"
    if "depend" in t or "block" in t or "qt " in t or "review" in t:
        return "🔴", "dependency"
    return "⚠️", "general"


def _build_meeting_title_map(transcriptions: List[MeetingTranscription]) -> Dict[Any, str]:
    event_ids = list({t.calendar_event_id for t in transcriptions})
    events = {e.id: e for e in CalendarEvent.objects.filter(id__in=event_ids)}

    def title_for(t: MeetingTranscription) -> str:
        ev = events.get(t.calendar_event_id)
        return ((ev.title or "").strip() if ev else "") or "(No title)"

    return {t.id: title_for(t) for t in transcriptions}


def compute_workspace_folder_insights(transcriptions: List[MeetingTranscription]) -> Dict[str, Any]:
    """
    Returns JSON-serializable dict for the workspace-insights API.
    """
    if not transcriptions:
        return {
            "status": "on_track",
            "status_label": "🟢 On Track",
            "reasons": [],
            "gaps_across_meetings": [],
            "repeated_issues": [],
            "action_items": [],
            "short_summary_bullets": [],
            "meetings_count": 0,
            "source_signature": _signature([]),
        }

    titles = _build_meeting_title_map(transcriptions)
    sig = _signature(transcriptions)

    # --- Collect gaps & critical flags ---
    critical_any = False
    gaps_with_meeting: List[Tuple[str, str, str]] = []  # meeting_id, title, gap_text
    signals_with_meeting: List[Tuple[str, str, str]] = []

    for t in transcriptions:
        mid = str(t.id)
        mt = titles.get(t.id, "(No title)")
        raw_gaps = t.meeting_gaps or []
        if isinstance(raw_gaps, str):
            try:
                raw_gaps = json.loads(raw_gaps)
            except Exception:
                raw_gaps = []
        if not isinstance(raw_gaps, list):
            raw_gaps = []
        for g in raw_gaps:
            if not isinstance(g, str):
                continue
            g = g.strip()
            if not g:
                continue
            if _is_critical_gap(g):
                critical_any = True
            gaps_with_meeting.append((mid, mt, g))

        raw_sig = t.key_outcomes_signals or []
        if isinstance(raw_sig, str):
            try:
                raw_sig = json.loads(raw_sig)
            except Exception:
                raw_sig = []
        if not isinstance(raw_sig, list):
            raw_sig = []
        for s in raw_sig[:12]:
            if isinstance(s, str) and s.strip():
                signals_with_meeting.append((mid, mt, s.strip()))

    # --- Flatten actions with owner/deadline/blockers ---
    action_rows: List[Dict[str, Any]] = []
    missing_owner_count = 0
    missing_deadline_count = 0
    missing_owner_meetings: Set[str] = set()
    missing_deadline_meetings: Set[str] = set()

    for t in transcriptions:
        mid = str(t.id)
        mt = titles.get(t.id, "(No title)")
        items = t.action_items_list or []
        for it in items[:40]:
            text = _action_text(it)
            if not text:
                continue
            owner_raw = None
            deadline_raw = None
            blockers_raw = None
            clarity = None
            if isinstance(it, dict):
                owner_raw = it.get("owner") or it.get("speaker")
                deadline_raw = it.get("deadline")
                blockers_raw = it.get("blockers")
                clarity = it.get("clarity")

            owner_missing = _absent(owner_raw)
            deadline_missing = _absent(deadline_raw)
            if owner_missing:
                missing_owner_count += 1
                missing_owner_meetings.add(mid)
            if deadline_missing:
                missing_deadline_count += 1
                missing_deadline_meetings.add(mid)

            blocked = not _absent(blockers_raw)
            flags: List[str] = []
            if owner_missing:
                flags.append("assign_owner")
            if deadline_missing:
                flags.append("define_deadline")
            if blocked:
                flags.append("blocked")

            action_rows.append(
                {
                    "text": text,
                    "meeting_id": mid,
                    "meeting_title": mt,
                    "owner": None if owner_missing else str(owner_raw).strip(),
                    "owner_display": "Unassigned" if owner_missing else str(owner_raw).strip(),
                    "deadline": None if deadline_missing else str(deadline_raw).strip(),
                    "deadline_display": "No deadline" if deadline_missing else str(deadline_raw).strip(),
                    "blocked_by": None if not blocked else str(blockers_raw).strip(),
                    "flags": flags,
                    "clarity": clarity,
                    "_sort": (
                        0 if owner_missing else 1,
                        0 if deadline_missing else 1,
                        mt,
                        text[:80],
                    ),
                }
            )

    if critical_any:
        status = "at_risk"
        status_label = "🔴 At Risk"
    elif (missing_owner_count + missing_deadline_count) >= 2:
        status = "needs_attention"
        status_label = "🟡 Needs Attention"
    else:
        status = "on_track"
        status_label = "🟢 On Track"

    # --- Reasons (max 3) ---
    reasons: List[str] = []
    if critical_any:
        crit_sample = next((g for _, _, g in gaps_with_meeting if _is_critical_gap(g)), None)
        if crit_sample and len(crit_sample) > 90:
            crit_sample = crit_sample[:87] + "…"
        reasons.append(crit_sample or "Critical dependency or risk called out in meeting gaps.")
    if missing_owner_count >= 1 and len(reasons) < 4:
        reasons.append(
            f"{missing_owner_count} action item{'s' if missing_owner_count != 1 else ''} without an owner."
        )
    if missing_deadline_count >= 1 and len(reasons) < 4:
        reasons.append(
            f"{missing_deadline_count} action item{'s' if missing_deadline_count != 1 else ''} missing a deadline."
        )
    if not reasons and status != "on_track":
        reasons.append("Execution details still need tightening across meetings.")

    # --- Aggregated gaps (max 5), prioritized ---
    gap_lines: List[Dict[str, Any]] = []
    seen_keys: Set[str] = set()

    def add_line(icon: str, key: str, text: str) -> None:
        if key in seen_keys or len(gap_lines) >= 5:
            return
        seen_keys.add(key)
        gap_lines.append({"icon": icon, "text": text, "key": key})

    if missing_owner_count > 0:
        add_line(
            "❌",
            "no_owners",
            f"{missing_owner_count} task{'s' if missing_owner_count != 1 else ''} without owners",
        )
    if missing_deadline_count > 0:
        add_line(
            "⚠️",
            "no_deadlines",
            f"{missing_deadline_count} task{'s' if missing_deadline_count != 1 else ''} missing deadlines",
        )

    # Theme buckets from raw gap strings (not already covered)
    theme_counts: Dict[str, int] = defaultdict(int)
    theme_icon: Dict[str, str] = {}
    for _, _, g in gaps_with_meeting:
        icon, key = _gap_theme_icon_and_label(g)
        if key in ("tasks_without_owners",):
            continue
        theme_counts[key] += 1
        theme_icon[key] = icon

    for key, cnt in sorted(theme_counts.items(), key=lambda x: -x[1]):
        if len(gap_lines) >= 5:
            break
        if key in seen_keys:
            continue
        icon = theme_icon.get(key, "⚠️")
        # Human-readable line
        label_map = {
            "deadline_pressure": "Timeline / deadline clarity issues",
            "approval": "Approval or sign-off gaps",
            "dependency": "Unresolved dependencies or reviews",
            "general": "Open gaps called out in meetings",
        }
        base = label_map.get(key, "Themes from meeting gaps")
        if cnt > 1:
            txt = f"{base} ({cnt} mentions)"
        else:
            txt = base
        add_line(icon, f"theme_{key}", txt)

    # Fill from raw critical / unique gaps if room
    for _, _, g in gaps_with_meeting:
        if len(gap_lines) >= 5:
            break
        nk = _norm_phrase(g)[:48]
        if not nk or nk in seen_keys:
            continue
        ic = "🔴" if _is_critical_gap(g) else "⚠️"
        add_line(ic, nk, g if len(g) < 120 else g[:117] + "…")

    # --- Repeated issues (2+ meetings): cluster by normalized phrase ---
    phrase_meetings: Dict[str, Set[str]] = defaultdict(set)
    for mid, _, g in gaps_with_meeting:
        key = _norm_phrase(g)[:96]
        if len(key) < 14:
            continue
        phrase_meetings[key].add(mid)
    for mid, _, s in signals_with_meeting:
        key = _norm_phrase(s)[:96]
        if len(key) < 14:
            continue
        phrase_meetings[key].add(mid)

    repeated_issues: List[str] = []
    for key, mids in sorted(phrase_meetings.items(), key=lambda x: -len(x[1])):
        if len(mids) < 2:
            continue
        # Find shortest original text for display
        sample = key
        for mid, _, g in gaps_with_meeting:
            if _norm_phrase(g)[:96] == key and len(g) < 140:
                sample = g
                break
        repeated_issues.append(sample[:200])
        if len(repeated_issues) >= 4:
            break

    if len(repeated_issues) < 4:
        if len(missing_owner_meetings) >= 2 and "🔁 Tasks missing ownership across recent meetings" not in repeated_issues:
            repeated_issues.append("🔁 Tasks missing ownership across recent meetings")
        if len(missing_deadline_meetings) >= 2 and "🔁 Deadlines have not been defined despite being discussed multiple times" not in repeated_issues:
            repeated_issues.append("🔁 Deadlines have not been defined despite being discussed multiple times")

    dependency_repeat = sum(1 for _, _, g in gaps_with_meeting if _gap_theme_icon_and_label(g)[1] == "dependency")
    approval_repeat = sum(1 for _, _, g in gaps_with_meeting if _gap_theme_icon_and_label(g)[1] == "approval")
    deadline_theme_repeat = sum(1 for _, _, g in gaps_with_meeting if _gap_theme_icon_and_label(g)[1] == "deadline_pressure")

    if len(repeated_issues) < 4 and deadline_theme_repeat >= 2:
        repeated_issues.append("🔁 Timeline clarity issues across meetings")
    if len(repeated_issues) < 4 and approval_repeat >= 2:
        repeated_issues.append("🔁 Approval or dependency gaps recurring")
    if len(repeated_issues) < 4 and dependency_repeat >= 2 and "🔁 Approval or dependency gaps recurring" not in repeated_issues:
        repeated_issues.append("🔁 Approval or dependency gaps recurring")

    # --- Add insight sentence if there are signs of stalled execution ---
    repeated_count = len([r for r in repeated_issues if r.startswith("🔁")])
    if (critical_any or repeated_count >= 2 or (missing_owner_count + missing_deadline_count) >= 3) and status != "on_track":
        # Insert at beginning of reasons for visibility
        reasons.insert(0, "The project is showing signs of stalled execution, with key issues persisting across multiple meetings without resolution.")
    reasons = reasons[:3]

    action_rows.sort(key=lambda r: r["_sort"])
    for r in action_rows:
        r.pop("_sort", None)

    # --- Short summary bullets: Groq optional ---
    short_bullets = _short_summary_groq_or_fallback(
        status=status,
        reasons=reasons,
        gap_lines=gap_lines,
        repeated_issues=repeated_issues,
        critical_any=critical_any,
    )
    
    # Add progress/execution line if needed
    attention_count = len([r for r in action_rows if r["flags"]])
    if attention_count >= 3 or len(repeated_issues) >= 2:
        progress_line = f"Progress: No meaningful progress across last {len(transcriptions)} meetings"
        if progress_line not in short_bullets:
            short_bullets.insert(0, progress_line)

    return {
        "status": status,
        "status_label": status_label,
        "reasons": reasons,
        "gaps_across_meetings": gap_lines[:5],
        "repeated_issues": repeated_issues[:4],
        "action_items": action_rows,
        "short_summary_bullets": short_bullets[:4],
        "meetings_count": len(transcriptions),
        "source_signature": sig,
    }


def _short_summary_groq_or_fallback(
    *,
    status: str,
    reasons: List[str],
    gap_lines: List[Dict[str, Any]],
    repeated_issues: List[str],
    critical_any: bool,
) -> List[str]:
    api_key = (os.getenv("GROQ_API_KEY") or "").strip()
    context_bits = [
        f"Overall status: {status}",
        "Top reasons: " + "; ".join(reasons[:3]),
        "Aggregated gap themes: " + "; ".join(g.get("text", "") for g in gap_lines[:4]),
        "Cross-meeting patterns: " + "; ".join(repeated_issues[:3]),
    ]
    bundle = "\n".join(context_bits)

    if api_key:
        prompt = f"""Based ONLY on this workspace snapshot, write 3-4 VERY short bullet lines (max 18 words each) for an executive.
Rules:
- High-level only; do NOT copy phrases verbatim from the inputs.
- Do not repeat the same idea as the gap list or repeated-issues list; add perspective (impact, priority).
- No paragraphs; one bullet per line in the JSON array.
- Return VALID JSON only: {{"bullets": ["...", "..."]}}

--- SNAPSHOT ---
{bundle}
"""

        try:
            endpoint = "https://api.groq.com/openai/v1/chat/completions"
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            }
            payload = {
                "model": "llama-3.3-70b-versatile",
                "messages": [
                    {
                        "role": "system",
                        "content": "You output only valid JSON with a bullets array.",
                    },
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.15,
                "max_tokens": 512,
            }
            r = requests.post(endpoint, json=payload, headers=headers, timeout=45)
            r.raise_for_status()
            content = (
                ((r.json().get("choices") or [{}])[0].get("message") or {}).get("content") or ""
            ).strip()
            m = re.search(r"\{[\s\S]*\}", content)
            if m:
                parsed = json.loads(m.group(0))
                arr = parsed.get("bullets")
                if isinstance(arr, list):
                    out = [str(x).strip() for x in arr if str(x).strip()]
                    if out:
                        return out[:4]
        except Exception as e:
            print(f"[workspace_insights] Groq short summary failed: {e}")

    # Deterministic fallback
    fb: List[str] = []
    if status == "at_risk":
        fb.append("Folder health is constrained by critical gaps or dependencies.")
    elif status == "needs_attention":
        fb.append("Several follow-ups still need owners or dates across meetings.")
    else:
        fb.append("Workstreams look aligned; keep monitoring commitments and dates.")
    if repeated_issues and len(fb) < 4:
        fb.append("Recurring themes suggest fixing root causes, not just individual tasks.")
    if critical_any and len(fb) < 4:
        fb.append("Unresolved risk items should get explicit owners and dates.")
    return fb[:4]
