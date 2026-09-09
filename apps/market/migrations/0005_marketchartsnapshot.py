from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("market", "0004_marketquotesnapshot")]

    operations = [
        migrations.CreateModel(
            name="MarketChartSnapshot",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("market", models.CharField(max_length=20)),
                ("symbol", models.CharField(max_length=50)),
                ("range_value", models.CharField(max_length=10)),
                ("interval", models.CharField(blank=True, max_length=10)),
                ("payload", models.JSONField(default=dict)),
                ("updated_at", models.DateTimeField(auto_now=True, db_index=True)),
            ],
            options={
                "ordering": ["-updated_at", "-id"],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("market", "symbol", "range_value", "interval"),
                        name="unique_market_chart_snapshot",
                    )
                ],
            },
        )
    ]
