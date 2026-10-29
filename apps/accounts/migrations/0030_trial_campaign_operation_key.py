from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounts", "0029_trial_session_decision")]

    operations = [
        migrations.AddField(
            model_name="trialcampaign",
            name="operation_key",
            field=models.CharField(blank=True, max_length=64, null=True, unique=True),
        ),
    ]
