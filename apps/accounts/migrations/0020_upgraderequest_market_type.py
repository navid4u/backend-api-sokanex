from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounts", "0019_market_gold_trial_telegram")]

    operations = [
        migrations.AddField(
            model_name="upgraderequest",
            name="market_type",
            field=models.CharField(
                blank=True,
                choices=[
                    ("internal", "Internal market"),
                    ("forex", "Forex"),
                    ("crypto", "Crypto"),
                ],
                max_length=12,
                null=True,
            ),
        ),
    ]
