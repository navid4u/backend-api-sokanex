from django.db import migrations, models


def migrate_live_statuses(apps, schema_editor):
    LiveEvent = apps.get_model("livestream", "LiveEvent")
    LiveEvent.objects.filter(status="LIVE").update(status="ACTIVE")
    LiveEvent.objects.filter(status="SCHEDULED").update(status="UPCOMING")
    LiveEvent.objects.filter(status__in=["CANCELLED", "DISABLED"]).update(
        status="UPCOMING",
        is_active=False,
    )
    LiveEvent.objects.exclude(
        status__in=["ACTIVE", "ENDED", "UPCOMING", "WITHIN_HOUR"]
    ).update(status="UPCOMING")


def reverse_live_statuses(apps, schema_editor):
    LiveEvent = apps.get_model("livestream", "LiveEvent")
    LiveEvent.objects.filter(status="ACTIVE").update(status="LIVE")
    LiveEvent.objects.filter(status__in=["UPCOMING", "WITHIN_HOUR"]).update(
        status="SCHEDULED"
    )


class Migration(migrations.Migration):
    dependencies = [("livestream", "0008_liveevent_join_early_minutes")]

    operations = [
        migrations.RunPython(migrate_live_statuses, reverse_live_statuses),
        migrations.AlterField(
            model_name="liveevent",
            name="status",
            field=models.CharField(
                choices=[
                    ("ACTIVE", "فعال"),
                    ("ENDED", "پایان‌یافته"),
                    ("UPCOMING", "به‌زودی"),
                    ("WITHIN_HOUR", "تا ساعتی دیگر"),
                ],
                default="UPCOMING",
                max_length=20,
            ),
        ),
        migrations.AlterModelOptions(
            name="liveevent",
            options={"ordering": ["-starts_at", "-id"]},
        ),
    ]
