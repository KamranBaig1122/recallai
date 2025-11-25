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

