"""
Views for retrieving and displaying bot recordings
"""
import json
from django.http import JsonResponse, HttpResponse, FileResponse, Http404
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import get_object_or_404
from app.models import BotRecording, RecordingArtifact, CalendarEvent
from app.services.recall.service import get_service
from app.services.assemblyai.transcript_fetcher import (
    get_assemblyai_transcript,
    extract_assemblyai_transcript_id
)
from pathlib import Path


@csrf_exempt
def retrieve_bot(request, bot_id: str):
    """
    Retrieve bot data from Recall.ai and save to database
    Similar to meeting-bot /retrieve/{bot_id} endpoint
    
    GET /retrieve/<bot_id>
    Returns bot data with download URLs (no file downloading)
    """
    if request.method != 'GET':
        return JsonResponse({
            'ok': False,
            'error': 'Method not allowed. Use GET.'
        }, status=405)
    
    try:
        print(f'INFO: Retrieving bot {bot_id}...')
        
        # Get bot data from Recall.ai
        recall_service = get_service()
        bot_json = recall_service.get_bot(bot_id)
        
        if not bot_json:
            print(f'WARNING: Bot {bot_id} not found in Recall.ai')
            return JsonResponse({
                'ok': False,
                'error': 'Bot not found'
            }, status=404)
        
        print(f'INFO: Retrieved bot data for {bot_id}')
        
        # Determine status from bot data
        status_changes = bot_json.get('status_changes', [])
        bot_status = 'processing'
        if status_changes:
            last_status = status_changes[-1].get('code', '')
            if last_status in ['done', 'recording_done', 'bot.done']:
                bot_status = 'completed'
        
        # Find or create BotRecording
        bot_recording, created = BotRecording.objects.update_or_create(
            bot_id=bot_id,
            defaults={
                'recall_data': bot_json,
                'status': bot_status
            }
        )
        
        print(f'INFO: Saved bot recording to database (created: {created})')
        
        # Try to link to calendar event if bot_id matches
        try:
            calendar_event = CalendarEvent.objects.filter(
                recall_data__bots__0__bot_id=bot_id
            ).first()
            if calendar_event:
                bot_recording.calendar_event_id = calendar_event.id
                bot_recording.save()
                print(f'INFO: Linked bot to calendar event {calendar_event.id}')
        except Exception as e:
            print(f'INFO: Could not link bot to calendar event: {e}')
        
        # Fetch AssemblyAI transcript if available (after meeting ends)
        assemblyai_transcript = None
        assemblyai_transcript_id = None
        
        if bot_status == 'completed':
            # Only fetch transcript if bot is completed
            assemblyai_transcript_id = extract_assemblyai_transcript_id(bot_json)
            
            if assemblyai_transcript_id:
                print(f'INFO: Found AssemblyAI transcript ID: {assemblyai_transcript_id}')
                try:
                    assemblyai_transcript = get_assemblyai_transcript(assemblyai_transcript_id)
                    if assemblyai_transcript:
                        print(f'INFO: Successfully fetched AssemblyAI transcript')
                        # Save transcript to bot_recording.recall_data
                        recall_data = bot_recording.recall_data.copy()
                        recall_data['assemblyai_transcript'] = assemblyai_transcript
                        recall_data['assemblyai_transcript_id'] = assemblyai_transcript_id
                        bot_recording.recall_data = recall_data
                        bot_recording.save()
                        print(f'INFO: Saved AssemblyAI transcript to database')
                except Exception as e:
                    print(f'WARNING: Failed to fetch AssemblyAI transcript: {e}')
                    import traceback
                    traceback.print_exc()
            else:
                print(f'INFO: No AssemblyAI transcript ID found in bot data')
        else:
            print(f'INFO: Bot not completed yet, skipping AssemblyAI transcript fetch')
        
        # Return bot data (no downloading)
        response_data = {
            'ok': True,
            'bot_id': bot_id,
            'bot_data': bot_json,
            'recording_id': str(bot_recording.id),
            'status': bot_status,
            'assemblyai_transcript_id': assemblyai_transcript_id,
            'assemblyai_transcript': assemblyai_transcript
        }
        
        print(f'INFO: Successfully retrieved bot {bot_id}')
        return JsonResponse(response_data)
        
    except Exception as e:
        print(f'ERROR: Failed to retrieve bot {bot_id}: {e}')
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'ok': False,
            'error': str(e),
            'bot_id': bot_id
        }, status=500)


