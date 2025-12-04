"""
WebSocket consumers for receiving real-time data from Recall.ai bots.
Handles audio, video, and transcript streams similar to meeting-bot implementation.
"""
import json
import base64
import os
from channels.generic.websocket import AsyncWebsocketConsumer


class BotRealtimeConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for receiving real-time bot data:
    - audio_mixed_raw.data: Base64 PCM audio chunks
    - video_separate_png.data: Base64 PNG frames
    - video_separate_h264.data: Base64 H.264 chunks
    - transcript.data: Real-time transcripts
    """
    
    async def connect(self):
        """Handle WebSocket connection with token authentication"""
        # Get token from query string
        query_string = self.scope.get('query_string', b'').decode('utf-8')
        token = None
        for param in query_string.split('&'):
            if '=' in param:
                key, value = param.split('=', 1)
                if key == 'token':
                    token = value
                    break
        
        # Verify token
        expected_token = os.getenv('WS_TOKEN', 'dev-secret')
        if token != expected_token:
            await self.close(code=1008)  # Policy violation
            return
        
        await self.accept()
        client = self.scope.get('client', ['unknown'])
        print(f'[ws] connected {client}')
    
    async def disconnect(self, close_code):
        """Handle WebSocket disconnection"""
        print(f'[ws] disconnected (code: {close_code})')
    
    async def receive(self, text_data=None, bytes_data=None):
        """Handle incoming WebSocket messages"""
        payload = None
        
        if text_data:
            payload = text_data
        elif bytes_data:
            try:
                payload = bytes_data.decode('utf-8', errors='replace')
            except Exception:
                payload = None
        
        if not payload:
            print('[ws] non-text frame or empty')
            return
        
        try:
            event_data = json.loads(payload)
        except json.JSONDecodeError:
            payload_preview = (payload[:200] + '…') if len(payload) > 200 else payload
            print(f'[ws] bad-json: {payload_preview}')
            return
        
        # Parse event structure (similar to meeting-bot)
        event = event_data.get('event')
        data = event_data.get('data') or {}
        event_data_inner = data.get('data') or {}
        timestamp = (event_data_inner.get('timestamp') or {}).get('absolute')
        buffer = event_data_inner.get('buffer')
        
        # Handle different event types
        if event == 'audio_mixed_raw.data' and buffer:
            try:
                audio_bytes = base64.b64decode(buffer)
                n = len(audio_bytes)
                dur_ms = n // 32  # Approximate duration
                print(f'[ws] audio {dur_ms}ms {n/1024:.1f}KB ts={timestamp}')
            except Exception as e:
                print(f'[ws] error decoding audio: {e}')
        
        elif event == 'video_separate_png.data' and buffer:
            try:
                raw = base64.b64decode(buffer)
                dims = '?'
                # Parse PNG dimensions
                if raw[:8] == b'\x89PNG\r\n\x1a\n' and raw[12:16] == b'IHDR':
                    w = int.from_bytes(raw[16:20], 'big')
                    h = int.from_bytes(raw[20:24], 'big')
                    dims = f'{w}x{h}'
                participant = event_data_inner.get('participant') or {}
                p_id = participant.get('id', '?')
                p_name = participant.get('name', '?')
                print(f'[ws] png {dims} {len(raw)/1024:.1f}KB {p_id}:{p_name} ts={timestamp}')
            except Exception as e:
                print(f'[ws] error decoding PNG: {e}')
        
        elif event == 'video_separate_h264.data' and buffer:
            try:
                h264_bytes = base64.b64decode(buffer)
                n = len(h264_bytes)
                participant = event_data_inner.get('participant') or {}
                p_id = participant.get('id', '?')
                p_name = participant.get('name', '?')
                print(f'[ws] h264 {n/1024:.1f}KB {p_id}:{p_name} ts={timestamp}')
            except Exception as e:
                print(f'[ws] error decoding H264: {e}')
        
        elif event == 'transcript.data':
            words = event_data_inner.get('words') or []
            text = ' '.join((w.get('text', '') for w in words)) or event_data_inner.get('text', '')
            participant = event_data_inner.get('participant') or {}
            who = participant.get('name', '?')
            print(f'[ws] transcript {who}: {text}')
        
        else:
            print(f'[ws] event {event}')


class CalendarUpdatesConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for real-time calendar updates.
    Sends updates to frontend when calendar events are synced via webhooks.
    """
    
    async def connect(self):
        """Handle WebSocket connection"""
        # Get userId from query string
        query_string = self.scope.get('query_string', b'').decode('utf-8')
        self.user_id = None
        for param in query_string.split('&'):
            if '=' in param:
                key, value = param.split('=', 1)
                if key == 'userId':
                    self.user_id = value
                    break
        
        if not self.user_id:
            await self.close(code=1008, reason='userId parameter required')
            return
        
        # Add to group for this user
        self.group_name = f'calendar_updates_{self.user_id}'
        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )
        
        await self.accept()
        print(f'[ws] Calendar updates consumer connected for user {self.user_id}')
    
    async def disconnect(self, close_code):
        """Handle WebSocket disconnection"""
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(
                self.group_name,
                self.channel_name
            )
        print(f'[ws] Calendar updates consumer disconnected (code: {close_code})')
    
    async def receive(self, text_data=None, bytes_data=None):
        """Handle incoming WebSocket messages (ping/pong for keepalive)"""
        if text_data:
            try:
                data = json.loads(text_data)
                if data.get('type') == 'ping':
                    await self.send(text_data=json.dumps({'type': 'pong'}))
            except:
                pass
    
    async def calendar_update(self, event):
        """Send calendar update to WebSocket"""
        message = event['message']
        await self.send(text_data=json.dumps({
            'type': 'calendar_update',
            'data': message
        }))
