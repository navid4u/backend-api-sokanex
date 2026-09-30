from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounts", "0018_financial_personality_risk_v2")]

    operations = [
        migrations.AddField(
            model_name="user",
            name="market_type",
            field=models.CharField(blank=True, choices=[("internal", "Internal market"), ("forex", "Forex"), ("crypto", "Crypto")], default="", max_length=12),
        ),
        migrations.AddField(
            model_name="user",
            name="telegram_id",
            field=models.CharField(blank=True, db_index=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="user",
            name="gold_trial_started_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="user",
            name="gold_trial_expires_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="user",
            name="gold_permanent_granted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="upgraderequest",
            name="grant_source",
            field=models.CharField(choices=[("LEGACY", "Legacy request"), ("WALLET_PURCHASE", "Wallet purchase"), ("GOLD_RENEWAL_REQUEST", "Gold renewal request")], default="LEGACY", max_length=32),
        ),
    ]
