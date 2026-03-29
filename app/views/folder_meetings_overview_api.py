"""
GET /api/folders/<folder_id>/meetings-overview?userId=...
Returns LLM-synthesized single summary + merged action items for all transcriptions in the folder.
Cached until any included transcription's updated_at changes.
"""
import hashlib
import uuid as uuid_lib
from typing import Any, Dict, List

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from app.models import CalendarEvent, FolderMeetingsOverview, MeetingTranscription
from app.views.calendar_api import add_cors_headers, get_backend_user_id_from_request
from app.services.groq.folder_overview_generator import generate_folder_meetings_overview_with_groq


def _action_item_to_text(item: Any) -> str:
    if isinstance(item, str):
        return item.strip()
    if isinstance(item, dict):
        text = item.get('text') or item.get('item') or item.get('action') or ''
        if isinstance(text, str) and text.strip():
            return text.strip()
    return ''


def _compute_source_signature(transcriptions: List[MeetingTranscription]) -> str:
    parts = []
    for t in sorted(transcriptions, key=lambda x: str(x.id)):
        ts = t.updated_at.isoformat() if t.updated_at else ''
        parts.append(f'{t.id}:{ts}')
    raw = '|'.join(parts)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def _build_bundle(transcriptions: List[MeetingTranscription]) -> List[Dict[str, Any]]:
    event_ids = list({t.calendar_event_id for t in transcriptions})
    events = {e.id: e for e in CalendarEvent.objects.filter(id__in=event_ids)}

    # Newest first for human context in prompt
    ordered = sorted(
        transcriptions,
        key=lambda x: x.created_at or x.updated_at,
        reverse=True,
    )
    bundle: List[Dict[str, Any]] = []
    for t in ordered:
        event = events.get(t.calendar_event_id)
        title = ((event.title or '').strip() if event else '') or '(No title)'
        when = ''
        if event and event.start_time:
            when = event.start_time.isoformat()
        elif t.created_at:
            when = t.created_at.isoformat()

        summary = (t.summary or '').strip()
        if len(summary) > 6000:
            summary = summary[:6000] + '…'

        items = t.action_items_list or []
        action_strs: List[str] = []
        for it in items[:30]:
            s = _action_item_to_text(it)
            if s:
                action_strs.append(s)

        bundle.append({
            'title': title,
            'date_label': when,
            'summary': summary,
            'action_items': action_strs,
        })
    return bundle


@require_http_methods(['GET', 'OPTIONS'])
@csrf_exempt
def api_folder_meetings_overview(request, folder_id):
    if request.method == 'OPTIONS':
        return add_cors_headers(JsonResponse({}), request)

    backend_user_id = get_backend_user_id_from_request(request)
    if not backend_user_id:
        r = JsonResponse(
            {'error': 'Authentication required. Provide JWT token or userId parameter'},
            status=400,
        )
        return add_cors_headers(r, request)

    try:
        user_uuid = uuid_lib.UUID(str(backend_user_id))
        folder_uuid = uuid_lib.UUID(str(folder_id))
    except (ValueError, AttributeError):
        r = JsonResponse({'error': 'Invalid userId or folder id'}, status=400)
        return add_cors_headers(r, request)

    force_refresh = request.GET.get('refresh') in ('1', 'true', 'yes')

    try:
        transcriptions = list(
            MeetingTranscription.objects.filter(
                backend_user_id=user_uuid,
                folder_id=folder_uuid,
            )
        )
    except Exception as e:
        r = JsonResponse({'error': str(e)}, status=500)
        return add_cors_headers(r, request)

    sig = _compute_source_signature(transcriptions)

    if not force_refresh and transcriptions:
        try:
            cached = FolderMeetingsOverview.objects.get(
                folder_id=folder_uuid,
                backend_user_id=user_uuid,
            )
            if cached.source_signature == sig:
                r = JsonResponse({
                    'summary': cached.summary or '',
                    'action_items': cached.action_items or [],
                    'meetings_count': len(transcriptions),
                    'cached': True,
                    'source_signature': sig,
                })
                return add_cors_headers(r, request)
        except FolderMeetingsOverview.DoesNotExist:
            pass

    if not transcriptions:
        r = JsonResponse({
            'summary': '',
            'action_items': [],
            'meetings_count': 0,
            'cached': False,
            'source_signature': sig,
        })
        return add_cors_headers(r, request)

    bundle = _build_bundle(transcriptions)
    groq_result = generate_folder_meetings_overview_with_groq(bundle)

    if groq_result is None:
        r = JsonResponse(
            {
                'error': 'Unable to generate overview. Check GROQ_API_KEY and try again.',
                'meetings_count': len(transcriptions),
            },
            status=502,
        )
        return add_cors_headers(r, request)

    summary = groq_result.get('summary') or ''
    action_items = groq_result.get('action_items') or []

    FolderMeetingsOverview.objects.update_or_create(
        folder_id=folder_uuid,
        backend_user_id=user_uuid,
        defaults={
            'source_signature': sig,
            'summary': summary,
            'action_items': action_items,
        },
    )

    r = JsonResponse({
        'summary': summary,
        'action_items': action_items,
        'meetings_count': len(transcriptions),
        'cached': False,
        'source_signature': sig,
    })
    return add_cors_headers(r, request)
