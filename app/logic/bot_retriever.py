"""
Auto-retrieve bot recordings when they're ready
"""
import os
import time
from django.utils import timezone
from app.models import BotRecording, CalendarEvent
from app.services.recall.service import get_service
from app.services.recall.artifact_downloader import download_and_save_artifacts
import traceback


def auto_retrieve_bot(bot_id: str, calendar_event_id: str = None, retry_count: int = 0, max_retries: int = 3):
    """
    Automatically retrieve bot data and download artifacts
    
    Args:
        bot_id: Recall.ai bot ID
        calendar_event_id: Optional calendar event UUID
        retry_count: Current retry attempt
        max_retries: Maximum retry attempts
        
    Returns:
        dict with success status and recording_id
    """
    try:
        recall_service = get_service()
        bot_json = recall_service.get_bot(bot_id)
        
        if not bot_json:
            if retry_count < max_retries:
                # Retry after delay
                time.sleep(5)
                return auto_retrieve_bot(bot_id, calendar_event_id, retry_count + 1, max_retries)
            return {
                'success': False,
                'error': 'Bot not found after retries'
            }
        
        # Check if recording is done
        status = bot_json.get('status')
        recordings = bot_json.get('recordings', [])
        
        # If bot is not done and has no recordings, retry later
        if status != 'done' and not recordings:
            if retry_count < max_retries:
                time.sleep(10)  # Wait 10 seconds before retry
                return auto_retrieve_bot(bot_id, calendar_event_id, retry_count + 1, max_retries)
            return {
                'success': False,
                'error': 'Recording not ready yet',
                'status': status
            }
        
        # Find or create BotRecording
        bot_recording, created = BotRecording.objects.update_or_create(
            bot_id=bot_id,
            defaults={
                'recall_data': bot_json,
                'status': 'completed' if status == 'done' else 'processing',
                'calendar_event_id': calendar_event_id
            }
        )
        
        # Download artifacts if recordings exist
        download_results = None
        if recordings:
            try:
                download_results = download_and_save_artifacts(bot_recording, bot_json)
                print(f'INFO: Downloaded artifacts for bot {bot_id}: {download_results}')
            except Exception as e:
                print(f'ERROR: Failed to download artifacts for bot {bot_id}: {e}')
                traceback.print_exc()
        
        return {
            'success': True,
            'recording_id': str(bot_recording.id),
            'bot_id': bot_id,
            'download_results': download_results,
            'status': status
        }
        
    except Exception as e:
        print(f'ERROR: Failed to auto-retrieve bot {bot_id}: {e}')
        traceback.print_exc()
        return {
            'success': False,
            'error': str(e)
        }


def check_and_retrieve_completed_bots():
    """
    Check all calendar events for bots that might be completed and retrieve them
    This can be called periodically (e.g., via cron or management command)
    """
    retrieved_count = 0
    error_count = 0
    
    # Find events with bots
    events = CalendarEvent.objects.filter(
        recall_data__bots__isnull=False
    )
    
    for event in events:
        bots = event.bots
        if not bots:
            continue
            
        for bot_info in bots:
            bot_id = bot_info.get('bot_id')
            if not bot_id:
                continue
            
            # Check if already retrieved
            existing_recording = BotRecording.objects.filter(bot_id=bot_id).first()
            if existing_recording and existing_recording.status == 'completed':
                continue  # Already retrieved
            
            # Try to retrieve
            try:
                result = auto_retrieve_bot(bot_id, str(event.id))
                if result['success']:
                    retrieved_count += 1
                    print(f'INFO: ✓ Retrieved bot {bot_id} for event {event.id}')
                else:
                    print(f'INFO: Bot {bot_id} not ready yet: {result.get("error")}')
            except Exception as e:
                error_count += 1
                print(f'ERROR: Failed to retrieve bot {bot_id}: {e}')
    
    return {
        'retrieved': retrieved_count,
        'errors': error_count
    }

