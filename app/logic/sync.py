"""
Calendar events sync logic
Similar to calendar-integration-demo/v2-demo/worker/processors/recall-calendar-sync-events.js
"""
from datetime import datetime, timedelta
from app.models import Calendar, CalendarEvent
from app.services.recall.service import get_service
import traceback


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
                                    result = create_bot_for_event(event_obj)
                                    if result['success']:
                                        print(f'INFO: ✓ Created bot {result["bot_id"]} for event {event_obj.id} (will join at {result["join_at"]})')
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

