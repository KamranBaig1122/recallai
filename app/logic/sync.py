"""
Calendar events sync logic
Similar to calendar-integration-demo/v2-demo/worker/processors/recall-calendar-sync-events.js
"""
from datetime import datetime, timedelta
from app.models import Calendar, CalendarEvent
from app.services.recall.service import get_service
import traceback
import os
import requests


def _get_workspace_id_from_email(email: str, backend_user_id: str) -> str | None:
    """
    Get workspace_id from user's email domain by calling Invite-ellie-backend API.
    Returns None if workspace cannot be determined.
    """
    try:
        api_base_url = os.environ.get('INVITE_ELLIE_BACKEND_API_URL', 'http://localhost:8000')
        if not api_base_url:
            print(f'[sync] ⚠ INVITE_ELLIE_BACKEND_API_URL not set, cannot get workspace_id')
            return None
        
        # Extract domain from email
        domain = email.split('@')[-1] if '@' in email else None
        if not domain:
            return None
        
        # Determine workspace name from domain
        personal_domains = ['gmail.com', 'outlook.com', 'hotmail.com', 'yahoo.com']
        if domain.lower() in personal_domains:
            workspace_name = 'Personal'
        else:
            # Use domain name as workspace name (capitalize first letter)
            workspace_name = domain.split('.')[0].capitalize()
        
        # Get user's workspaces from Invite-ellie-backend
        from app.logic.backend_auth import get_backend_api_headers
        api_url = f'{api_base_url}/api/workspaces/'
        headers = get_backend_api_headers({
            'X-User-ID': backend_user_id,  # Still include X-User-ID for user context
        })
        
        response = requests.get(api_url, headers=headers, timeout=5)
        if response.status_code == 200:
            workspaces = response.json()
            # Find workspace by name (case-insensitive)
            for workspace in workspaces.get('results', []):
                if workspace.get('name', '').lower() == workspace_name.lower():
                    return workspace.get('id')
        
        print(f'[sync] ⚠ Could not find workspace "{workspace_name}" for user {backend_user_id}')
        return None
    except Exception as e:
        print(f'[sync] ⚠ Error getting workspace_id from email: {e}')
        return None


