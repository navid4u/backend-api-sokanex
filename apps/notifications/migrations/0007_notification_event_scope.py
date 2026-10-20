from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("notifications", "0006_trial_journey")]

    operations = [
        migrations.AddField(
            model_name="notification",
            name="source_key",
            field=models.CharField(blank=True, max_length=120, null=True, unique=True),
        ),
        migrations.AddField(
            model_name="notification",
            name="market_scope",
            field=models.CharField(blank=True, default="", max_length=12),
        ),
    ]
