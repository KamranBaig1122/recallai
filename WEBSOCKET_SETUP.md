# WebSocket Setup Guide

## Overview

The Django project now supports WebSocket connections for receiving real-time data from Recall.ai bots, including:
- **Audio streams**: `audio_mixed_raw.data` - Base64 PCM audio chunks
- **Video streams**: `video_separate_png.data` or `video_separate_h264.data` - Base64 video frames
- **Transcripts**: `transcript.data` - Real-time transcript data

This is implemented using Django Channels, similar to the meeting-bot FastAPI server.

## Installation

1. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
   
   This installs:
   - `channels` - Django Channels for WebSocket support
   - `channels-redis` - Redis backend for Channels (optional, uses in-memory for dev)

2. **Run migrations** (if needed):
   ```bash
   python manage.py migrate
   ```

## Configuration

### Environment Variables

Make sure these are set in your `.env`:

```bash
PUBLIC_URL=https://your-ngrok-domain.ngrok-free.dev
WS_TOKEN=dev-secret  # Token for WebSocket authentication
```

### Settings

The following are already configured in `recallai/settings.py`:

- `INSTALLED_APPS` includes `'channels'`
- `ASGI_APPLICATION = 'recallai.asgi.application'`
- `CHANNEL_LAYERS` configured for in-memory (development)

## Running the Server

### Development (with WebSocket support)

Use an ASGI server instead of the default Django development server:

```bash
# Install daphne (ASGI server)
pip install daphne

# Run with daphne
daphne -b 0.0.0.0 -p 3003 recallai.asgi:application
```

Or use uvicorn (if you have it):

```bash
uvicorn recallai.asgi:application --host 0.0.0.0 --port 3003
```

### Production

For production, use:
- **Daphne**: `daphne -b 0.0.0.0 -p 3003 recallai.asgi:application`
- **Uvicorn**: `uvicorn recallai.asgi:application --host 0.0.0.0 --port 3003`
- **Gunicorn with Uvicorn workers**: `gunicorn recallai.asgi:application -k uvicorn.workers.UvicornWorker`

## WebSocket Endpoint

The WebSocket endpoint is available at:

```
wss://your-public-url/ws/rt?token=dev-secret
```

Or for local development:

```
ws://localhost:3003/ws/rt?token=dev-secret
```

## How It Works

1. **Bot Creation**: When a bot is created, the WebSocket URL is included in the recording config:
   ```python
   {
     "type": "websocket",
     "url": "wss://your-public-url/ws/rt?token=dev-secret",
     "events": ["audio_mixed_raw.data", "video_separate_png.data", "transcript.data"]
   }
   ```

2. **Connection**: Recall.ai connects to your WebSocket endpoint when the bot joins a meeting

3. **Data Reception**: The `BotRealtimeConsumer` receives and processes:
   - Audio chunks (logs duration and size)
   - Video frames (PNG or H.264, logs dimensions and size)
   - Transcripts (logs speaker and text)

4. **Logging**: All received data is logged to console with `[ws]` prefix

## Testing

### Test WebSocket Connection

You can test the WebSocket endpoint using a WebSocket client:

```python
import asyncio
import websockets
import json

async def test_websocket():
    uri = "ws://localhost:3003/ws/rt?token=dev-secret"
    async with websockets.connect(uri) as websocket:
        print("Connected!")
        # Send a test message
        await websocket.send(json.dumps({"test": "message"}))
        # Receive response
        response = await websocket.recv()
        print(f"Received: {response}")

asyncio.run(test_websocket())
```

### Check Server Logs

When a bot connects and sends data, you'll see logs like:

```
[ws] connected ('127.0.0.1', 54321)
[ws] audio 100ms 3.2KB ts=2025-11-29T12:00:00Z
[ws] transcript Alice: Hello everyone
[ws] png 1920x1080 45.2KB 123:Alice ts=2025-11-29T12:00:01Z
```

## Troubleshooting

### WebSocket not connecting

1. **Check server is running with ASGI**:
   - Don't use `python manage.py runserver` (it doesn't support WebSockets)
   - Use `daphne` or `uvicorn` instead

2. **Check token**:
   - Ensure `WS_TOKEN` matches the token in the WebSocket URL
   - Default is `dev-secret`

3. **Check ngrok**:
   - Ensure ngrok is running and exposing port 3003
   - Verify `PUBLIC_URL` matches your ngrok domain

### No data received

1. **Check bot configuration**:
   - Verify bot was created with WebSocket URL in recording config
   - Check that events are subscribed: `["audio_mixed_raw.data", "transcript.data"]`

2. **Check server logs**:
   - Look for `[ws] connected` message
   - Check for any error messages

### Production Considerations

For production, use Redis as the channel layer:

```python
# settings.py
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels_redis.core.RedisChannelLayer',
        'CONFIG': {
            "hosts": [('127.0.0.1', 6379)],
        },
    },
}
```

## Differences from Meeting-Bot Server

| Feature | Meeting-Bot (FastAPI) | Django (Channels) |
|---------|----------------------|-------------------|
| WebSocket Support | Native FastAPI | Django Channels |
| Server | Uvicorn | Daphne/Uvicorn |
| Routing | FastAPI routes | Channels routing |
| Consumer | FastAPI handler | Channels consumer |

Both implementations handle the same data types and events.

