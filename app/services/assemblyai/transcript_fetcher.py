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
        print('[AssemblyAI] ⚠ WARNING: ASSEMBLY_AI_API_KEY not set in environment')
        print('[AssemblyAI] Cannot fetch transcript without API key')
        return None
    
    print(f'[AssemblyAI] API Key configured: {api_key[:10]}...{api_key[-4:] if len(api_key) > 14 else "***"}')
    
    headers = {
        "authorization": api_key
    }
    
    polling_endpoint = f"{base_url}/v2/transcript/{transcript_id}"
    
    try:
        print(f'[AssemblyAI] ==========================================')
        print(f'[AssemblyAI] 📥 FETCHING TRANSCRIPT: {transcript_id}')
        print(f'[AssemblyAI] Endpoint: {polling_endpoint}')
        print(f'[AssemblyAI] ==========================================')
        
        # Poll until transcript is ready (or get it if already completed)
        max_attempts = 60  # 3 minutes max (60 * 3 seconds)
        attempt = 0
        
        while attempt < max_attempts:
            print(f'[AssemblyAI] Polling attempt {attempt + 1}/{max_attempts}...')
            response = requests.get(polling_endpoint, headers=headers)
            response.raise_for_status()
            
            transcription_result = response.json()
            status = transcription_result.get('status')
            
            print(f'[AssemblyAI] Response status: {status}')
            
            if status == 'completed':
                print(f'[AssemblyAI] ✅ Transcript is ready!')
                print(f'[AssemblyAI] Transcript text length: {len(transcription_result.get("text", ""))} chars')
                print(f'[AssemblyAI] Has summary: {bool(transcription_result.get("summary"))}')
                print(f'[AssemblyAI] Utterances: {len(transcription_result.get("utterances", []))}')
                print(f'[AssemblyAI] Words: {len(transcription_result.get("words", []))}')
                print(f'[AssemblyAI] Language: {transcription_result.get("language_code", "unknown")}')
                print(f'[AssemblyAI] Duration: {transcription_result.get("audio_duration", "unknown")}s')
                print(f'[AssemblyAI] ==========================================')
                return transcription_result
            elif status == 'error':
                error_msg = transcription_result.get('error', 'Unknown error')
                print(f'[AssemblyAI] ❌ Transcription failed: {error_msg}')
                print(f'[AssemblyAI] ==========================================')
                raise RuntimeError(f"Transcription failed: {error_msg}")
            else:
                # Still processing - wait and retry
                attempt += 1
                if attempt < max_attempts:
                    print(f'[AssemblyAI] ⏳ Status: {status}, waiting 3 seconds... (attempt {attempt}/{max_attempts})')
                    time.sleep(3)
                else:
                    print(f'[AssemblyAI] ⚠ WARNING: Transcript timed out after {max_attempts} attempts')
                    print(f'[AssemblyAI] ==========================================')
                    return None
                    
    except requests.exceptions.RequestException as e:
        print(f'[AssemblyAI] ❌ ERROR: Failed to fetch transcript {transcript_id}: {e}')
        print(f'[AssemblyAI] ==========================================')
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
            print(f'[AssemblyAI] ✅ Found transcript ID in data: {transcript_id}')
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
                            print(f'[AssemblyAI] ✅ Extracted transcript ID from URL: {potential_id}')
                            return potential_id
        
        # Method 3: Check provider metadata for assembly_ai_v3_streaming (as per demo project)
        provider = transcript_node.get('provider', {})
        if isinstance(provider, dict):
            # Check if it's AssemblyAI v3 streaming (as per zoomBot.js demo)
            # The demo uses assembly_ai_v3_streaming, not assembly_ai_async_chunked
            assembly_ai_data = provider.get('assembly_ai_v3_streaming')
            if assembly_ai_data:
                print(f'[AssemblyAI] Found assembly_ai_v3_streaming provider (as per demo)')
                # Check metadata for transcript ID
                metadata = transcript_node.get('metadata', {})
                transcript_id = metadata.get('transcript_id') or metadata.get('assemblyai_transcript_id')
                if transcript_id:
                    print(f'[AssemblyAI] ✅ Found transcript ID in metadata: {transcript_id}')
                    return transcript_id
                
                # Also check the provider data itself
                if isinstance(assembly_ai_data, dict):
                    transcript_id = assembly_ai_data.get('transcript_id') or assembly_ai_data.get('id')
                    if transcript_id:
                        print(f'[AssemblyAI] ✅ Found transcript ID in provider data: {transcript_id}')
                        return transcript_id
            
            # Fallback: Check for assembly_ai_async_chunked (older format)
            assembly_ai_async = provider.get('assembly_ai_async_chunked')
            if assembly_ai_async:
                print(f'[AssemblyAI] Found assembly_ai_async_chunked provider (fallback)')
                metadata = transcript_node.get('metadata', {})
                transcript_id = metadata.get('transcript_id') or metadata.get('assemblyai_transcript_id')
                if transcript_id:
                    print(f'[AssemblyAI] ✅ Found transcript ID in metadata: {transcript_id}')
                    return transcript_id
        
        # Method 4: Check if there's a direct transcript ID field in the node
        transcript_id = transcript_node.get('transcript_id') or transcript_node.get('id')
        if transcript_id:
            print(f'[AssemblyAI] ✅ Found transcript ID in node: {transcript_id}')
            return transcript_id
    
    print('[AssemblyAI] ⚠ WARNING: Could not find AssemblyAI transcript ID in bot data')
    print('[AssemblyAI] Checked all methods: data.id, provider URL, metadata, node.id')
    return None


