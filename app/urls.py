from django.urls import path
from app.views import root, auth, oauth, calendar, calendar_event, webhooks, calendar_api, transcription_api
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
    
    # Calendar API endpoints (for frontend) - simple like root_view
    path('api/calendars', calendar_api.api_list_calendars, name='api-list-calendars'),
    path('api/calendar/connect-urls', calendar_api.api_get_connect_urls, name='api-get-connect-urls'),
    path('api/calendar/<uuid:calendar_id>', calendar_api.api_get_calendar, name='api-get-calendar'),
    path('api/calendar/<uuid:calendar_id>/update', calendar_api.api_update_calendar, name='api-update-calendar'),
    path('api/calendar/<uuid:calendar_id>/sync', calendar_api.api_sync_calendar, name='api-sync-calendar'),
    path('api/calendar/<uuid:calendar_id>/delete', calendar_api.api_delete_calendar, name='api-delete-calendar'),
    path('api/calendar-event/<uuid:event_id>/set-manual-record', calendar_api.api_set_manual_record, name='api-set-manual-record'),
    path('api/calendar-event/<uuid:event_id>/create-bot', calendar_api.api_create_bot_for_event, name='api-create-bot-for-event'),
    path('api/transcriptions', transcription_api.api_list_transcriptions, name='api-list-transcriptions'),
    path('api/transcriptions/<uuid:transcription_id>', transcription_api.api_get_transcription, name='api-get-transcription'),
    
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

