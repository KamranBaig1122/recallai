# Generated migration for adding backend_user_id fields and calendar status

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0006_add_action_items_to_meetingtranscription'),
    ]

    operations = [
        # Add backend_user_id to Calendar
        migrations.AddField(
            model_name='calendar',
            name='backend_user_id',
            field=models.UUIDField(blank=True, db_index=True, null=True),
        ),
        # Add status field to Calendar
        migrations.AddField(
            model_name='calendar',
            name='status',
            field=models.CharField(
                choices=[('connected', 'Connected'), ('disconnected', 'Disconnected')],
                default='connected',
                max_length=20
            ),
        ),
        # Add index for backend_user_id on Calendar
        migrations.AddIndex(
            model_name='calendar',
            index=models.Index(fields=['backend_user_id'], name='calendars_backend_user_id_idx'),
        ),
        # Add index for status on Calendar
        migrations.AddIndex(
            model_name='calendar',
            index=models.Index(fields=['status'], name='calendars_status_idx'),
        ),
        # Add backend_user_id to CalendarEvent
        migrations.AddField(
            model_name='calendarevent',
            name='backend_user_id',
            field=models.UUIDField(blank=True, db_index=True, null=True),
        ),
        # Add index for backend_user_id on CalendarEvent
        migrations.AddIndex(
            model_name='calendarevent',
            index=models.Index(fields=['backend_user_id'], name='calendar_events_backend_user_id_idx'),
        ),
        # Add backend_user_id to MeetingTranscription
        migrations.AddField(
            model_name='meetingtranscription',
            name='backend_user_id',
            field=models.UUIDField(blank=True, db_index=True, null=True),
        ),
        # Add index for backend_user_id on MeetingTranscription
        migrations.AddIndex(
            model_name='meetingtranscription',
            index=models.Index(fields=['backend_user_id'], name='meeting_transcriptions_backend_user_id_idx'),
        ),
        # Add backend_user_id to BotRecording
        migrations.AddField(
            model_name='botrecording',
            name='backend_user_id',
            field=models.UUIDField(blank=True, db_index=True, null=True),
        ),
        # Add index for backend_user_id on BotRecording
        migrations.AddIndex(
            model_name='botrecording',
            index=models.Index(fields=['backend_user_id'], name='bot_recordings_backend_user_id_idx'),
        ),
    ]

