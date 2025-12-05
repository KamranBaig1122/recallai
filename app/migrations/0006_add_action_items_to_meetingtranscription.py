# Generated manually for adding action_items field

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0005_alter_meetingtranscription_assemblyai_transcript_id_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='meetingtranscription',
            name='action_items',
            field=models.JSONField(blank=True, default=list, null=True),
        ),
    ]

