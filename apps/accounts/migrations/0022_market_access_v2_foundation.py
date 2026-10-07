import uuid

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


MARKET_CHOICES = [
    ("internal", "Internal market"),
    ("forex", "Forex"),
    ("crypto", "Crypto"),
]


class Migration(migrations.Migration):
    dependencies = [("accounts", "0021_normalize_permanent_gold_to_level_five")]

    operations = [
        migrations.CreateModel(
            name="UserAccessProfile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("market_selection_confirmed_at", models.DateTimeField(blank=True, null=True)),
                ("is_elite", models.BooleanField(default=False)),
                ("elite_updated_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("elite_updated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="elite_access_changes", to=settings.AUTH_USER_MODEL)),
                ("user", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="market_access_profile", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name="UserMarketPreference",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("market", models.CharField(choices=MARKET_CHOICES, max_length=12)),
                ("selected_at", models.DateTimeField(auto_now_add=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="market_preferences_v2", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "constraints": [
                    models.UniqueConstraint(fields=("user", "market"), name="unique_user_market_preference_v2"),
                    models.CheckConstraint(condition=models.Q(market__in=["internal", "forex", "crypto"]), name="valid_user_market_preference_v2"),
                ],
            },
        ),
        migrations.CreateModel(
            name="UserMarketGrant",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("market", models.CharField(choices=MARKET_CHOICES, max_length=12)),
                ("source", models.CharField(choices=[("ADMIN", "Administrator"), ("APPROVED_REQUEST", "Approved request")], max_length=20)),
                ("granted_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("revoked_at", models.DateTimeField(blank=True, null=True)),
                ("granted_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="market_grants_issued_v2", to=settings.AUTH_USER_MODEL)),
                ("revoked_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="market_grants_revoked_v2", to=settings.AUTH_USER_MODEL)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="market_grants_v2", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "indexes": [models.Index(fields=["user", "revoked_at"], name="mkt_grant_user_active_v2_idx")],
                "constraints": [
                    models.UniqueConstraint(condition=models.Q(revoked_at__isnull=True), fields=("user", "market"), name="unique_active_user_market_grant_v2"),
                    models.CheckConstraint(condition=models.Q(market__in=["internal", "forex", "crypto"]), name="valid_user_market_grant_v2"),
                    models.CheckConstraint(condition=models.Q(revoked_at__isnull=True) | models.Q(revoked_at__gte=models.F("granted_at")), name="market_grant_revoked_after_grant_v2"),
                ],
            },
        ),
        migrations.CreateModel(
            name="TrialCampaign",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_from", models.DateTimeField(blank=True, null=True)),
                ("duration_days", models.PositiveSmallIntegerField(default=7)),
                ("status", models.CharField(choices=[("PENDING", "Pending"), ("APPLIED", "Applied"), ("CANCELLED", "Cancelled")], default="PENDING", max_length=12)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("applied_at", models.DateTimeField(blank=True, null=True)),
                ("created_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="trial_campaigns_created_v2", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "constraints": [models.CheckConstraint(condition=models.Q(duration_days__gt=0), name="trial_campaign_positive_days_v2")],
            },
        ),
        migrations.CreateModel(
            name="TrialGrant",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("started_at", models.DateTimeField()),
                ("ends_at", models.DateTimeField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("campaign", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="grants", to="accounts.trialcampaign")),
                ("user", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="trial_grant_v2", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "indexes": [models.Index(fields=["ends_at"], name="trial_grant_ends_at_v2_idx")],
                "constraints": [models.CheckConstraint(condition=models.Q(ends_at__gt=models.F("started_at")), name="trial_grant_ends_after_start_v2")],
            },
        ),
        migrations.CreateModel(
            name="UserAccessAudit",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("subject_user_id", models.PositiveBigIntegerField()),
                ("action", models.CharField(choices=[("PREFERENCES_CHANGED", "Preferences changed"), ("MARKET_GRANTED", "Market granted"), ("MARKET_REVOKED", "Market revoked"), ("ELITE_CHANGED", "Elite changed"), ("TRIAL_STARTED", "Trial started"), ("LEGACY_RESET", "Legacy access reset")], max_length=24)),
                ("before", models.JSONField(default=dict)),
                ("after", models.JSONField(default=dict)),
                ("operation_id", models.UUIDField(db_index=True, default=uuid.uuid4)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("actor", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="market_access_actions_v2", to=settings.AUTH_USER_MODEL)),
                ("user", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="market_access_audits_v2", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ("-created_at", "-id"),
                "indexes": [models.Index(fields=["subject_user_id", "-created_at"], name="access_audit_user_time_v2_idx")],
            },
        ),
    ]
