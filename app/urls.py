from django.urls import path
from app.views import root, auth, oauth, calendar, calendar_event, webhooks
import app.views.bot_webhooks as bot_webhooks
from app.views import static_files, bot_recordings, recordings_list

urlpatterns = [
    # Root
    path('', root.root_view, name='root'),
    
    # Authentication
    path('sign-in', auth.sign_in, name='sign-in'),
    path('sign-up', auth.sign_up, name='sign-up'),
    path('sign-out', auth.sign_out, name='sign-out'),
    
    # Calendar
    path('calendar/<uuid:calendar_id>', calendar.calendar_get, name='calendar-get'),
    path('calendar/<uuid:calendar_id>/sync', calendar.calendar_sync, name='calendar-sync'),
    path('calendar/<uuid:calendar_id>/update', calendar.calendar_update, name='calendar-update'),
    path('calendar/<uuid:calendar_id>/delete', calendar.calendar_delete, name='calendar-delete'),
    
    # Calendar Event
    path('calendar-event/<uuid:event_id>/set-manual-record', calendar_event.set_manual_record, name='calendar-event-set-manual-record'),
    
    # OAuth Callbacks
    path('oauth-callback/google-calendar', oauth.google_calendar_callback, name='oauth-callback-google-calendar'),
    path('oauth-callback/microsoft-outlook', oauth.microsoft_outlook_callback, name='oauth-callback-microsoft-outlook'),
    
    # Calendar Webhooks (from Recall.ai for calendar sync)
    path('webhooks', webhooks.recall_calendar_updates, name='webhooks-recall-calendar-updates'),  # Simple /webhooks endpoint
    path('webhooks/recall-calendar-updates', webhooks.recall_calendar_updates, name='webhooks-recall-calendar-updates-alt'),  # Alternative route
    
    # Bot Webhooks (from bots during meetings - transcripts, participant events, etc.)
    path('wh', bot_webhooks.bot_webhook, name='bot-webhook'),
    # WebSocket endpoint is handled by Django Channels in app/routing.py
    
    # Static files - Logo
    path('static/ellie-logo.svg', static_files.serve_logo, name='ellie-logo'),
    
    # Bot Recordings
    path('retrieve/<str:bot_id>', bot_recordings.retrieve_bot, name='retrieve-bot'),
    path('recording/<uuid:recording_id>', bot_recordings.view_recording, name='view-recording'),
    path('recording/<uuid:recording_id>/video', bot_recordings.serve_video, name='serve-video'),
    path('recording/<uuid:recording_id>/transcript', bot_recordings.serve_transcript, name='serve-transcript'),
    path('recordings', recordings_list.list_recordings, name='list-recordings'),
]

