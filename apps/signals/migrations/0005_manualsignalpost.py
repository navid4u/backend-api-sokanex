import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models

import apps.signals.models


class Migration(migrations.Migration):
    dependencies = [
        ("signals", "0004_signal_ingestion_source"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ManualSignalPost",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("text", models.TextField(blank=True, max_length=4000)),
                ("image", models.ImageField(blank=True, null=True, upload_to=apps.signals.models.manual_signal_post_upload)),
                ("source", models.CharField(choices=[("SUPER_ADMIN_MANUAL", "ثبت دستی سوپر ادمین")], default="SUPER_ADMIN_MANUAL", editable=False, max_length=30)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("published_at", models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("author", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="manual_signal_posts", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["-published_at", "-id"],
                "indexes": [models.Index(fields=["is_active", "-published_at"], name="signals_man_is_acti_81b9bb_idx")],
            },
        ),
    ]
