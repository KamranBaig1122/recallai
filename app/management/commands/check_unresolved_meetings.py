"""
Django management command to check for unresolved meetings and send notifications.

This command:
1. Finds meetings that are unresolved (folder_id is NULL)
2. Checks if meeting has ended and threshold time has passed
3. Sends notifications (in-app and/or email) for eligible meetings

Usage:
    python manage.py check_unresolved_meetings
    
    # Dry run (show what would be notified without actually sending)
    python manage.py check_unresolved_meetings --dry-run
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.conf import settings
from datetime import timedelta
from app.models import MeetingTranscription, CalendarEvent
from app.logic.notification_handler import handle_unresolved_meeting_notification
import traceback


class Command(BaseCommand):
    help = 'Check for unresolved meetings and send notifications'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be notified without actually sending notifications',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No notifications will be sent'))
        
        # Get threshold from settings
        threshold_minutes = settings.UNRESOLVED_MEETING_NOTIFICATION_THRESHOLD_MINUTES
        self.stdout.write(f'Checking for unresolved meetings (threshold: {threshold_minutes} minutes)...')
        
        # Calculate cutoff time
        cutoff_time = timezone.now() - timedelta(minutes=threshold_minutes)
        
        # Find unresolved meetings that:
        # 1. Have folder_id = NULL (unresolved)
        # 2. Have status = 'completed' (meeting completed)
        # 3. End time + threshold < now (threshold time has passed)
        # 4. Notification not yet sent (notification_sent_at is NULL)
        
        unresolved_meetings = MeetingTranscription.objects.filter(
            folder_id__isnull=True,  # Unresolved
            status='completed',  # Meeting must be completed
            notification_sent_at__isnull=True,  # Not yet notified
            backend_user_id__isnull=False,  # Must have user ID to send notifications
        ).select_related()
        
        eligible_meetings = []
        
        for meeting in unresolved_meetings:
            # Skip if no backend_user_id (can't send notifications without user)
            if not meeting.backend_user_id:
                self.stdout.write(
                    self.style.WARNING(f'Meeting {meeting.id} has no backend_user_id, skipping')
                )
                continue
            
            # IMPORTANT: Use MeetingTranscription.updated_at as the actual completion time
            # This is more accurate than CalendarEvent.end_time because:
            # 1. Meetings often end before the scheduled end_time
            # 2. updated_at reflects when the bot actually completed (status changed to 'completed')
            # 3. This works for both calendar events and manual meetings joined via link
            
            completion_time = meeting.updated_at
            
            if not completion_time:
                # Skip if no updated_at (shouldn't happen, but safety check)
                self.stdout.write(
                    self.style.WARNING(f'Meeting {meeting.id} has no updated_at, skipping')
                )
                continue
            
            # Check if threshold time has passed since actual completion
            if completion_time < cutoff_time:
                # Get event for display purposes (title, etc.)
                try:
                    event = CalendarEvent.objects.get(id=meeting.calendar_event_id)
                except CalendarEvent.DoesNotExist:
                    # Create a mock event for display purposes
                    class MockEvent:
                        def __init__(self, meeting_id):
                            # MeetingTranscription doesn't have meeting_title, use default
                            self.title = 'Untitled Meeting'
                    event = MockEvent(meeting.id)
                    self.stdout.write(
                        self.style.WARNING(f'Meeting {meeting.id} has no CalendarEvent, using updated_at as completion time: {completion_time}')
                    )
                
                eligible_meetings.append((meeting, event, completion_time))
            else:
                # Meeting completed but threshold not yet passed
                time_since_completion = timezone.now() - completion_time
                minutes_remaining = threshold_minutes - int(time_since_completion.total_seconds() / 60)
                if minutes_remaining > 0:
                    self.stdout.write(
                        f'Meeting {meeting.id} completed {int(time_since_completion.total_seconds() / 60)} minutes ago, needs {minutes_remaining} more minutes before notification'
                    )
        
        self.stdout.write(f'Found {len(eligible_meetings)} eligible unresolved meeting(s)')
        
        if not eligible_meetings:
            self.stdout.write(self.style.SUCCESS('No unresolved meetings requiring notification'))
            return
        
        # Process each eligible meeting
        notified_count = 0
        error_count = 0
        
        for meeting, event, completion_time in eligible_meetings:
            try:
                # Get meeting title from event (CalendarEvent has title property)
                meeting_title = event.title if hasattr(event, 'title') and event.title else 'Untitled Meeting'
                time_since_completion = timezone.now() - completion_time
                minutes_since_completion = int(time_since_completion.total_seconds() / 60)
                
                self.stdout.write(
                    f'\nMeeting: "{meeting_title}" (ID: {meeting.id})'
                )
                self.stdout.write(
                    f'  Completed: {completion_time.strftime("%Y-%m-%d %H:%M:%S")} ({minutes_since_completion} minutes ago)'
                )
                self.stdout.write(
                    f'  Status: {meeting.status}'
                )
                self.stdout.write(
                    f'  User: {meeting.backend_user_id}'
                )
                
                if dry_run:
                    self.stdout.write(
                        self.style.WARNING('  [DRY RUN] Would send notification for this meeting')
                    )
                else:
                    # Send notification
                    handle_unresolved_meeting_notification(meeting)
                    notified_count += 1
                    self.stdout.write(
                        self.style.SUCCESS(f'  ✓ Notification sent')
                    )
                    
            except Exception as e:
                error_count += 1
                self.stdout.write(
                    self.style.ERROR(f'  ✗ Error processing meeting {meeting.id}: {e}')
                )
                if settings.DEBUG:
                    traceback.print_exc()
        
        # Summary
        self.stdout.write('\n' + '='*60)
        if dry_run:
            self.stdout.write(self.style.WARNING(f'DRY RUN: Would notify {len(eligible_meetings)} meeting(s)'))
        else:
            self.stdout.write(self.style.SUCCESS(f'Successfully notified {notified_count} meeting(s)'))
            if error_count > 0:
                self.stdout.write(self.style.ERROR(f'Errors: {error_count} meeting(s)'))

