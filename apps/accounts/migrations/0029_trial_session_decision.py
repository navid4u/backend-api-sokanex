from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def backfill_enabled_cutoff(apps, schema_editor):
    Setting = apps.get_model("accounts", "TrialAutoStartSettings")
    Setting.objects.filter(auto_start_new_users=True, enabled_at__isnull=True).update(
        enabled_at=models.F("updated_at"),
    )


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0028_user_created_at_index"),
    ]

    operations = [
        migrations.AddField(
            model_name="trialgrant", name="expiry_audited_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="trialgrant", name="source",
            field=models.CharField(blank=True, default="", max_length=24),
        ),
        migrations.AddField(
            model_name="trialautostartsettings", name="enabled_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.CreateModel(
            name="TrialAutoStartDecision",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("reason", models.CharField(max_length=40)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("grant", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                             related_name="auto_start_decisions", to="accounts.trialgrant")),
                ("user", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE,
                                                related_name="trial_auto_start_decision", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AlterField(
            model_name="useraccessaudit", name="action",
            field=models.CharField(choices=[
                ("PREFERENCES_CHANGED", "Preferences changed"),
                ("MARKET_GRANTED", "Market granted"),
                ("MARKET_REVOKED", "Market revoked"),
                ("ELITE_CHANGED", "Elite changed"),
                ("TRIAL_STARTED", "Trial started"),
                ("TRIAL_AUTO_START_SKIPPED", "Automatic trial not started"),
                ("TRIAL_EXPIRED", "Trial expired"),
                ("LEGACY_RESET", "Legacy access reset"),
            ], max_length=24),
        ),
        migrations.RunPython(backfill_enabled_cutoff, migrations.RunPython.noop),
    ]
