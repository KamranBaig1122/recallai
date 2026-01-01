# Generated manually
from django.db import migrations, models
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0011_add_default_folder'),
    ]

    operations = [
        migrations.CreateModel(
            name='Notification',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True)),
                ('backend_user_id', models.UUIDField(db_index=True)),
                ('notification_type', models.CharField(choices=[('unresolved_meeting_notification', 'Unresolved Meeting Notification')], max_length=50)),
                ('meeting_id', models.UUIDField(blank=True, db_index=True, null=True)),
                ('meeting_title', models.CharField(max_length=500)),
                ('message', models.TextField()),
                ('read', models.BooleanField(db_index=True, default=False)),
                ('read_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'db_table': 'notifications',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='notification',
            index=models.Index(fields=['backend_user_id', 'read'], name='notificatio_user_re_8a3f2d_idx'),
        ),
        migrations.AddIndex(
            model_name='notification',
            index=models.Index(fields=['backend_user_id', '-created_at'], name='notificatio_user_cr_9b4e5f_idx'),
        ),
        migrations.AddIndex(
            model_name='notification',
            index=models.Index(fields=['meeting_id'], name='notificatio_meeting_7c8d9e_idx'),
        ),
    ]

