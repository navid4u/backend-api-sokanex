import apps.signals.models
from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [
        ("signals", "0005_manualsignalpost"),
    ]

    operations = [
        migrations.CreateModel(
            name="VIPSignalPost",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("channel", models.CharField(choices=[("CRYPTO", "کانال وی آی پی سوکانکس (کریپتو)"), ("FOREX", "کانال وی آی پی سوکانکس (فارکس)")], db_index=True, max_length=10)),
                ("text", models.TextField(max_length=20000)),
                ("image", models.ImageField(blank=True, null=True, upload_to=apps.signals.models.vip_signal_post_upload)),
                ("external_id", models.CharField(blank=True, max_length=180, null=True)),
                ("source", models.CharField(choices=[("TELEGRAM_API", "API تلگرام")], default="TELEGRAM_API", editable=False, max_length=20)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("published_at", models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ["-published_at", "-id"],
                "indexes": [models.Index(fields=["channel", "is_active", "-published_at"], name="vip_signal_channel_feed_idx")],
                "constraints": [models.UniqueConstraint(condition=models.Q(("external_id__isnull", False)), fields=("channel", "external_id"), name="uniq_vip_signal_channel_external")],
            },
        ),
    ]
