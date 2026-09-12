from django.conf import settings
from django.db import migrations, models


def create_ingestion_author(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    User.objects.get_or_create(
        username="sokanex-feed-bot",
        defaults={"first_name": "Sokanex", "last_name": "Feed Bot", "is_active": False, "password": "!"},
    )


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("content_channels", "0002_channelpost_status_channelpost_views_count_and_more"),
    ]

    operations = [
        migrations.AddField(model_name="channelpost", name="source", field=models.CharField(choices=[("LEGACY", "سامانه داخلی"), ("TELEGRAM_API", "API تلگرام")], db_index=True, default="LEGACY", max_length=20)),
        migrations.AddField(model_name="channelpost", name="external_id", field=models.CharField(blank=True, max_length=150, null=True, unique=True)),
        migrations.AlterField(model_name="channelpost", name="scope", field=models.CharField(blank=True, choices=[("DOLLAR", "دلار"), ("GOLD", "طلا"), ("STOCK", "بورس ایران"), ("FOREX", "فارکس"), ("HOUSING", "مسکن")], max_length=20)),
        migrations.RunPython(create_ingestion_author, migrations.RunPython.noop),
    ]
