"""
API endpoints for notifications.
"""
import json
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from app.models import Notification
from app.views.calendar_api import add_cors_headers, get_backend_user_id_from_request
from django.utils import timezone


@require_http_methods(["GET", "OPTIONS"])
@csrf_exempt
def api_get_notifications(request):
    """
    Get all notifications for the authenticated user.
    """
    if request.method == 'OPTIONS':
        response = JsonResponse({})
        return add_cors_headers(response, request)
    
    try:
        backend_user_id = get_backend_user_id_from_request(request)
        if not backend_user_id:
            response = JsonResponse({'error': 'Authentication required'}, status=401)
            return add_cors_headers(response, request)
        
        # Get query parameters
        read_only = request.GET.get('read_only', '').lower() == 'true'
        unread_only = request.GET.get('unread_only', '').lower() == 'true'
        
        # Build query
        notifications_query = Notification.objects.filter(backend_user_id=backend_user_id)
        
        if read_only:
            notifications_query = notifications_query.filter(read=True)
        elif unread_only:
            notifications_query = notifications_query.filter(read=False)
        
        notifications = notifications_query.order_by('-created_at')[:100]  # Limit to 100 most recent
        
        result = []
        for notification in notifications:
            result.append({
                'id': str(notification.id),
                'type': notification.notification_type,
                'meeting_id': str(notification.meeting_id) if notification.meeting_id else None,
                'meeting_title': notification.meeting_title,
                'message': notification.message,
                'read': notification.read,
                'read_at': notification.read_at.isoformat() if notification.read_at else None,
                'timestamp': notification.created_at.isoformat(),
                'created_at': notification.created_at.isoformat(),
            })
        
        response = JsonResponse({
            'results': result,
            'count': len(result),
        })
        return add_cors_headers(response, request)
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        response = JsonResponse({'error': str(e)}, status=500)
        return add_cors_headers(response, request)


@require_http_methods(["POST", "OPTIONS"])
@csrf_exempt
def api_mark_notification_read(request, notification_id):
    """
    Mark a notification as read.
    """
    if request.method == 'OPTIONS':
        response = JsonResponse({})
        return add_cors_headers(response, request)
    
    try:
        backend_user_id = get_backend_user_id_from_request(request)
        if not backend_user_id:
            response = JsonResponse({'error': 'Authentication required'}, status=401)
            return add_cors_headers(response, request)
        
        try:
            notification = Notification.objects.get(id=notification_id, backend_user_id=backend_user_id)
        except Notification.DoesNotExist:
            response = JsonResponse({'error': 'Notification not found'}, status=404)
            return add_cors_headers(response, request)
        
        # Mark as read
        notification.read = True
        notification.read_at = timezone.now()
        notification.save(update_fields=['read', 'read_at', 'updated_at'])
        
        response = JsonResponse({
            'success': True,
            'message': 'Notification marked as read',
        })
        return add_cors_headers(response, request)
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        response = JsonResponse({'error': str(e)}, status=500)
        return add_cors_headers(response, request)


@require_http_methods(["POST", "OPTIONS"])
@csrf_exempt
def api_mark_all_notifications_read(request):
    """
    Mark all notifications as read for the authenticated user.
    """
    if request.method == 'OPTIONS':
        response = JsonResponse({})
        return add_cors_headers(response, request)
    
    try:
        backend_user_id = get_backend_user_id_from_request(request)
        if not backend_user_id:
            response = JsonResponse({'error': 'Authentication required'}, status=401)
            return add_cors_headers(response, request)
        
        # Mark all unread notifications as read
        updated_count = Notification.objects.filter(
            backend_user_id=backend_user_id,
            read=False
        ).update(
            read=True,
            read_at=timezone.now()
        )
        
        response = JsonResponse({
            'success': True,
            'message': f'Marked {updated_count} notification(s) as read',
            'count': updated_count,
        })
        return add_cors_headers(response, request)
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        response = JsonResponse({'error': str(e)}, status=500)
        return add_cors_headers(response, request)


@require_http_methods(["DELETE", "OPTIONS"])
@csrf_exempt
def api_delete_notification(request, notification_id):
    """
    Delete a notification (removes from DB).
    """
    if request.method == 'OPTIONS':
        response = JsonResponse({})
        return add_cors_headers(response, request)
    
    try:
        backend_user_id = get_backend_user_id_from_request(request)
        if not backend_user_id:
            response = JsonResponse({'error': 'Authentication required'}, status=401)
            return add_cors_headers(response, request)
        
        try:
            notification = Notification.objects.get(id=notification_id, backend_user_id=backend_user_id)
        except Notification.DoesNotExist:
            response = JsonResponse({'error': 'Notification not found'}, status=404)
            return add_cors_headers(response, request)
        
        # Delete the notification
        notification.delete()
        
        response = JsonResponse({
            'success': True,
            'message': 'Notification deleted',
        })
        return add_cors_headers(response, request)
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        response = JsonResponse({'error': str(e)}, status=500)
        return add_cors_headers(response, request)

