# Recording Retrieve & Download Guide

This guide explains how to retrieve bot recordings, download artifacts (video, transcript, audio), and view them in the frontend.

## Overview

The system now includes:
1. **Database Models**: `BotRecording` and `RecordingArtifact` to store recording data and downloaded files
2. **Retrieve Endpoint**: `/retrieve/<bot_id>` - Fetches bot data from Recall.ai and downloads artifacts
3. **View Endpoint**: `/recording/<recording_id>` - Displays video and transcript in the frontend
4. **Download Service**: Automatically downloads video, transcript, and audio files

## Setup

### 1. Install Dependencies

Make sure all dependencies are installed:
```bash
pip install -r requirements.txt
```

### 2. Run Migrations

Create and apply database migrations for the new models:
```bash
python manage.py makemigrations
python manage.py migrate
```

### 3. Create Artifacts Directory

The system will automatically create an `artifacts/` directory in your project root to store downloaded files.

## Usage

### Retrieve Bot Data and Download Artifacts

**Endpoint**: `GET /retrieve/<bot_id>`

This endpoint:
1. Fetches bot data from Recall.ai API
2. Saves bot data to database (`BotRecording`)
3. Extracts media shortcut URLs (video, transcript, audio)
4. Downloads files to local storage
5. Saves artifact metadata to database (`RecordingArtifact`)

**Example**:
```bash
curl http://localhost:3003/retrieve/abc123-bot-id
```

**Response**:
```json
{
  "ok": true,
  "bot_id": "abc123-bot-id",
  "bot_data": { ... },
  "recording_id": "uuid-of-recording",
  "download_results": {
    "downloaded": ["transcript-recording-id", "video-recording-id"],
    "failed": [],
    "skipped": []
  }
}
```

### View Recording in Frontend

**Endpoint**: `GET /recording/<recording_id>`

Displays a page with:
- Video player (if video is available)
- Interactive transcript (click words to seek video)
- Download links for video, transcript, and audio
- Recording metadata

**Example**:
```
http://localhost:3003/recording/123e4567-e89b-12d3-a456-426614174000
```

### Serve Video File

**Endpoint**: `GET /recording/<recording_id>/video`

Serves the downloaded video file for playback.

### Serve Transcript File

**Endpoint**: `GET /recording/<recording_id>/transcript`

Serves the downloaded transcript JSON file.

## Database Models

### BotRecording

Stores bot recording data:
- `bot_id`: Recall.ai bot ID
- `calendar_event_id`: Link to calendar event (optional)
- `recall_data`: Full bot data from Recall.ai (JSON)
- `status`: pending, processing, completed, failed

### RecordingArtifact

Stores downloaded artifacts:
- `bot_recording_id`: Foreign key to BotRecording
- `recording_id`: Recall.ai recording ID
- `artifact_type`: video_mixed, audio_mixed, transcript, audio_separate
- `file_path`: Local file path
- `file_size`: File size in bytes
- `file_format`: mp4, json, mp3, etc.
- `download_url`: Original download URL (short-lived)
- `downloaded_at`: Timestamp when downloaded

## File Storage

Downloaded files are stored in:
```
project_root/
  artifacts/
    <recording_id>/
      <recording_id>_video.mp4
      <recording_id>_transcript.json
      <recording_id>_audio.mp3
```

## Frontend Features

The recording view page (`/recording/<recording_id>`) includes:

1. **Video Player**: HTML5 video player with controls
2. **Interactive Transcript**: 
   - Click words to seek video to that timestamp
   - Words highlight as video plays
   - Auto-scrolls to current word
3. **Download Links**: Direct download links for all artifacts
4. **Metadata Display**: Bot ID, status, file sizes, timestamps

## Integration with Calendar Events

When a bot is created for a calendar event, the system automatically links the recording to the event. The recording view page will display:
- Event title
- Event date/time
- Link back to calendar event

## Automatic Download

The retrieve endpoint automatically downloads all available artifacts:
- **Video Mixed**: Combined video of all participants
- **Audio Mixed**: Combined audio track
- **Transcript**: JSON file with word-level timestamps

## Error Handling

- If download fails, the error is logged and the artifact is marked as failed
- The retrieve endpoint continues even if some downloads fail
- Frontend gracefully handles missing artifacts

## Example Workflow

1. **Bot joins meeting** (automatically via `join_at` parameter)
2. **Meeting ends** - Recall.ai processes recording
3. **Retrieve bot data**:
   ```bash
   curl http://localhost:3003/retrieve/<bot_id>
   ```
4. **View recording**:
   ```
   http://localhost:3003/recording/<recording_id>
   ```

## Notes

- Download URLs from Recall.ai are **short-lived** (expire after a few days)
- Always call `/retrieve/<bot_id>` to refresh download URLs if they expire
- Files are stored locally, so they persist even after Recall.ai URLs expire
- Large video files may take time to download - the endpoint returns immediately and downloads in the background

## Troubleshooting

**Issue**: Downloads fail with 404
- **Solution**: Download URLs may have expired. Call `/retrieve/<bot_id>` again to refresh URLs.

**Issue**: Video not showing in frontend
- **Solution**: Check that video file exists in `artifacts/` directory and file permissions are correct.

**Issue**: Transcript not interactive
- **Solution**: Ensure transcript JSON has word-level timestamps. Some transcript formats may not support seeking.

