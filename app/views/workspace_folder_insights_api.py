"""
GET /api/folders/<folder_id>/workspace-insights?userId=...
Folder-level status, aggregated gaps, repeated themes, action rows (server-side).
"""
import uuid as uuid_lib

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from app.models import MeetingTranscription
from app.services.workspace_folder_insights import compute_workspace_folder_insights
from app.views.calendar_api import add_cors_headers, get_backend_user_id_from_request


@require_http_methods(["GET", "OPTIONS"])
@csrf_exempt
def api_folder_workspace_insights(request, folder_id):
    if request.method == "OPTIONS":
        return add_cors_headers(JsonResponse({}), request)

    backend_user_id = get_backend_user_id_from_request(request)
    if not backend_user_id:
        r = JsonResponse(
            {"error": "Authentication required. Provide JWT token or userId parameter"},
            status=400,
        )
        return add_cors_headers(r, request)

    try:
        user_uuid = uuid_lib.UUID(str(backend_user_id))
        folder_uuid = uuid_lib.UUID(str(folder_id))
    except (ValueError, AttributeError):
        r = JsonResponse({"error": "Invalid userId or folder id"}, status=400)
        return add_cors_headers(r, request)

    try:
        transcriptions = list(
            MeetingTranscription.objects.filter(
                backend_user_id=user_uuid,
                folder_id=folder_uuid,
            )
        )
    except Exception as e:
        r = JsonResponse({"error": str(e)}, status=500)
        return add_cors_headers(r, request)

    payload = compute_workspace_folder_insights(transcriptions)
    r = JsonResponse(payload)
    return add_cors_headers(r, request)
