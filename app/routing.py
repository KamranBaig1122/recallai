"""
WebSocket URL routing for Django Channels
"""
from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'^ws/rt$', consumers.BotRealtimeConsumer.as_asgi()),
    re_path(r'^ws/calendar-updates$', consumers.CalendarUpdatesConsumer.as_asgi()),
]

