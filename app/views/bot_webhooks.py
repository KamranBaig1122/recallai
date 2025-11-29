"""
Webhook handlers for Recall.ai bot events (transcripts, participant events, etc.)
These are different from calendar webhooks - these come from bots during meetings.
"""
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json
import os


@csrf_exempt
def bot_webhook(request):
    """
    Handle webhooks from Recall.ai bots during meetings.
    
    Receives:
    - transcript.data: Real-time transcripts
    - participant_events.*: Join/leave, speech on/off, webcam on/off, etc.
    - bot.status_change: Bot status updates (e.g., bot.done when meeting ends)
    
    Similar to meeting-bot/app/pythonHowToBuildABot.py wh() function
    """
    if request.method != 'POST':
        return HttpResponse(status=405)
    
    try:
        # Parse request body
        body_str = request.body.decode('utf-8')
        try:
            payload = json.loads(body_str)
        except json.JSONDecodeError:
            print(f'[bot-wh] non-JSON payload: {body_str[:200]}')
            return JsonResponse({"ok": False, "error": "bad json"}, status=400)
        
        event = payload.get("event") or payload.get("type", "")
        data = payload.get("data") or payload.get("payload") or {}
        event_data = data.get("data") or {}
        
        # Extract timestamp and participant info
        timestamp = (event_data.get("timestamp") or {}).get("absolute")
        participant = event_data.get("participant")
        participant_name = None
        if isinstance(participant, dict):
            participant_name = participant.get("name") or participant.get("id")
        
        # Handle different event types
        if event == "transcript.data":
            words = event_data.get("words") or []
            text = " ".join((w.get("text", "") for w in words)) or event_data.get("text", "") or ""
            print(f'[bot-wh] transcript.data ts={timestamp} speaker={participant_name} text={text[:100]}')
        
        elif event.startswith("participant_events."):
            # Compact logging for participant events
            details = json.dumps(event_data, separators=(",", ":"), ensure_ascii=False)
            if len(details) > 500:
                details = details[:500] + "…"
            print(f'[bot-wh] {event} ts={timestamp} who={participant_name} details={details}')
        
        elif event == "bot.status_change":
            code = event_data.get("code")
            print(f'[bot-wh] bot.status_change ts={timestamp} code={code}')
            
            # Auto-retrieve when bot is done
            if code in ["bot.done", "recording_done", "done"]:
                bot_id = payload.get("bot_id") or event_data.get("bot_id")
                if bot_id:
                    print(f'[bot-wh] Bot {bot_id} is done, triggering auto-retrieve...')
                    try:
                        # Import here to avoid circular imports
                        from app.logic.bot_retriever import auto_retrieve_bot
                        from app.models import CalendarEvent
                        
                        # Find calendar event with this bot_id
                        calendar_event = CalendarEvent.objects.filter(
                            recall_data__bots__bot_id=bot_id
                        ).first()
                        
                        calendar_event_id = str(calendar_event.id) if calendar_event else None
                        
                        # Trigger auto-retrieve (async/background)
                        # Use threading to avoid blocking webhook response
                        import threading
                        def retrieve_in_background():
                            result = auto_retrieve_bot(bot_id, calendar_event_id)
                            if result['success']:
                                print(f'[bot-wh] ✓ Auto-retrieved bot {bot_id}: {result.get("recording_id")}')
                            else:
                                print(f'[bot-wh] ⚠ Auto-retrieve failed for bot {bot_id}: {result.get("error")}')
                        
                        thread = threading.Thread(target=retrieve_in_background)
                        thread.daemon = True
                        thread.start()
                    except Exception as e:
                        print(f'[bot-wh] ERROR: Failed to trigger auto-retrieve: {e}')
                        import traceback
                        traceback.print_exc()
        
        else:
            # Log unknown events
            payload_str = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
            print(f'[bot-wh] event: {event} | payload: {(payload_str[:800] + "…") if len(payload_str) > 800 else payload_str}')
        
        # Return success quickly (do heavy work in background)
        return JsonResponse({"ok": True})
        
    except Exception as e:
        print(f'[bot-wh] ERROR: {e}')
        import traceback
        traceback.print_exc()
        # Still return 200 to prevent webhook retries
        return JsonResponse({"ok": False, "error": str(e)}, status=200)


@csrf_exempt
def bot_websocket_info(request):
    """
    Info endpoint for WebSocket connections.
    Returns WebSocket connection information.
    """
    if request.method != 'GET':
        return HttpResponse(status=405)
    
    # Check token if provided
    token = request.GET.get('token')
    expected_token = os.getenv('WS_TOKEN', 'dev-secret')
    
    if token != expected_token:
        return JsonResponse({"error": "Invalid token"}, status=401)
    
    # Return WebSocket connection info
    public_url = os.getenv('PUBLIC_URL', '')
    ws_url = None
    if public_url:
        if public_url.startswith('https://'):
            ws_url = public_url.replace('https://', 'wss://') + '/ws/rt?token=' + expected_token
        elif public_url.startswith('http://'):
            ws_url = public_url.replace('http://', 'ws://') + '/ws/rt?token=' + expected_token
    
    return JsonResponse({
        "message": "WebSocket endpoint available",
        "websocket_url": ws_url or "ws://localhost:3003/ws/rt?token=" + expected_token,
        "status": "ready"
    })

