from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0014_folder_meetings_overview'),
    ]

    operations = [
        migrations.AddField(
            model_name='meetingtranscription',
            name='key_outcomes_signals',
            field=models.JSONField(blank=True, default=list, null=True),
        ),
        migrations.AddField(
            model_name='meetingtranscription',
            name='meeting_gaps',
            field=models.JSONField(blank=True, default=list, null=True),
        ),
        migrations.AddField(
            model_name='meetingtranscription',
            name='open_questions',
            field=models.JSONField(blank=True, default=list, null=True),
        ),
    ]
