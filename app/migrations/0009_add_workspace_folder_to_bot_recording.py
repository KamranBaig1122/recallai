# Generated manually
from django.db import migrations, models
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0008_rename_bot_recordings_backend_user_id_idx_bot_recordi_backend_57df2b_idx_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='botrecording',
            name='workspace_id',
            field=models.UUIDField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name='botrecording',
            name='folder_id',
            field=models.UUIDField(blank=True, db_index=True, null=True),
        ),
        migrations.AddIndex(
            model_name='botrecording',
            index=models.Index(fields=['workspace_id'], name='bot_recordi_workspa_idx'),
        ),
        migrations.AddIndex(
            model_name='botrecording',
            index=models.Index(fields=['folder_id'], name='bot_recordi_folder__idx'),
        ),
    ]

