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
        print(f'INFO: Raw request body (first 1000 chars): {body_str[:1000]}')
        body = json.loads(body_str)
        
        event = body.get('event')
        payload = body.get('data', {})
        recall_id = payload.get('calendar_id')
        
        print(f'INFO: Received "{event}" calendar webhook from Recall')
        print(f'INFO: Full body JSON: {json.dumps(body, indent=2)}')
        print(f'INFO: Full body keys: {list(body.keys())}')
        print(f'INFO: Webhook payload (data only): {json.dumps(payload, indent=2)}')
        
        # Check if this is a bot status webhook FIRST (before checking calendar_id)
        # Bot webhooks have bot info nested in body['data']['bot'] (not at top level)
        # Structure: body['data']['bot']['id'] and body['data']['data']['code']
        bot_id = None
        bot_status_code = None
        
        # Check if body has 'data' key and then 'bot' inside it
        # The actual structure is: body['data']['bot']['id']
        if 'data' in body:
            data_obj = body.get('data', {})
            if isinstance(data_obj, dict):
                # Check for bot info nested in data
                if 'bot' in data_obj:
                    bot_data = data_obj.get('bot', {})
                    if isinstance(bot_data, dict):
                        bot_id = bot_data.get('id')
                        print(f'INFO: Found bot_id in body["data"]["bot"]["id"]: {bot_id}')
                    else:
                        print(f'INFO: body["data"]["bot"] is not a dict, type: {type(bot_data)}')
                
                # Get bot_status_code from data.data.code (nested structure)
                # The actual structure is: body['data']['data']['code']
                if 'data' in data_obj:
                    nested_data = data_obj.get('data', {})
                    if isinstance(nested_data, dict):
                        bot_status_code = nested_data.get('code')
                        print(f'INFO: Found bot_status_code in body["data"]["data"]["code"]: {bot_status_code}')
            else:
                print(f'INFO: body["data"] is not a dict, type: {type(data_obj)}')
        
        # Fallback: Check top-level 'bot' key (for backwards compatibility with other webhook formats)
        if not bot_id and 'bot' in body:
            bot_data = body.get('bot', {})
            if isinstance(bot_data, dict):
                bot_id = bot_data.get('id')
                print(f'INFO: Found bot_id in body["bot"]["id"] (fallback): {bot_id}')
        
        # Fallback: If event indicates bot webhook but bot_id is None, try recursive extraction
        is_bot_webhook = event and event.startswith('bot.')
        if is_bot_webhook and not bot_id:
            # Try alternative extraction methods - search recursively for UUID-like bot IDs
            print(f'INFO: Bot webhook detected but bot_id is None. Trying recursive extraction...')
            def find_bot_id_recursive(obj, path=""):
                """Recursively search for bot id in nested structure"""
                if isinstance(obj, dict):
                    # Check if this dict has 'id' and looks like a bot id (UUID format)
                    if 'id' in obj and isinstance(obj['id'], str):
                        potential_id = obj['id']
                        # Check if it looks like a UUID (contains hyphens and is 36 chars)
                        if '-' in potential_id and len(potential_id) == 36:
                            # Also check if parent key is 'bot' or we're in a bot-related structure
                            print(f'INFO: Found potential bot_id at path {path}["id"]: {potential_id}')
                            return potential_id
                    # Recursively search nested dicts
                    for key, value in obj.items():
                        if key != 'event' and key != 'calendar_id' and key != 'recall_id':  # Skip known non-bot keys
                            result = find_bot_id_recursive(value, f'{path}["{key}"]' if path else f'["{key}"]')
                            if result:
                                return result
                elif isinstance(obj, list):
                    for i, item in enumerate(obj):
                        result = find_bot_id_recursive(item, f'{path}[{i}]')
                        if result:
                            return result
                return None
            
            found_bot_id = find_bot_id_recursive(body)
            if found_bot_id:
                bot_id = found_bot_id
                print(f'INFO: Using bot_id from recursive search: {bot_id}')
        
        print(f'INFO: Event="{event}", is_bot_webhook={is_bot_webhook}, bot_id={bot_id}, bot_status_code={bot_status_code}, recall_id={recall_id}')
        
        # SIMPLE CHECK: If we have bot_id, this is a bot webhook (handle it)
        # Bot webhooks don't have calendar_id, so if bot_id exists, it's a bot webhook
        if bot_id:
            # This is a bot status webhook (bot.joining_call, bot.in_call_recording, bot.done, etc.)
            print(f'INFO: ✅ BOT WEBHOOK DETECTED: bot_id={bot_id}, status_code={bot_status_code}, event={event}')
            try:
                from app.models import BotRecording
                bot_recording = BotRecording.objects.filter(bot_id=bot_id).first()
                
                if bot_recording:
                    print(f'INFO: Found BotRecording {bot_recording.id} for bot_id {bot_id}')
                    print(f'INFO: Current status: {bot_recording.status}, recall_data: {bot_recording.recall_data}')
                    
                    # Try to fetch and store owner name if not already stored (OPTIONAL - fallback if fails)
                    if bot_recording.backend_user_id and not (bot_recording.recall_data and bot_recording.recall_data.get('owner_name')):
                        try:
                            from app.logic.bot_creator import get_user_name_from_backend
                            owner_name = get_user_name_from_backend(str(bot_recording.backend_user_id))
                            if owner_name:
                                if not bot_recording.recall_data:
                                    bot_recording.recall_data = {}
                                bot_recording.recall_data['owner_name'] = owner_name
                                bot_recording.save(update_fields=['recall_data'])
                                print(f'INFO: ✓ Stored owner name in BotRecording: {owner_name}')
                        except Exception as e:
                            # Silently fail - this is optional, bot will work without it
                            pass
                    
                    # Map bot status codes to BotRecording status
                    status_mapping = {
                        'joining_call': 'joining',
                        'in_waiting_room': 'joining',
                        'in_call_not_recording': 'processing',
                        'in_call_recording': 'processing',
                        'call_ended': 'processing',  # Still processing until bot.done
                        'done': 'completed',
                    }
                    
                    new_status = status_mapping.get(bot_status_code, bot_recording.status)
                    print(f'INFO: Mapping bot_status_code "{bot_status_code}" to new_status "{new_status}"')
                    
                    if new_status != bot_recording.status:
                        old_status = bot_recording.status
                        bot_recording.status = new_status
                        bot_recording.save()
                        print(f'INFO: ✅ Updated BotRecording {bot_recording.id} status: {old_status} → {new_status} (from webhook: {bot_status_code})')
                    else:
                        print(f'INFO: BotRecording status unchanged ({new_status}), skipping status update')
                    
                    # Store latest bot status in recall_data for real-time tracking
                    if not bot_recording.recall_data:
                        bot_recording.recall_data = {}
                        print(f'INFO: Initialized empty recall_data for BotRecording {bot_recording.id}')
                    
                    if 'bot_status' not in bot_recording.recall_data:
                        bot_recording.recall_data['bot_status'] = {}
                    
                    updated_at = body.get('data', {}).get('updated_at')
                    bot_recording.recall_data['bot_status'][bot_status_code] = updated_at
                    bot_recording.recall_data['latest_status'] = bot_status_code
                    bot_recording.save()
                    print(f'INFO: ✅ Updated BotRecording {bot_recording.id} latest_status to: {bot_status_code}, recall_data saved')
                    
                    # Verify the save worked
                    bot_recording.refresh_from_db()
                    print(f'INFO: Verified - BotRecording {bot_recording.id} status={bot_recording.status}, latest_status={bot_recording.recall_data.get("latest_status") if bot_recording.recall_data else None}')
                    
                    # If bot is done, also update MeetingTranscription status to 'completed'
                    if bot_status_code == 'done':
                        try:
                            from app.models import MeetingTranscription
                            # Update all transcriptions for this bot
                            transcriptions = MeetingTranscription.objects.filter(
                                bot_id=bot_id
                            )
                            if bot_recording.backend_user_id:
                                transcriptions = transcriptions.filter(backend_user_id=bot_recording.backend_user_id)
                            
                            updated_count = 0
                            for transcription in transcriptions:
                                if transcription.status != 'completed':
                                    transcription.status = 'completed'
                                    transcription.save()
                                    updated_count += 1
                            
                            if updated_count > 0:
                                print(f'INFO: Updated {updated_count} MeetingTranscription record(s) status to completed (bot.done received for bot_id: {bot_id})')
                        except Exception as e:
                            print(f'WARNING: Failed to update MeetingTranscription status: {e}')
                            import traceback
                            traceback.print_exc()
                else:
                    print(f'WARNING: BotRecording not found for bot_id: {bot_id}')
                    # Try to find by bot_id without backend_user_id filter
                    all_bots = BotRecording.objects.filter(bot_id=bot_id)
                    print(f'WARNING: Found {all_bots.count()} BotRecording(s) with bot_id {bot_id} (without backend_user_id filter)')
                    if all_bots.exists():
                        print(f'WARNING: BotRecording exists but backend_user_id might not match. Bot IDs: {[b.id for b in all_bots]}')
            except Exception as e:
                print(f'ERROR: Failed to update bot status: {e}')
                import traceback
                traceback.print_exc()
            
            return HttpResponse(status=200)
        
        # If we reach here, it's not a bot webhook, check if it's a calendar webhook
        if not recall_id:
            print(f'WARNING: Webhook missing "calendar_id" in data and no bot_id found. Ignoring.')
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
        
        # Process webhook events in background to avoid blocking webhook response
        # This prevents the "took too long to shut down" warning
        import threading
        
        def process_webhook_in_background():
            try:
                # Re-fetch calendar in background thread (fresh connection)
                from app.models import Calendar
                calendar = Calendar.objects.get(recall_id=recall_id)
                
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
                
                # Close database connection after processing
                try:
                    from django.db import connections
                    connections['default'].close()
                except:
                    pass
            except Exception as e:
                print(f'ERROR: Failed to process webhook in background: {e}')
                import traceback
                traceback.print_exc()
        
        # Start background thread and return immediately
        thread = threading.Thread(target=process_webhook_in_background)
        thread.daemon = True
        thread.start()
        
        # Close database connection before returning to free up pool
        try:
            from django.db import connections
            connections['default'].close()
        except:
            pass
        
        # Return immediately - processing happens in background
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

