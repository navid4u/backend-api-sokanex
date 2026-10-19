from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0027_trial_settings_and_invitations"),
    ]

    operations = [
        migrations.AlterField(
            model_name="user",
            name="created_at",
            field=models.DateTimeField(auto_now_add=True, db_index=True),
        ),
    ]
