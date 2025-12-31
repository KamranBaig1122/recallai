# Generated manually
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0009_add_workspace_folder_to_bot_recording'),
    ]

    operations = [
        migrations.AddField(
            model_name='meetingtranscription',
            name='workspace_id',
            field=models.UUIDField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name='meetingtranscription',
            name='folder_id',
            field=models.UUIDField(blank=True, db_index=True, null=True),
        ),
        migrations.AddIndex(
            model_name='meetingtranscription',
            index=models.Index(fields=['workspace_id'], name='meeting_tra_workspa_idx'),
        ),
        migrations.AddIndex(
            model_name='meetingtranscription',
            index=models.Index(fields=['folder_id'], name='meeting_tra_folder__idx'),
        ),
    ]

