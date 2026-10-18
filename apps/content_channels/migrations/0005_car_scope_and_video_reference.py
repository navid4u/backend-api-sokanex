from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("content_channels", "0004_internal_analysis_opportunity_details"),
        ("videos", "0004_video_file_size_bytes_video_height_video_mime_type_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="channelpost", name="scope",
            field=models.CharField(blank=True, choices=[
                ("DOLLAR", "دلار"), ("GOLD", "طلا"), ("STOCK", "بورس ایران"),
                ("HOUSING", "مسکن"), ("CAR", "خودرو"), ("FOREX", "فارکس"),
            ], max_length=20),
        ),
        migrations.AddField(
            model_name="channelpost", name="usage_guide_video_reference",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name="internal_analysis_usage_guides", to="videos.video",
            ),
        ),
    ]
