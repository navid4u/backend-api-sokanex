from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0023_content_section_access_policy"),
    ]

    operations = [
        migrations.CreateModel(
            name="MarketAccessRequest",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("requested_tier", models.CharField(choices=[("PRO", "Pro"), ("GOLD", "Gold"), ("ELITE", "Elite")], max_length=8)),
                ("requested_markets", models.JSONField(default=list)),
                ("message", models.CharField(blank=True, max_length=1000)),
                ("status", models.CharField(choices=[("PENDING", "Pending"), ("APPROVED", "Approved"), ("REJECTED", "Rejected")], default="PENDING", max_length=8)),
                ("approved_markets", models.JSONField(default=list)),
                ("approved_elite", models.BooleanField(default=False)),
                ("admin_note", models.CharField(blank=True, max_length=1000)),
                ("reviewed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("reviewed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="market_access_requests_reviewed_v2", to=settings.AUTH_USER_MODEL)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="market_access_requests_v2", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ("-created_at", "-id"),
                "indexes": [models.Index(fields=["status", "-created_at"], name="mkt_request_status_time_v2_idx")],
                "constraints": [models.UniqueConstraint(condition=models.Q(status="PENDING"), fields=("user",), name="unique_pending_market_access_request_v2")],
            },
        ),
    ]
