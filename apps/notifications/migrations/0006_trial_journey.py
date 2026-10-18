from datetime import time

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def seed_journey_and_retire_legacy(apps, schema_editor):
    Day = apps.get_model("notifications", "TrialJourneyDay")
    Rule = apps.get_model("notifications", "SMSAutomationRule")
    Delivery = apps.get_model("notifications", "SMSAutomationDelivery")
    texts = {
        1: "{first_name} عزیز، به سوکانکس خوش آمدید!\nhttps://t.me/sokanexsupportbot",
        2: "",
        3: "فرصت مرتبط با بازار داخلی سوکانکس را چک کنید!\nپیشنهاد جدید بازار داخلی 👇\nhttps://app.sokanex.com",
        4: "جلسه جدید آموزشی فارکس!\nدر سوکانکس مشاهده کنید 👇\nhttps://app.sokanex.com",
        5: "روزانه سود کسب کنید!\nسیگنال‌های روزانه بازار کریپتو\nمشاهده فوری 👇\nhttps://app.sokanex.com",
        6: "",
        7: "{first_name} عزیز، اشتراک ۷ روزه شما به پایان رسید.\nبرای ادامه استفاده از خدمات، به پشتیبانی پیام دهید 👇\nhttps://t.me/supportsokanexbot",
    }
    markets = {3: "internal", 4: "forex", 5: "crypto"}
    for day in range(1, 8):
        Day.objects.get_or_create(day=day, defaults={
            "text": texts[day], "is_active": day not in (2, 6),
            "send_time_utc": time(9, 0), "market": markets.get(day, "ALL"),
            "in_app_enabled": True, "push_enabled": True,
        })
    Rule.objects.filter(event__in=("TRIAL", "WELCOME")).update(enabled=False)
    Delivery.objects.filter(
        event__in=("TRIAL", "WELCOME"), status="PENDING",
    ).update(status="SKIPPED", failure_code="REPLACED_BY_TRIAL_JOURNEY")


class Migration(migrations.Migration):
    dependencies = [
        ("notifications", "0005_sms_automation"),
        ("accounts", "0027_trial_settings_and_invitations"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="notification", name="show_in_app",
            field=models.BooleanField(default=True),
        ),
        migrations.CreateModel(
            name="TrialJourneyDay",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("day", models.PositiveSmallIntegerField(unique=True)),
                ("text", models.CharField(blank=True, max_length=500)),
                ("is_active", models.BooleanField(default=False)),
                ("send_time_utc", models.TimeField(default=time(9, 0))),
                ("market", models.CharField(choices=[("ALL", "All markets / fallback"), ("internal", "Internal"), ("forex", "Forex"), ("crypto", "Crypto")], default="ALL", max_length=12)),
                ("in_app_enabled", models.BooleanField(default=True)),
                ("push_enabled", models.BooleanField(default=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ("day",),
                "constraints": [models.CheckConstraint(condition=models.Q(day__gte=1, day__lte=7), name="trial_journey_day_1_7")],
            },
        ),
        migrations.CreateModel(
            name="TrialJourneyActivation",
            fields=[
                ("id", models.PositiveSmallIntegerField(default=1, primary_key=True, serialize=False)),
                ("activated_at", models.DateTimeField()),
            ],
        ),
        migrations.CreateModel(
            name="TrialJourneyEnrollment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("grant", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="journey_enrollment", to="accounts.trialgrant")),
            ],
        ),
        migrations.CreateModel(
            name="TrialJourneyDispatch",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("day", models.PositiveSmallIntegerField()),
                ("channel", models.CharField(choices=[("SMS", "SMS"), ("IN_APP", "In-app"), ("PUSH", "Push")], max_length=8)),
                ("status", models.CharField(default="DISPATCHED", max_length=12)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("enrollment", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="dispatches", to="notifications.trialjourneyenrollment")),
                ("notification", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="trial_journey_dispatches", to="notifications.notification")),
                ("sms_delivery", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="trial_journey_dispatches", to="notifications.smsautomationdelivery")),
            ],
            options={"constraints": [models.UniqueConstraint(fields=("enrollment", "day", "channel"), name="unique_trial_journey_channel_day")]},
        ),
        migrations.CreateModel(
            name="TrialJourneyConfigAudit",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("before", models.JSONField(default=list)),
                ("after", models.JSONField(default=list)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("actor", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="trial_journey_config_audits", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.RunPython(seed_journey_and_retire_legacy, migrations.RunPython.noop),
    ]
