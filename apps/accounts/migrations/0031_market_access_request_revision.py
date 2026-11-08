from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounts", "0030_trial_campaign_operation_key")]

    operations = [
        migrations.AddField(
            model_name="marketaccessrequest",
            name="revision",
            field=models.PositiveIntegerField(default=1),
        ),
    ]
