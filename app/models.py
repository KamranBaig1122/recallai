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
    
    STATUS_CHOICES = [
        ('connected', 'Connected'),
        ('disconnected', 'Disconnected'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user_id = models.UUIDField()  # Keep for backward compatibility during migration
    backend_user_id = models.UUIDField(null=True, blank=True, db_index=True)  # Invite-ellie-backend user ID
    platform = models.CharField(max_length=20, choices=PLATFORM_CHOICES)
    recall_id = models.CharField(max_length=255, unique=True)
    recall_data = JSONField(default=dict)
    auto_record_external_events = models.BooleanField(default=False)
    auto_record_only_confirmed_events = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='connected')  # connected or disconnected
    default_folder_id = models.UUIDField(null=True, blank=True, db_index=True)  # Default folder ID for all bots created from this calendar
    default_workspace_id = models.UUIDField(null=True, blank=True, db_index=True)  # Default workspace ID for this calendar
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'calendars'
        indexes = [
            models.Index(fields=['backend_user_id']),
            models.Index(fields=['status']),
        ]
    
    @property
    def email(self):
        return self.recall_data.get('platform_email')
    
    @property
    def recall_status(self):
        """Get status from recall_data (for backward compatibility)"""
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
    calendar_id = models.UUIDField()  # Keep for relationship
    backend_user_id = models.UUIDField(null=True, blank=True, db_index=True)  # Invite-ellie-backend user ID
    platform = models.CharField(max_length=20, choices=PLATFORM_CHOICES)
    recall_id = models.CharField(max_length=255, unique=True)
    recall_data = JSONField(default=dict)
    should_record_automatic = models.BooleanField(default=False)
    should_record_manual = models.BooleanField(null=True, default=None)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'calendar_events'
        indexes = [
            models.Index(fields=['backend_user_id']),
            models.Index(fields=['calendar_id']),
        ]
    
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
        # For manual meetings, title is stored directly in recall_data['title']
        if 'title' in self.recall_data:
            return self.recall_data.get('title', '')
        # For calendar-synced events, title is in recall_data['raw']
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
    backend_user_id = models.UUIDField(null=True, blank=True, db_index=True)  # Invite-ellie-backend user ID
    workspace_id = models.UUIDField(null=True, blank=True, db_index=True)  # Invite-ellie-backend workspace ID (required for bot creation)
    folder_id = models.UUIDField(null=True, blank=True, db_index=True)  # Invite-ellie-backend folder ID (optional - if None, goes to unresolved)
    recall_data = JSONField(default=dict)  # Full bot data from Recall.ai
    status = models.CharField(max_length=50, default='pending')  # pending, processing, completed, failed
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'bot_recordings'
        indexes = [
            models.Index(fields=['backend_user_id']),
            models.Index(fields=['calendar_event_id']),
            models.Index(fields=['workspace_id']),
            models.Index(fields=['folder_id']),
        ]
    
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


class MeetingTranscription(models.Model):
    """Stores meeting transcriptions and summaries from AssemblyAI"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    calendar_event_id = models.UUIDField()  # Link to calendar event
    backend_user_id = models.UUIDField(null=True, blank=True, db_index=True)  # Invite-ellie-backend user ID
    workspace_id = models.UUIDField(null=True, blank=True, db_index=True)  # Invite-ellie-backend workspace ID (copied from BotRecording)
    folder_id = models.UUIDField(null=True, blank=True, db_index=True)  # Invite-ellie-backend folder ID (copied from BotRecording, None = unresolved)
    bot_id = models.CharField(max_length=255)  # Recall.ai bot ID
    assemblyai_transcript_id = models.CharField(max_length=255, null=True, blank=True)  # AssemblyAI transcript ID (not unique for real-time)
    
    # Transcription data from AssemblyAI
    transcript_data = JSONField(default=dict)  # Full transcript JSON from AssemblyAI
    transcript_text = models.TextField(null=True, blank=True)  # Full transcript text
    summary = models.TextField(null=True, blank=True)  # Summary if available
    action_items = JSONField(default=list, null=True, blank=True)  # Action items extracted from transcript
    
    # Contextual nudges and impact score (generated by Groq)
    contextual_nudges = JSONField(default=list, null=True, blank=True)  # Array of contextual nudges
    impact_score = models.FloatField(null=True, blank=True)  # Impact score (0-100) of the meeting
    
    # Metadata
    status = models.CharField(max_length=50, default='processing')  # processing, completed, failed
    language = models.CharField(max_length=10, null=True, blank=True)  # Language code (e.g., 'en')
    duration = models.FloatField(null=True, blank=True)  # Duration in seconds
    
    # Notification tracking for unresolved meetings
    notification_sent_at = models.DateTimeField(null=True, blank=True, db_index=True)  # When notification was sent
    notification_type = models.CharField(max_length=20, null=True, blank=True)  # 'in_app', 'email', or 'both'
    notification_retry_count = models.IntegerField(default=0)  # Number of retry attempts
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'meeting_transcriptions'
        # One transcription per bot per event (real-time transcripts get merged)
        unique_together = [['calendar_event_id', 'bot_id']]
        indexes = [
            models.Index(fields=['backend_user_id']),
            models.Index(fields=['calendar_event_id']),
            models.Index(fields=['bot_id']),
            models.Index(fields=['assemblyai_transcript_id']),
            models.Index(fields=['workspace_id']),
            models.Index(fields=['folder_id']),
        ]
    
    @property
    def utterances(self):
        """Get utterances array from transcript_data"""
        return self.transcript_data.get('utterances', [])
    
    @property
    def words(self):
        """Get words array from transcript_data"""
        return self.transcript_data.get('words', [])
    
    @property
    def action_items_list(self):
        """Get action items array from transcript_data or action_items field"""
        if self.action_items:
            return self.action_items
        return self.transcript_data.get('action_items', [])


class Notification(models.Model):
    """Stores in-app notifications for users"""
    NOTIFICATION_TYPES = [
        ('unresolved_meeting_notification', 'Unresolved Meeting Notification'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    backend_user_id = models.UUIDField(db_index=True)  # Invite-ellie-backend user ID
    notification_type = models.CharField(max_length=50, choices=NOTIFICATION_TYPES)
    meeting_id = models.UUIDField(null=True, blank=True, db_index=True)  # Associated meeting transcription ID
    meeting_title = models.CharField(max_length=500)
    message = models.TextField()
    read = models.BooleanField(default=False, db_index=True)
    read_at = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'notifications'
        indexes = [
            models.Index(fields=['backend_user_id', 'read']),
            models.Index(fields=['backend_user_id', '-created_at']),
            models.Index(fields=['meeting_id']),
        ]
        ordering = ['-created_at']
    
    def __str__(self):
        return f'Notification {self.id} for user {self.backend_user_id} - {self.notification_type}'