from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from app.models import Calendar, CalendarWebhook
from app.services.recall.service import get_service
from app.logic.sync import sync_calendar_events
import json


@csrf_exempt
def recall_calendar_updates(request):
    """
    Webhook handler for Recall API Calendar V2 webhooks.
    
    Handles two types of webhooks as per Recall AI documentation:
    
    1. calendar.update - When calendar data changes (e.g., status becomes disconnected)
       {
         "event": "calendar.update",
         "data": {
           "calendar_id": "cal_abc123"
         }
       }
       Action: Re-fetch calendar via Retrieve Calendar endpoint
    
    2. calendar.sync_events - When events are created, updated, or deleted
       {
         "event": "calendar.sync_events",
         "data": {
           "calendar_id": "cal_abc123",
           "last_updated_ts": "2025-01-29T23:49:58.570998+00:00"
         }
       }
       Action: Fetch events with updated_at__gte = last_updated_ts
    
    Webhooks are sent via Svix and scoped to a specific calendar.
    """
    if request.method != 'POST':
        return HttpResponse(status=405)
    
    try:
        # Parse request body
        body_str = request.body.decode('utf-8')
        body = json.loads(body_str)
        
        event = body.get('event')
        payload = body.get('data', {})
        recall_id = payload.get('calendar_id')
        
        print(f'INFO: Received "{event}" calendar webhook from Recall')
        print(f'INFO: Webhook payload: {json.dumps(payload, indent=2)}')
        
        if not event:
            print(f'WARNING: Webhook missing "event" field. Ignoring.')
            return HttpResponse(status=200)
        
        if not recall_id:
            print(f'WARNING: Webhook missing "calendar_id" in data. Ignoring.')
            return HttpResponse(status=200)
        
        # Verify calendar exists with retry logic for connection errors
        calendar = None
        max_retries = 3
        for attempt in range(max_retries):
            try:
                calendar = Calendar.objects.get(recall_id=recall_id)
                print(f'INFO: Found calendar {calendar.id} for recall_id {recall_id}')
                break
            except Calendar.DoesNotExist:
                print(f'INFO: Could not find calendar with recall_id: {recall_id}. Ignoring webhook.')
                return HttpResponse(status=200)
            except Exception as e:
                if 'MaxClientsInSessionMode' in str(e) or 'max clients reached' in str(e):
                    if attempt < max_retries - 1:
                        wait_time = (attempt + 1) * 2  # Exponential backoff: 2s, 4s, 6s
                        print(f'WARNING: Connection pool exhausted. Retrying in {wait_time}s (attempt {attempt + 1}/{max_retries})')
                        import time
                        time.sleep(wait_time)
                        # Close any open connections
                        from django.db import connections
                        connections['default'].close()
                        continue
                    else:
                        print(f'ERROR: Failed to connect after {max_retries} retries: {e}')
                        # Still return 200 to prevent webhook retries
                        return HttpResponse(status=200)
                else:
                    raise
        
        if not calendar:
            print(f'ERROR: Could not find or connect to calendar with recall_id: {recall_id}')
            return HttpResponse(status=200)
        
        # Save webhook for bookkeeping (similar to background job in JS project)
        # Use connection.close() after operations to free up connections
        try:
            CalendarWebhook.objects.create(
                calendar_id=calendar.id,
                event=event,
                payload=payload
            )
            print(f'INFO: Saved webhook to database')
            # Close connection after database operation to free up pool
            from django.db import connections
            connections['default'].close()
        except Exception as e:
            print(f'WARNING: Failed to save webhook to database: {e}')
            # Close connection even on error
            from django.db import connections
            connections['default'].close()
            # Continue processing even if webhook save fails
        
        # Process webhook events per Recall AI documentation
        if event == 'calendar.update':
            # calendar.update: Calendar data changed (e.g., status becomes disconnected)
            # Action: Re-fetch calendar via Retrieve Calendar endpoint
            recall_service = get_service()
            try:
                updated_calendar_data = recall_service.get_calendar(calendar.recall_id)
                calendar.recall_data = updated_calendar_data
                calendar.save()
                print(f'INFO: Updated calendar {calendar.id} with latest Recall data')
                print(f'INFO: Calendar status: {updated_calendar_data.get("status", "unknown")}')
            except Exception as e:
                print(f'ERROR: Failed to update calendar: {e}')
                import traceback
                traceback.print_exc()
        
        elif event == 'calendar.sync_events':
            # calendar.sync_events: Events created, updated, or deleted
            # Action: Fetch events with updated_at__gte = last_updated_ts
            # Use is_deleted field to determine if event was removed
            last_updated_ts = payload.get('last_updated_ts')
            print(f'INFO: Processing calendar.sync_events for calendar {calendar.id} with timestamp: {last_updated_ts}')
            try:
                result = sync_calendar_events(calendar, last_updated_timestamp=last_updated_ts)
                if result.get('success'):
                    print(f'INFO: Successfully synced events for calendar {calendar.id}: {result.get("upserted", 0)} upserted, {result.get("deleted", 0)} deleted')
                    
                    # Broadcast update to WebSocket clients for this user
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
                                        'event': 'sync_events',
                                        'upserted': result.get('upserted', 0),
                                        'deleted': result.get('deleted', 0),
                                        'timestamp': last_updated_ts,
                                    }
                                }
                            )
                            print(f'INFO: Broadcasted calendar update to WebSocket group {group_name}')
                    except Exception as ws_error:
                        print(f'WARNING: Failed to broadcast WebSocket update: {ws_error}')
                        import traceback
                        traceback.print_exc()
                else:
                    print(f'ERROR: Sync failed for calendar {calendar.id}: {result.get("error", "Unknown error")}')
            except Exception as e:
                print(f'ERROR: Failed to sync events: {e}')
                import traceback
                traceback.print_exc()
        else:
            print(f'WARNING: Unknown event type "{event}". Ignoring.')
        
        # Close database connection before returning to free up pool
        try:
            from django.db import connections
            connections['default'].close()
        except:
            pass
        
        return HttpResponse(status=200)
    except json.JSONDecodeError as e:
        print(f'ERROR: Invalid JSON in webhook body: {e}')
        print(f'ERROR: Body received: {request.body.decode("utf-8", errors="ignore")}')
        return HttpResponse(status=400)
    except Exception as e:
        print(f'ERROR: Failed to process webhook: {e}')
        import traceback
        traceback.print_exc()
        return HttpResponse(status=200)  # Return 200 to prevent retries