def get_audio_url_from_bot(bot_json: Dict[str, Any]) -> Optional[str]:
    """
    Extract audio file URL from bot data for submitting to AssemblyAI
    
    Args:
        bot_json: Full bot data from Recall.ai
        
    Returns:
        Audio file URL if found, None otherwise
    """
    recordings = bot_json.get('recordings', [])
    
    for recording in recordings:
        media_shortcuts = recording.get('media_shortcuts', {})
        
        # Check for audio_mixed download URL
        audio_mixed = media_shortcuts.get('audio_mixed', {})
        if audio_mixed:
            data = audio_mixed.get('data', {})
            download_url = data.get('download_url') or data.get('url')
            if download_url:
                print(f'[AssemblyAI] ✅ Found audio URL: {download_url}')
                return download_url
        
        # Check for audio_mixed_raw
        audio_mixed_raw = media_shortcuts.get('audio_mixed_raw', {})
        if audio_mixed_raw:
            data = audio_mixed_raw.get('data', {})
            download_url = data.get('download_url') or data.get('url')
            if download_url:
                print(f'[AssemblyAI] ✅ Found audio URL (raw): {download_url}')
                return download_url
        
        # Check recordings array for audio files
        artifacts = recording.get('artifacts', [])
        for artifact in artifacts:
            if artifact.get('type') in ['audio_mixed', 'audio_mixed_raw']:
                download_url = artifact.get('download_url') or artifact.get('url')
                if download_url:
                    print(f'[AssemblyAI] ✅ Found audio URL in artifacts: {download_url}')
                    return download_url
    
    print('[AssemblyAI] ⚠ WARNING: Could not find audio URL in bot data')
    return None


