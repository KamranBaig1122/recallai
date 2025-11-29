"""
Service to download and store recording artifacts (video, transcript, audio)
"""
import os
import requests
import json
from pathlib import Path
from django.conf import settings
from django.utils import timezone
from typing import Dict, Any, Optional
from app.models import BotRecording, RecordingArtifact
from app.services.recall.service import get_service
import traceback


def extract_media_shortcuts(bot_json: Dict[str, Any]) -> list:
    """
    Extract media shortcut URLs from bot JSON (similar to meeting-bot/mediahelpers.py)
    Returns list of dicts with recording_id and download URLs
    """
    out = []
    for rec in bot_json.get("recordings") or []:
        shortcuts = rec.get("media_shortcuts") or {}
        
        def url(key: str) -> Optional[str]:
            node = shortcuts.get(key) or {}
            data = node.get("data") or {}
            return data.get("download_url")
        
        out.append({
            "recording_id": rec.get("id"),
            "transcript_url": url("transcript"),
            "video_mixed_url": url("video_mixed"),
            "audio_mixed_url": url("audio_mixed"),
        })
    return out


def download_file(url: str, save_path: Path, timeout: int = 300) -> tuple[bool, Optional[int]]:
    """
    Download a file from URL and save to local path
    
    Returns:
        (success: bool, file_size: int or None)
    """
    try:
        response = requests.get(url, stream=True, timeout=timeout)
        response.raise_for_status()
        
        # Ensure directory exists
        save_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Download and save
        file_size = 0
        with open(save_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    file_size += len(chunk)
        
        return True, file_size
    except Exception as e:
        print(f'ERROR: Failed to download {url}: {e}')
        traceback.print_exc()
        return False, None


def download_and_save_artifacts(bot_recording: BotRecording, bot_json: Dict[str, Any]) -> Dict[str, Any]:
    """
    Download artifacts from Recall.ai and save to database and local storage
    
    Args:
        bot_recording: BotRecording instance
        bot_json: Full bot data from Recall.ai API
        
    Returns:
        Dict with download results
    """
    results = {
        'downloaded': [],
        'failed': [],
        'skipped': []
    }
    
    # Extract media shortcuts
    media_shortcuts = extract_media_shortcuts(bot_json)
    
    # Create artifacts directory with better structure
    # Format: artifacts/bot_id/recording_id/
    base_dir = Path(settings.BASE_DIR)
    bot_id = bot_recording.bot_id
    
    # Get first recording ID for folder structure
    first_recording_id = None
    if bot_json.get('recordings'):
        first_recording_id = bot_json['recordings'][0].get('id')
    
    if first_recording_id:
        artifacts_dir = base_dir / 'artifacts' / bot_id / first_recording_id
    else:
        artifacts_dir = base_dir / 'artifacts' / bot_id / 'default'
    
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    
    for media in media_shortcuts:
        recording_id = media.get('recording_id')
        if not recording_id:
            continue
        
        # Download transcript
        if media.get('transcript_url'):
            success, file_size = download_file(
                media['transcript_url'],
                artifacts_dir / f'{recording_id}_transcript.json'
            )
            if success:
                artifact, created = RecordingArtifact.objects.update_or_create(
                    bot_recording_id=bot_recording.id,
                    recording_id=recording_id,
                    artifact_type='transcript',
                    defaults={
                        'file_path': str(artifacts_dir / f'{recording_id}_transcript.json'),
                        'file_size': file_size,
                        'file_format': 'json',
                        'download_url': media['transcript_url'],
                        'downloaded_at': timezone.now()
                    }
                )
                results['downloaded'].append(f'transcript-{recording_id}')
            else:
                results['failed'].append(f'transcript-{recording_id}')
        
        # Download video
        if media.get('video_mixed_url'):
            success, file_size = download_file(
                media['video_mixed_url'],
                artifacts_dir / f'{recording_id}_video.mp4'
            )
            if success:
                artifact, created = RecordingArtifact.objects.update_or_create(
                    bot_recording_id=bot_recording.id,
                    recording_id=recording_id,
                    artifact_type='video_mixed',
                    defaults={
                        'file_path': str(artifacts_dir / f'{recording_id}_video.mp4'),
                        'file_size': file_size,
                        'file_format': 'mp4',
                        'download_url': media['video_mixed_url'],
                        'downloaded_at': timezone.now()
                    }
                )
                results['downloaded'].append(f'video-{recording_id}')
            else:
                results['failed'].append(f'video-{recording_id}')
        
        # Download audio
        if media.get('audio_mixed_url'):
            success, file_size = download_file(
                media['audio_mixed_url'],
                artifacts_dir / f'{recording_id}_audio.mp3'
            )
            if success:
                artifact, created = RecordingArtifact.objects.update_or_create(
                    bot_recording_id=bot_recording.id,
                    recording_id=recording_id,
                    artifact_type='audio_mixed',
                    defaults={
                        'file_path': str(artifacts_dir / f'{recording_id}_audio.mp3'),
                        'file_size': file_size,
                        'file_format': 'mp3',
                        'download_url': media['audio_mixed_url'],
                        'downloaded_at': timezone.now()
                    }
                )
                results['downloaded'].append(f'audio-{recording_id}')
            else:
                results['failed'].append(f'audio-{recording_id}')
    
    return results

