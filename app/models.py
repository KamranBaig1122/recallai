import uuid
import json
from django.db import models
from django.db.models import JSONField


class User(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    email = models.EmailField(unique=True)
    password = models.CharField(max_length=255)  # In production, use hashed passwords
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'users'
    
    def get_calendars(self):
        return Calendar.objects.filter(user_id=self.id)


class Calendar(models.Model):
    PLATFORM_CHOICES = [
        ('google_calendar', 'Google Calendar'),
        ('microsoft_outlook', 'Microsoft Outlook'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user_id = models.UUIDField()
    platform = models.CharField(max_length=20, choices=PLATFORM_CHOICES)
    recall_id = models.CharField(max_length=255, unique=True)
    recall_data = JSONField(default=dict)
    auto_record_external_events = models.BooleanField(default=False)
    auto_record_only_confirmed_events = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'calendars'
    
    @property
    def email(self):
        return self.recall_data.get('platform_email')
    
    @property
    def status(self):
        return self.recall_data.get('status')
    
    def get_connect_url(self):
        from app.logic.oauth import build_google_calendar_oauth_url, build_microsoft_outlook_oauth_url
        state = {'userId': str(self.user_id), 'calendarId': str(self.id)}
        if self.platform == 'google_calendar':
            return build_google_calendar_oauth_url(state)
        else:
            return build_microsoft_outlook_oauth_url(state)


class CalendarEvent(models.Model):
    PLATFORM_CHOICES = [
        ('google_calendar', 'Google Calendar'),
        ('microsoft_outlook', 'Microsoft Outlook'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    calendar_id = models.UUIDField()
    platform = models.CharField(max_length=20, choices=PLATFORM_CHOICES)
    recall_id = models.CharField(max_length=255, unique=True)
    recall_data = JSONField(default=dict)
    should_record_automatic = models.BooleanField(default=False)
    should_record_manual = models.BooleanField(null=True, default=None)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'calendar_events'
    
    @property
    def start_time(self):
        from datetime import datetime
        start = self.recall_data.get('start_time')
        return datetime.fromisoformat(start) if start else None
    
    @property
    def end_time(self):
        from datetime import datetime
        end = self.recall_data.get('end_time')
        return datetime.fromisoformat(end) if end else None
    
    @property
    def title(self):
        raw = self.recall_data.get('raw', {})
        if self.platform == 'google_calendar':
            return raw.get('summary', '')
        else:
            return raw.get('subject', '')
    
    @property
    def meeting_url(self):
        return self.recall_data.get('meeting_url')
    
    @property
    def bots(self):
        return self.recall_data.get('bots', [])


class CalendarWebhook(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    calendar_id = models.UUIDField()
    event = models.CharField(max_length=255)
    payload = JSONField(default=dict)
    received_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'calendar_webhooks'


class BotRecording(models.Model):
    """Stores bot recording data and links to artifacts"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    bot_id = models.CharField(max_length=255, unique=True)  # Recall.ai bot ID
    calendar_event_id = models.UUIDField(null=True, blank=True)  # Link to calendar event
    recall_data = JSONField(default=dict)  # Full bot data from Recall.ai
    status = models.CharField(max_length=50, default='pending')  # pending, processing, completed, failed
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'bot_recordings'
    
    @property
    def recordings(self):
        """Get recordings array from recall_data"""
        return self.recall_data.get('recordings', [])


class RecordingArtifact(models.Model):
    """Stores downloaded artifacts (video, transcript, audio)"""
    ARTIFACT_TYPES = [
        ('video_mixed', 'Video Mixed'),
        ('audio_mixed', 'Audio Mixed'),
        ('transcript', 'Transcript'),
        ('provider_transcript', 'Provider Transcript'),
        ('audio_separate', 'Audio Separate'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    bot_recording_id = models.UUIDField()  # Foreign key to BotRecording
    recording_id = models.CharField(max_length=255)  # Recall.ai recording ID
    artifact_type = models.CharField(max_length=50, choices=ARTIFACT_TYPES)
    
    # File storage
    # Using relative paths to keep under database limit
    file_path = models.CharField(max_length=1000, null=True, blank=True)  # Local file path (relative to BASE_DIR)
    file_size = models.BigIntegerField(null=True, blank=True)  # File size in bytes
    file_format = models.CharField(max_length=50, null=True, blank=True)  # mp4, json, mp3, etc.
    
    # Metadata
    download_url = models.URLField(null=True, blank=True)  # Original download URL (short-lived)
    metadata = JSONField(default=dict)  # Additional metadata
    
    downloaded_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'recording_artifacts'
        unique_together = [['bot_recording_id', 'recording_id', 'artifact_type']]