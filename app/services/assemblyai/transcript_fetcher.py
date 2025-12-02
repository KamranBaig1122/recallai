"""
Service to fetch transcripts from AssemblyAI API after meeting ends
Based on assemblyai-recallai-zoom-bot integration pattern
"""
import os
import requests
import time
from typing import Dict, Any, Optional
from django.conf import settings


def get_assemblyai_transcript(transcript_id: str) -> Optional[Dict[str, Any]]:
    """
    Fetch transcript from AssemblyAI API by transcript ID
    
    This fetches the full transcript including:
    - text: Full transcript text
    - summary: Summary if summarization was enabled
    - words: Word-level timestamps
    - utterances: Speaker-segmented utterances
    - All other AssemblyAI metadata
    
    Args:
        transcript_id: AssemblyAI transcript ID
        
    Returns:
        Full transcript data including summary, words, utterances, etc.
    """
    base_url = "https://api.assemblyai.com"
    api_key = os.getenv('ASSEMBLY_AI_API_KEY', '')
    
    if not api_key:
        print('WARNING: ASSEMBLY_AI_API_KEY not set in environment')
        return None
    
    headers = {
        "authorization": api_key
    }
    
    polling_endpoint = f"{base_url}/v2/transcript/{transcript_id}"
    
    try:
        print(f'INFO: Fetching AssemblyAI transcript {transcript_id}...')
        
        # Poll until transcript is ready (or get it if already completed)
        max_attempts = 60  # 3 minutes max (60 * 3 seconds)
        attempt = 0
        
        while attempt < max_attempts:
            response = requests.get(polling_endpoint, headers=headers)
            response.raise_for_status()
            
            transcription_result = response.json()
            status = transcription_result.get('status')
            
            if status == 'completed':
                print(f'INFO: AssemblyAI transcript {transcript_id} is ready')
                return transcription_result
            elif status == 'error':
                error_msg = transcription_result.get('error', 'Unknown error')
                print(f'ERROR: AssemblyAI transcription failed: {error_msg}')
                raise RuntimeError(f"Transcription failed: {error_msg}")
            else:
                # Still processing - wait and retry
                attempt += 1
                if attempt < max_attempts:
                    print(f'INFO: Transcript {transcript_id} status: {status}, waiting... (attempt {attempt}/{max_attempts})')
                    time.sleep(3)
                else:
                    print(f'WARNING: AssemblyAI transcript {transcript_id} timed out after {max_attempts} attempts')
                    return None
                    
    except requests.exceptions.RequestException as e:
        print(f'ERROR: Failed to fetch AssemblyAI transcript {transcript_id}: {e}')
        return None


def extract_assemblyai_transcript_id(bot_json: Dict[str, Any]) -> Optional[str]:
    """
    Extract AssemblyAI transcript ID from bot data
    
    When using AssemblyAI with Recall.ai, the transcript ID can be found in:
    - recordings[].media_shortcuts.transcript.data.id (direct transcript ID)
    - recordings[].media_shortcuts.transcript.data.provider_data_download_url (URL containing ID)
    - recordings[].media_shortcuts.transcript.provider.assembly_ai_v3_streaming (metadata)
    
    Args:
        bot_json: Full bot data from Recall.ai
        
    Returns:
        AssemblyAI transcript ID if found, None otherwise
    """
    recordings = bot_json.get('recordings', [])
    
    for recording in recordings:
        media_shortcuts = recording.get('media_shortcuts', {})
        transcript_node = media_shortcuts.get('transcript', {})
        
        # Method 1: Check if transcript ID is directly in the data
        transcript_data = transcript_node.get('data', {})
        
        # Direct ID field
        transcript_id = transcript_data.get('id') or transcript_data.get('transcript_id')
        if transcript_id:
            print(f'INFO: Found transcript ID in data: {transcript_id}')
            return transcript_id
        
        # Method 2: Check provider_data_download_url - might contain transcript ID
        provider_url = transcript_data.get('provider_data_download_url', '')
        if provider_url:
            # Extract ID from URL if it's an AssemblyAI URL
            # URL format might be: https://api.assemblyai.com/v2/transcript/{id}
            if 'assemblyai.com' in provider_url or '/transcript/' in provider_url:
                # Try to extract ID from URL
                parts = provider_url.split('/')
                for i, part in enumerate(parts):
                    if part == 'transcript' and i + 1 < len(parts):
                        potential_id = parts[i + 1]
                        # Remove query parameters if any
                        potential_id = potential_id.split('?')[0].split('#')[0]
                        if len(potential_id) == 36 and '-' in potential_id:  # UUID format
                            print(f'INFO: Extracted transcript ID from URL: {potential_id}')
                            return potential_id
        
        # Method 3: Check provider metadata for assembly_ai_v3_streaming
        provider = transcript_node.get('provider', {})
        if isinstance(provider, dict):
            # Check if it's AssemblyAI v3 streaming (as per zoomBot.js)
            assembly_ai_data = provider.get('assembly_ai_v3_streaming') or provider.get('assembly_ai_async_chunked')
            if assembly_ai_data:
                # Check metadata for transcript ID
                metadata = transcript_node.get('metadata', {})
                transcript_id = metadata.get('transcript_id') or metadata.get('assemblyai_transcript_id')
                if transcript_id:
                    print(f'INFO: Found transcript ID in metadata: {transcript_id}')
                    return transcript_id
        
        # Method 4: Check if there's a direct transcript ID field in the node
        transcript_id = transcript_node.get('transcript_id') or transcript_node.get('id')
        if transcript_id:
            print(f'INFO: Found transcript ID in node: {transcript_id}')
            return transcript_id
    
    print('WARNING: Could not find AssemblyAI transcript ID in bot data')
    return None

