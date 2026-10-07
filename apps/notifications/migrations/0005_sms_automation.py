from datetime import time

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def seed_disabled_rules(apps, schema_editor):
    Rule = apps.get_model("notifications", "SMSAutomationRule")
    markets = ("ALL", "internal", "forex", "crypto")
    base = {
        "WELCOME": ("WELCOME", None, "{first_name} عزیز، به سوکانکس خوش آمدید. {support_link}"),
        "ACCESS_CHANGE": ("ACCESS_CHANGE", None, "{first_name} عزیز، وضعیت دسترسی شما به {membership_tier} تغییر کرد. {support_link}"),
    }
    for day in (1, 3, 5, 6, 7):
        base[f"TRIAL_{day}"] = (
            "TRIAL", day,
            "{first_name} عزیز، روز {days_remaining} از دوره آزمایشی شما باقی مانده است. {support_link}",
        )
    for market in markets:
        for slot, (event, day, text) in base.items():
            Rule.objects.get_or_create(
                slot=slot, market=market,
                defaults={"event": event, "trial_day": day, "text": text, "enabled": False},
            )


class Migration(migrations.Migration):
    dependencies = [
        ("notifications", "0004_web_push_subscriptions_and_deliveries"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="SMSAutomationRule",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("event", models.CharField(choices=[("WELCOME", "Registration welcome"), ("ACCESS_CHANGE", "Access changed"), ("TRIAL", "Trial day")], max_length=20)),
                ("market", models.CharField(choices=[("ALL", "All markets / fallback"), ("internal", "Internal"), ("forex", "Forex"), ("crypto", "Crypto")], default="ALL", max_length=12)),
                ("slot", models.CharField(max_length=24)),
                ("trial_day", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("text", models.CharField(max_length=500)),
                ("enabled", models.BooleanField(default=False)),
                ("send_time_utc", models.TimeField(default=time(9, 0))),
                ("delay_minutes", models.PositiveIntegerField(default=0)),
                ("enabled_at", models.DateTimeField(blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("updated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="sms_automation_rules_edited", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ("event", "slot", "market"),
                "constraints": [models.UniqueConstraint(fields=("slot", "market"), name="unique_sms_automation_slot_market")],
            },
        ),
        migrations.CreateModel(
            name="SMSBroadcast",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("idempotency_key", models.CharField(max_length=64, unique=True)),
                ("membership_tiers", models.JSONField(default=list)),
                ("market", models.CharField(default="ALL", max_length=12)),
                ("text", models.CharField(max_length=500)),
                ("recipient_count", models.PositiveIntegerField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("created_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name="SMSAutomationDelivery",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("event_key", models.CharField(max_length=100)),
                ("event", models.CharField(max_length=20)),
                ("phone", models.CharField(max_length=20)),
                ("text", models.CharField(max_length=500)),
                ("status", models.CharField(choices=[("PENDING", "Pending"), ("SENDING", "Sending / reconciliation required if interrupted"), ("SENT", "Sent"), ("FAILED", "Failed"), ("SKIPPED", "Skipped after eligibility changed")], default="PENDING", max_length=10)),
                ("scheduled_at", models.DateTimeField()),
                ("claimed_at", models.DateTimeField(blank=True, null=True)),
                ("sent_at", models.DateTimeField(blank=True, null=True)),
                ("provider_message_id", models.CharField(blank=True, max_length=100)),
                ("failure_code", models.CharField(blank=True, max_length=80)),
                ("attempts", models.PositiveSmallIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("broadcast", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to="notifications.smsbroadcast")),
                ("rule", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to="notifications.smsautomationrule")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ("-created_at", "-id"),
                "constraints": [models.UniqueConstraint(fields=("user", "event_key"), name="unique_sms_automation_user_event")],
                "indexes": [
                    models.Index(fields=("status", "scheduled_at"), name="sms_auto_status_due_idx"),
                    models.Index(fields=("user", "-created_at"), name="sms_auto_user_time_idx"),
                ],
            },
        ),
        migrations.RunPython(seed_disabled_rules, migrations.RunPython.noop),
    ]
