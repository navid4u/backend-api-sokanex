from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("platform_settings", "0003_seed_current_english_ui_catalog")]

    operations = [
        migrations.AddField(
            model_name="platformsettings",
            name="default_theme",
            field=models.CharField(
                choices=[("light", "Light"), ("dark", "Dark")],
                default="dark", max_length=5,
            ),
        ),
    ]
