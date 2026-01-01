"""
Notification handler for unresolved meetings.

This module handles sending notifications (in-app and email) for meetings
that remain unresolved after a configurable time threshold.
"""
import os
import logging
from datetime import timedelta
from django.utils import timezone
from django.conf import settings
from app.models import MeetingTranscription, Notification
from app.services.email_service import send_unresolved_meeting_email
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

logger = logging.getLogger(__name__)


def handle_unresolved_meeting_notification(meeting_transcription: MeetingTranscription):
    """
    Handle notification for an unresolved meeting.
    
    This function:
    1. Checks if notification already sent (prevent duplicates)
    2. Sends in-app notification (via WebSocket)
    3. Sends email notification (if enabled)
    4. Updates notification tracking fields
    
    Args:
        meeting_transcription: MeetingTranscription instance that is unresolved
    """
    # Check if notification already sent
    if meeting_transcription.notification_sent_at:
        logger.info(f'[Notification] Notification already sent for meeting {meeting_transcription.id} at {meeting_transcription.notification_sent_at}')
        return
    
    if not meeting_transcription.backend_user_id:
        logger.warning(f'[Notification] Cannot send notification for meeting {meeting_transcription.id}: no backend_user_id')
        return
    
    try:
        notification_types = []
        
        # Send in-app notification
        if settings.ENABLE_IN_APP_NOTIFICATIONS:
            try:
                send_in_app_notification(meeting_transcription)
                notification_types.append('in_app')
                logger.info(f'[Notification] Sent in-app notification for meeting {meeting_transcription.id}')
            except Exception as e:
                logger.error(f'[Notification] Failed to send in-app notification for meeting {meeting_transcription.id}: {e}')
        
        # Send email notification
        if settings.ENABLE_EMAIL_NOTIFICATIONS:
            try:
                # Check if email follow-up delay is configured
                email_delay_minutes = settings.UNRESOLVED_MEETING_EMAIL_FOLLOW_UP_DELAY_MINUTES
                if email_delay_minutes > 0:
                    # Calculate if enough time has passed for email
                    threshold_time = meeting_transcription.updated_at + timedelta(
                        minutes=settings.UNRESOLVED_MEETING_NOTIFICATION_THRESHOLD_MINUTES
                    )
                    email_time = threshold_time + timedelta(minutes=email_delay_minutes)
                    if timezone.now() < email_time:
                        logger.info(f'[Notification] Email delay not yet reached for meeting {meeting_transcription.id}')
                    else:
                        send_unresolved_meeting_email(meeting_transcription)
                        notification_types.append('email')
                        logger.info(f'[Notification] Sent email notification for meeting {meeting_transcription.id}')
                else:
                    # Send email immediately (same time as in-app)
                    send_unresolved_meeting_email(meeting_transcription)
                    notification_types.append('email')
                    logger.info(f'[Notification] Sent email notification for meeting {meeting_transcription.id}')
            except Exception as e:
                logger.error(f'[Notification] Failed to send email notification for meeting {meeting_transcription.id}: {e}')
        
        # Update notification tracking
        if notification_types:
            meeting_transcription.notification_sent_at = timezone.now()
            meeting_transcription.notification_type = ','.join(notification_types)
            meeting_transcription.save(update_fields=['notification_sent_at', 'notification_type'])
            logger.info(f'[Notification] Successfully sent notifications ({", ".join(notification_types)}) for meeting {meeting_transcription.id}')
        else:
            logger.warning(f'[Notification] No notifications sent for meeting {meeting_transcription.id} (all failed or disabled)')
            
    except Exception as e:
        logger.error(f'[Notification] Error handling notification for meeting {meeting_transcription.id}: {e}')
        # Increment retry count
        meeting_transcription.notification_retry_count += 1
        meeting_transcription.save(update_fields=['notification_retry_count'])


def send_in_app_notification(meeting_transcription: MeetingTranscription):
    """
    Send in-app notification via WebSocket.
    
    Args:
        meeting_transcription: MeetingTranscription instance
    """
    try:
        channel_layer = get_channel_layer()
        if not channel_layer:
            logger.warning('[Notification] Channel layer not configured, cannot send in-app notification')
            return
        
        user_id = str(meeting_transcription.backend_user_id)
        group_name = f'notifications_{user_id}'
        
        # Get meeting title from CalendarEvent
        meeting_title = 'Untitled Meeting'
        try:
            from app.models import CalendarEvent
            try:
                event = CalendarEvent.objects.get(id=meeting_transcription.calendar_event_id)
                if event.title:
                    meeting_title = event.title
            except CalendarEvent.DoesNotExist:
                logger.debug(f'[Notification] CalendarEvent not found for meeting {meeting_transcription.id}, using default title')
        except Exception as e:
            logger.warning(f'[Notification] Error getting meeting title: {e}')
        
        # Create notification in database
        notification = Notification.objects.create(
            backend_user_id=meeting_transcription.backend_user_id,
            notification_type='unresolved_meeting_notification',
            meeting_id=meeting_transcription.id,
            meeting_title=meeting_title,
            message=f'Meeting "{meeting_title}" is unresolved and needs folder assignment',
            read=False,
        )
        logger.info(f'[Notification] Created notification {notification.id} in database for meeting {meeting_transcription.id}')
        
        # Send notification via WebSocket
        message = {
            'type': 'unresolved_meeting_notification',
            'id': str(notification.id),
            'meeting_id': str(meeting_transcription.id),
            'meeting_title': meeting_title,
            'message': f'Meeting "{meeting_title}" is unresolved and needs folder assignment',
            'timestamp': timezone.now().isoformat(),
        }
        
        async_to_sync(channel_layer.group_send)(
            group_name,
            {
                'type': 'send_notification',
                'message': message
            }
        )
        logger.info(f'[Notification] Sent in-app notification to group {group_name} for meeting "{meeting_title}" (ID: {meeting_transcription.id})')
    except Exception as e:
        logger.error(f'[Notification] Error sending in-app notification: {e}', exc_info=True)
        # Don't raise - allow email notification to still be sent

