import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("notifications", "0003_notification_allowed_level_1_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="WebPushSubscription",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("endpoint", models.URLField(max_length=2048, unique=True)),
                ("p256dh", models.CharField(max_length=256)),
                ("auth", models.CharField(max_length=128)),
                ("user_agent", models.CharField(blank=True, max_length=500)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("last_seen_at", models.DateTimeField(auto_now=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="web_push_subscriptions", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ("-last_seen_at",)},
        ),
        migrations.CreateModel(
            name="NotificationPushDelivery",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("status", models.CharField(choices=[("PENDING", "Pending"), ("SENT", "Sent"), ("FAILED", "Failed")], db_index=True, default="PENDING", max_length=10)),
                ("attempts", models.PositiveSmallIntegerField(default=0)),
                ("provider_status_code", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("error_code", models.CharField(blank=True, max_length=80)),
                ("sent_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("notification", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="push_deliveries", to="notifications.notification")),
                ("subscription", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="deliveries", to="notifications.webpushsubscription")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="notification_push_deliveries", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "constraints": [models.UniqueConstraint(fields=("notification", "subscription"), name="unique_notification_push_per_subscription")],
                "indexes": [models.Index(fields=["status", "attempts", "created_at"], name="notif_push_status_4d971b_idx")],
            },
        ),
    ]