def sync_calendar_events(calendar, last_updated_timestamp=None):
    """
    Sync calendar events from Recall API.
    
    Per Recall AI documentation:
    - Fetch events via List Calendar Events endpoint
    - Set updated_at__gte to last_updated_ts from webhook (if provided)
    - Use is_deleted field to determine if event was removed
    - Note: Recall doesn't delete events from their system, only marks as deleted
    
    Similar to recall-calendar-sync-events.js processor
    """
    recall_service = get_service()
    
    # If no timestamp provided, sync ALL events (no filter)
    # This is useful for manual syncs or initial syncs
    # For webhook-triggered syncs, timestamp will be provided
    if not last_updated_timestamp:
        last_updated_timestamp = None  # Sync all events
    
    if last_updated_timestamp:
        print(f'INFO: Sync events for calendar {calendar.id}(recall_id: {calendar.recall_id}) since {last_updated_timestamp}')
    else:
        print(f'INFO: Sync ALL events for calendar {calendar.id}(recall_id: {calendar.recall_id})')
    
    try:
        # Fetch events from Recall API (with pagination)
        events = recall_service.fetch_calendar_events(
            calendar_id=calendar.recall_id,
            last_updated_timestamp=last_updated_timestamp
        )
        
        print(f'INFO: Fetched {len(events) if events else 0} events from Recall API for calendar {calendar.id}')
        
        if not events:
            print(f'INFO: No events found for calendar {calendar.id}')
            return {
                'success': True,
                'upserted': 0,
                'deleted': 0,
                'total': 0
            }
        
        events_upserted = []
        events_deleted = []
        
        for event in events:
            try:
                if event.get('is_deleted'):
                    # Event was deleted from calendar in Recall.ai
                    # IMPORTANT: DO NOT delete CalendarEvent from local database
                    # CalendarEvents contain meeting data (transcriptions, summaries, action items)
                    # that must be preserved even when calendar is disconnected
                    # We keep the event in the database so users can still access their meeting history
                    print(f'INFO: Event {event.get("id")} marked as deleted in Recall.ai, but preserving in local database to maintain meeting data')
                    
                    # Delete scheduled bots for this event
                    try:
                        event_obj = CalendarEvent.objects.filter(recall_id=event.get('id')).first()
                        if event_obj:
                            bots = event_obj.bots
                            if bots and len(bots) > 0:
                                from django.utils import timezone
                                from app.models import BotRecording
                                
                                deleted_bots = []
                                for bot in bots:
                                    bot_id = bot.get('bot_id') or bot.get('id')
                                    if not bot_id:
                                        continue
                                    
                                    # Only delete scheduled bots that haven't joined yet
                                    bot_status = bot.get('status', '').lower()
                                    join_at = bot.get('join_at')
                                    
                                    # Check if bot is scheduled (has join_at in future) or hasn't joined yet
                                    should_delete = False
                                    if join_at:
                                        try:
                                            join_time = datetime.fromisoformat(join_at.replace('Z', '+00:00'))
                                            if timezone.is_naive(join_time):
                                                join_time = timezone.make_aware(join_time)
                                            # Delete if join time is in the future (scheduled bot)
                                            if join_time > timezone.now():
                                                should_delete = True
                                        except:
                                            # If we can't parse join_at, check status
                                            if bot_status in ['pending', 'scheduled', 'waiting']:
                                                should_delete = True
                                    elif bot_status in ['pending', 'scheduled', 'waiting']:
                                        # No join_at but status indicates it's scheduled
                                        should_delete = True
                                    
                                    if should_delete:
                                        try:
                                            # Delete bot from Recall.ai
                                            recall_service.delete_bot(bot_id)
                                            print(f'INFO: ✓ Deleted scheduled bot {bot_id} from Recall.ai for deleted event {event.get("id")}')
                                            deleted_bots.append(bot_id)
                                            
                                            # Delete BotRecording if it exists (only for scheduled bots)
                                            BotRecording.objects.filter(bot_id=bot_id).delete()
                                            print(f'INFO: ✓ Deleted BotRecording for bot {bot_id}')
                                        except Exception as delete_error:
                                            # If bot deletion fails (e.g., bot already joined), log and continue
                                            print(f'WARNING: Could not delete bot {bot_id} from Recall.ai: {delete_error}')
                                            # Check if bot has already joined - if so, don't delete BotRecording
                                            try:
                                                bot_data = recall_service.get_bot(bot_id)
                                                bot_status_from_api = bot_data.get('status', '').lower()
                                                if bot_status_from_api in ['joined', 'recording', 'done', 'completed']:
                                                    print(f'INFO: Bot {bot_id} has already joined, preserving BotRecording')
                                                else:
                                                    # Bot is still scheduled, try to delete BotRecording
                                                    BotRecording.objects.filter(bot_id=bot_id).delete()
                                            except:
                                                # If we can't check bot status, preserve BotRecording to be safe
                                                pass
                                    
                                # Remove deleted bots from recall_data
                                if deleted_bots:
                                    recall_data = event_obj.recall_data.copy()
                                    bots_list = recall_data.get('bots', [])
                                    # Filter out deleted bots
                                    updated_bots = [
                                        bot for bot in bots_list
                                        if (bot.get('bot_id') or bot.get('id')) not in deleted_bots
                                    ]
                                    recall_data['bots'] = updated_bots
                                    event_obj.recall_data = recall_data
                                    event_obj.save()
                                    print(f'INFO: ✓ Removed {len(deleted_bots)} bot(s) from CalendarEvent {event_obj.id} recall_data')
                                    
                                    # Broadcast WebSocket update immediately after bot deletion
                                    try:
                                        from channels.layers import get_channel_layer
                                        from asgiref.sync import async_to_sync
                                        channel_layer = get_channel_layer()
                                        if channel_layer:
                                            group_name = f'calendar_updates_{calendar.user_id}'
                                            async_to_sync(channel_layer.group_send)(
                                                group_name,
                                                {
                                                    'type': 'calendar_update',
                                                    'message': {
                                                        'calendar_id': str(calendar.id),
                                                        'event': 'bots_deleted',
                                                        'event_id': str(event_obj.id),
                                                        'deleted_bot_ids': deleted_bots,
                                                        'timestamp': datetime.now().isoformat(),
                                                    }
                                                }
                                            )
                                            print(f'INFO: Broadcasted bot deletion to WebSocket group {group_name}')
                                    except Exception as ws_error:
                                        print(f'WARNING: Failed to broadcast WebSocket update for bot deletion: {ws_error}')
                                        import traceback
                                        traceback.print_exc()
                    except Exception as bot_delete_error:
                        print(f'WARNING: Error deleting bots for deleted event {event.get("id")}: {bot_delete_error}')
                        import traceback
                        traceback.print_exc()
                    
                    # Don't add to events_deleted - we're preserving it
                else:
                    # Create or update event
                    event_obj, created = CalendarEvent.objects.update_or_create(
                        recall_id=event['id'],
                        calendar_id=calendar.id,
                        defaults={
                            'platform': event.get('platform', calendar.platform),
                            'recall_data': event,
                            'should_record_automatic': False,  # Will be updated later
                            'should_record_manual': None,
                            'backend_user_id': calendar.backend_user_id,  # Set backend_user_id from calendar
                        }
                    )
                    events_upserted.append(event)
                    action = 'Created' if created else 'Updated'
                    print(f'INFO: {action} event {event.get("id")} ({event.get("title", "No title")}) for calendar {calendar.id}')
                    
                    # Automatically create bot for events with meeting URLs
                    if event_obj.meeting_url and event_obj.start_time:
                        from django.utils import timezone
                        from app.logic.bot_creator import create_bot_for_event
                        
                        # Only create bot if event is in the future
                        start_time = event_obj.start_time
                        if timezone.is_naive(start_time):
                            start_time = timezone.make_aware(start_time)
                        
                        if start_time > timezone.now():
                            # Check if bot already exists
                            bots = event_obj.bots
                            if not bots or len(bots) == 0:
                                try:
                                    # Use calendar's default workspace_id and folder_id if set
                                    workspace_id = calendar.default_workspace_id
                                    folder_id = calendar.default_folder_id
                                    
                                    # Fallback: Get workspace_id from calendar email domain if not set on calendar
                                    if not workspace_id and calendar.email and event_obj.backend_user_id:
                                        workspace_id = _get_workspace_id_from_email(calendar.email, str(event_obj.backend_user_id))
                                    
                                    result = create_bot_for_event(event_obj, workspace_id=str(workspace_id) if workspace_id else None, folder_id=str(folder_id) if folder_id else None)
                                    if result['success']:
                                        print(f'INFO: ✓ Created bot {result["bot_id"]} for event {event_obj.id} (will join at {result["join_at"]})')
                                        # Previous meeting email is sent automatically by create_bot_for_event
                                    else:
                                        print(f'WARNING: Failed to create bot for event {event_obj.id}: {result.get("error")}')
                                except Exception as bot_error:
                                    print(f'WARNING: Error creating bot for event {event_obj.id}: {bot_error}')
                            else:
                                print(f'INFO: Event {event_obj.id} already has {len(bots)} bot(s), skipping bot creation')
                        else:
                            print(f'INFO: Event {event_obj.id} start time is in the past, skipping bot creation')
            except Exception as e:
                print(f'ERROR: Failed to process event {event.get("id", "unknown")}: {e}')
                traceback.print_exc()
                continue
        
        print(f'INFO: Synced (upsert: {len(events_upserted)}, delete: {len(events_deleted)}) calendar events for calendar({calendar.id})')
        
        # Close database connection to free up pool for Supabase Session Pooler
        try:
            from django.db import connections
            connections['default'].close()
        except:
            pass
        
        return {
            'success': True,
            'upserted': len(events_upserted),
            'deleted': len(events_deleted),
            'total': len(events)
        }
    except Exception as e:
        error_msg = str(e)
        print(f'ERROR: Error syncing events for calendar {calendar.id}: {error_msg}')
        traceback.print_exc()
        
        # Close connection even on error
        try:
            from django.db import connections
            connections['default'].close()
        except:
            pass
        
        return {
            'success': False,
            'error': error_msg
        }

