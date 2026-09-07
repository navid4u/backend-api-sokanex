from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("market", "0003_cryptomarketsnapshot")]
    operations = [
        migrations.CreateModel(
            name="MarketQuoteSnapshot",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("quotes", models.JSONField(default=dict)),
                ("source_updated_at", models.DateTimeField()),
                ("captured_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["-source_updated_at", "-id"]},
        ),
    ]
