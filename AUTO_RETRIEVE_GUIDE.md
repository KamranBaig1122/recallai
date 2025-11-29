# Auto-Retrieve Bot Recordings Guide

This guide explains the automatic retrieval system for bot recordings.

## Overview

The system automatically retrieves bot recordings when:
1. **Bot creation**: A placeholder `BotRecording` is created when a bot is scheduled
2. **Bot completion**: When a bot finishes (via webhook `bot.status_change` with code `done` or `recording_done`)
3. **Manual trigger**: Via management command or API endpoint

## How It Works

### 1. Bot Creation Flow

When a bot is created for a calendar event:
- Bot is created via Recall.ai API
- A `BotRecording` entry is created with status `pending`
- Bot ID is stored in calendar event's `recall_data.bots[]`

### 2. Auto-Retrieve on Completion

When a bot completes (webhook event `bot.status_change` with code `done`):
- Webhook handler detects completion
- Triggers `auto_retrieve_bot()` in background thread
- Retrieves full bot data from Recall.ai
- Downloads all artifacts (video, transcript, audio)
- Updates `BotRecording` status to `completed`

### 3. Folder Structure

Artifacts are stored in:
```
artifacts/
  <bot_id>/
    <recording_id>/
      <recording_id>_video.mp4
      <recording_id>_transcript.json
      <recording_id>_audio.mp3
```

Example:
```
artifacts/
  6134af87-3439-483b-b94a-de5a01c42db2/
    4fbb3511-f6fe-4170-9fb2-d929c37ee163/
      4fbb3511-f6fe-4170-9fb2-d929c37ee163_video.mp4
      4fbb3511-f6fe-4170-9fb2-d929c37ee163_transcript.json
```

## Manual Retrieval

### Management Command

Check and retrieve all completed bots:
```bash
python manage.py retrieve_completed_bots
```

This command:
- Finds all calendar events with bots
- Checks if recordings are ready
- Retrieves and downloads artifacts
- Updates database

### API Endpoint

Manually retrieve a specific bot:
```bash
curl http://localhost:3003/retrieve/<bot_id>
```

## Viewing Recordings

### List All Recordings

Visit: `http://localhost:3003/recordings`

Features:
- Filter by status (pending, processing, completed)
- Filter by calendar event
- View bot ID, event info, status, artifacts
- Links to view individual recordings

### View Individual Recording

Visit: `http://localhost:3003/recording/<recording_id>`

Features:
- Video player
- Interactive transcript
- Download links
- Recording metadata

## Database Models

### BotRecording

- `bot_id`: Recall.ai bot ID (unique)
- `calendar_event_id`: Link to calendar event
- `recall_data`: Full bot JSON from Recall.ai
- `status`: pending, processing, completed, failed

### RecordingArtifact

- `bot_recording_id`: Foreign key to BotRecording
- `recording_id`: Recall.ai recording ID
- `artifact_type`: video_mixed, audio_mixed, transcript
- `file_path`: Local file path
- `file_size`: File size in bytes
- `download_url`: Original download URL (short-lived)

## Webhook Integration

The webhook handler (`/wh`) automatically triggers retrieval when:
- Event: `bot.status_change`
- Code: `done`, `recording_done`, or `bot.done`

The retrieval runs in a background thread to avoid blocking the webhook response.

## Periodic Checking

For bots that might not trigger webhooks, run the management command periodically:

**Cron example** (every 5 minutes):
```bash
*/5 * * * * cd /path/to/project && python manage.py retrieve_completed_bots
```

**Windows Task Scheduler**:
- Create a task to run every 5 minutes
- Command: `python manage.py retrieve_completed_bots`
- Working directory: Project root

## Troubleshooting

### Bot not auto-retrieving

1. Check webhook is receiving events:
   - Look for `[bot-wh] bot.status_change` in logs
   - Verify webhook URL is correct in bot config

2. Check bot status:
   ```bash
   curl http://localhost:3003/retrieve/<bot_id>
   ```

3. Manually trigger retrieval:
   ```bash
   python manage.py retrieve_completed_bots
   ```

### Downloads failing

1. Check download URLs are valid (they expire after a few days)
2. Call `/retrieve/<bot_id>` to refresh URLs
3. Check file permissions on `artifacts/` directory
4. Verify disk space

### Recordings not showing

1. Check `BotRecording` exists in database
2. Verify `status` is `completed`
3. Check `RecordingArtifact` entries exist
4. Verify files exist in `artifacts/` directory

## Example Workflow

1. **Calendar event created** → Bot scheduled with `join_at`
2. **Bot joins meeting** → Status: `in_call_recording`
3. **Meeting ends** → Webhook: `bot.status_change` with code `done`
4. **Auto-retrieve triggered** → Downloads video, transcript, audio
5. **Recording available** → View at `/recording/<recording_id>`

## Notes

- Download URLs from Recall.ai expire after a few days
- Always call `/retrieve/<bot_id>` to refresh URLs if needed
- Files are stored locally, so they persist even after URLs expire
- Large video files may take time to download
- Auto-retrieve runs in background to avoid blocking webhooks

