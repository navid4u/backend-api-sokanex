import apps.content_channels.models
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("content_channels", "0003_channelpost_ingestion_source")]

    operations = [
        migrations.AddField(
            model_name="channelpost",
            name="external_url",
            field=models.URLField(blank=True, default="", max_length=1000),
        ),
        migrations.AddField(
            model_name="channelpost",
            name="more_info_text",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="channelpost",
            name="more_info_video",
            field=models.FileField(blank=True, null=True, upload_to=apps.content_channels.models.secure_more_info_video_upload),
        ),
        migrations.AddField(
            model_name="channelpost",
            name="usage_guide_text",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="channelpost",
            name="usage_guide_video",
            field=models.FileField(blank=True, null=True, upload_to=apps.content_channels.models.secure_usage_guide_video_upload),
        ),
    ]