def view_recording(request, recording_id: str):
    """
    View a recording with video and transcript
    """
    bot_recording = get_object_or_404(BotRecording, id=recording_id)
    
    # Get artifacts
    artifacts = RecordingArtifact.objects.filter(bot_recording_id=bot_recording.id)
    video_artifact = artifacts.filter(artifact_type='video_mixed').first()
    transcript_artifact = artifacts.filter(artifact_type='transcript').first()
    audio_artifact = artifacts.filter(artifact_type='audio_mixed').first()
    
    # Load transcript if available
    transcript_data = None
    if transcript_artifact and transcript_artifact.file_path:
        try:
            # Handle both absolute and relative paths
            file_path = transcript_artifact.file_path
            if not Path(file_path).is_absolute():
                # Relative path - resolve from BASE_DIR
                from django.conf import settings
                transcript_path = Path(settings.BASE_DIR) / file_path
            else:
                transcript_path = Path(file_path)
            
            with open(transcript_path, 'r', encoding='utf-8') as f:
                transcript_data = json.load(f)
        except Exception as e:
            print(f'ERROR: Failed to load transcript: {e}')
    
    # Get calendar event if linked
    calendar_event = None
    if bot_recording.calendar_event_id:
        try:
            calendar_event = CalendarEvent.objects.get(id=bot_recording.calendar_event_id)
        except CalendarEvent.DoesNotExist:
            pass
    
    context = {
        'recording': bot_recording,
        'video_artifact': video_artifact,
        'transcript_artifact': transcript_artifact,
        'audio_artifact': audio_artifact,
        'transcript_data': transcript_data,
        'calendar_event': calendar_event,
    }
    
    # Render HTML template
    from django.shortcuts import render
    return render(request, 'recording_view.html', context)


def serve_video(request, recording_id: str):
    """
    Serve video file
    """
    bot_recording = get_object_or_404(BotRecording, id=recording_id)
    video_artifact = RecordingArtifact.objects.filter(
        bot_recording_id=bot_recording.id,
        artifact_type='video_mixed'
    ).first()
    
    if not video_artifact or not video_artifact.file_path:
        raise Http404('Video not found')
    
    # Handle both absolute and relative paths
    file_path = video_artifact.file_path
    if not Path(file_path).is_absolute():
        # Relative path - resolve from BASE_DIR
        from django.conf import settings
        video_path = Path(settings.BASE_DIR) / file_path
    else:
        video_path = Path(file_path)
    
    if not video_path.exists():
        raise Http404('Video file not found')
    
    return FileResponse(
        open(video_path, 'rb'),
        content_type='video/mp4',
        headers={
            'Content-Disposition': f'inline; filename="{video_path.name}"',
            'Accept-Ranges': 'bytes'
        }
    )


def serve_transcript(request, recording_id: str):
    """
    Serve transcript as JSON
    """
    bot_recording = get_object_or_404(BotRecording, id=recording_id)
    transcript_artifact = RecordingArtifact.objects.filter(
        bot_recording_id=bot_recording.id,
        artifact_type='transcript'
    ).first()
    
    if not transcript_artifact or not transcript_artifact.file_path:
        raise Http404('Transcript not found')
    
    # Handle both absolute and relative paths
    file_path = transcript_artifact.file_path
    if not Path(file_path).is_absolute():
        # Relative path - resolve from BASE_DIR
        from django.conf import settings
        transcript_path = Path(settings.BASE_DIR) / file_path
    else:
        transcript_path = Path(file_path)
    
    if not transcript_path.exists():
        raise Http404('Transcript file not found')
    
    return FileResponse(
        open(transcript_path, 'rb'),
        content_type='application/json',
        headers={
            'Content-Disposition': f'inline; filename="{transcript_path.name}"'
        }
    )

