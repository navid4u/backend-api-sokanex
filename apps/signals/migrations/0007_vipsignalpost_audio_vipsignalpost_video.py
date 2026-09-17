import apps.signals.models
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("signals", "0006_vipsignalpost")]

    operations = [
        migrations.AddField(
            model_name="vipsignalpost",
            name="audio",
            field=models.FileField(
                blank=True,
                null=True,
                upload_to=apps.signals.models.vip_signal_audio_upload,
            ),
        ),
        migrations.AddField(
            model_name="vipsignalpost",
            name="video",
            field=models.FileField(
                blank=True,
                null=True,
                upload_to=apps.signals.models.vip_signal_video_upload,
            ),
        ),
    ]