def submit_audio_for_transcription_with_summary(audio_url: str) -> Optional[str]:
    """
    Submit audio URL to AssemblyAI for transcription with summarization and action items
    
    Args:
        audio_url: URL to the audio file
        
    Returns:
        AssemblyAI transcript ID if submission successful, None otherwise
    """
    base_url = "https://api.assemblyai.com"
    api_key = os.getenv('ASSEMBLY_AI_API_KEY', '')
    
    if not api_key:
        print('[AssemblyAI] ⚠ WARNING: ASSEMBLY_AI_API_KEY not set')
        return None
    
    submit_endpoint = f"{base_url}/v2/transcript"
    
    headers = {
        "authorization": api_key,
        "content-type": "application/json"
    }
    
    # Request transcription with summarization and action items
    payload = {
        "audio_url": audio_url,
        "summarization": True,
        "summary_model": "informative",  # Options: "informative", "conversational", "catchy"
        "summary_type": "paragraph",  # Options: "bullets", "bullets_verbose", "gist", "headline", "paragraph"
        "action_items": True,  # Enable action items extraction
        "speaker_labels": True,  # Enable speaker identification
        "punctuate": True,
        "format_text": True
    }
    
    try:
        print(f'[AssemblyAI] ==========================================')
        print(f'[AssemblyAI] 📤 SUBMITTING AUDIO FOR TRANSCRIPTION')
        print(f'[AssemblyAI] Audio URL: {audio_url[:100]}...')
        print(f'[AssemblyAI] Features: Summarization + Action Items')
        print(f'[AssemblyAI] ==========================================')
        
        response = requests.post(submit_endpoint, json=payload, headers=headers)
        response.raise_for_status()
        
        result = response.json()
        transcript_id = result.get('id')
        
        if transcript_id:
            print(f'[AssemblyAI] ✅ Audio submitted successfully!')
            print(f'[AssemblyAI] Transcript ID: {transcript_id}')
            print(f'[AssemblyAI] Status: {result.get("status", "unknown")}')
            print(f'[AssemblyAI] ==========================================')
            return transcript_id
        else:
            print(f'[AssemblyAI] ❌ ERROR: No transcript ID in response')
            print(f'[AssemblyAI] Response: {result}')
            return None
            
    except requests.exceptions.RequestException as e:
        print(f'[AssemblyAI] ❌ ERROR: Failed to submit audio: {e}')
        if hasattr(e, 'response') and e.response is not None:
            print(f'[AssemblyAI] Response: {e.response.text}')
        return None


def generate_summary_and_action_items_from_transcript(transcript_text: str) -> Optional[Dict[str, Any]]:
    """
    Use AssemblyAI LeMUR API to generate summary and action items from existing transcript text
    
    This is a fallback if we can't get audio URL or if audio submission fails
    
    Args:
        transcript_text: The transcript text we already have
        
    Returns:
        Dict with summary and action_items, or None if failed
    """
    base_url = "https://api.assemblyai.com"
    api_key = os.getenv('ASSEMBLY_AI_API_KEY', '')
    
    if not api_key:
        print('[AssemblyAI] ⚠ WARNING: ASSEMBLY_AI_API_KEY not set')
        return None
    
    # LeMUR endpoint for generating summaries and action items
    lemur_endpoint = f"{base_url}/lemur/v3/generate"
    
    headers = {
        "authorization": api_key,
        "content-type": "application/json"
    }
    
    payload = {
        "transcript_ids": [],  # Not using transcript IDs, using text directly
        "prompt": f"""Please provide:
1. A comprehensive summary of this meeting transcript
2. A list of action items mentioned in the meeting

Format your response as JSON with the following structure:
{{
  "summary": "detailed summary here",
  "action_items": [
    {{"text": "action item 1", "speaker": "speaker name if mentioned"}},
    {{"text": "action item 2", "speaker": "speaker name if mentioned"}}
  ]
}}

Transcript:
{transcript_text[:5000]}"""  # Limit to 5000 chars for prompt
    }
    
    try:
        print(f'[AssemblyAI] ==========================================')
        print(f'[AssemblyAI] 🤖 GENERATING SUMMARY & ACTION ITEMS')
        print(f'[AssemblyAI] Using LeMUR API')
        print(f'[AssemblyAI] ==========================================')
        
        response = requests.post(lemur_endpoint, json=payload, headers=headers)
        response.raise_for_status()
        
        result = response.json()
        # LeMUR returns text, we need to parse it
        response_text = result.get('response', '')
        
        # Try to parse JSON from response
        import json
        try:
            # Extract JSON from response text
            if '{' in response_text and '}' in response_text:
                json_start = response_text.find('{')
                json_end = response_text.rfind('}') + 1
                json_str = response_text[json_start:json_end]
                parsed = json.loads(json_str)
                
                print(f'[AssemblyAI] ✅ Generated summary and action items')
                print(f'[AssemblyAI] Summary length: {len(parsed.get("summary", ""))} chars')
                print(f'[AssemblyAI] Action items: {len(parsed.get("action_items", []))} items')
                return parsed
        except json.JSONDecodeError:
            # If JSON parsing fails, extract summary and action items manually
            print(f'[AssemblyAI] ⚠ Could not parse JSON, extracting manually')
            # Fallback: return response text as summary
            return {
                "summary": response_text,
                "action_items": []
            }
            
    except requests.exceptions.RequestException as e:
        print(f'[AssemblyAI] ❌ ERROR: Failed to generate summary: {e}')
        return None
