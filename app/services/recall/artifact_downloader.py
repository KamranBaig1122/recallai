"""
Service to extract media shortcut URLs from bot data
Download functionality has been removed - only URL extraction remains
"""
from typing import Dict, Any, Optional


def extract_media_shortcuts(bot_json: Dict[str, Any]) -> list:
    """
    Extract media shortcut URLs from bot JSON (similar to meeting-bot/mediahelpers.py)
    Returns list of dicts with recording_id and download URLs
    Includes: video, transcript, and provider_data_download_url
    """
    out = []
    for rec in bot_json.get("recordings") or []:
        shortcuts = rec.get("media_shortcuts") or {}
        
        def url(key: str) -> Optional[str]:
            node = shortcuts.get(key) or {}
            data = node.get("data") or {}
            return data.get("download_url")
        
        # Get provider_data_download_url from transcript
        provider_transcript_url = None
        transcript_node = shortcuts.get("transcript") or {}
        transcript_data = transcript_node.get("data") or {}
        provider_transcript_url = transcript_data.get("provider_data_download_url")
        
        out.append({
            "recording_id": rec.get("id"),
            "transcript_url": url("transcript"),
            "provider_transcript_url": provider_transcript_url,  # Provider transcript URL
            "video_mixed_url": url("video_mixed"),
            "audio_mixed_url": url("audio_mixed"),
        })
    return out
