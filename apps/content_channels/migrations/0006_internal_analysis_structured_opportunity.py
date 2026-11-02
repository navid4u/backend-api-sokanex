from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("content_channels", "0005_car_scope_and_video_reference")]

    operations = [
        migrations.AddField("channelpost", "opportunity_status", models.CharField(blank=True, null=True, max_length=10, choices=[("ACTIVE", "Active"), ("PENDING", "Pending"), ("EXPIRED", "Expired"), ("CLOSED", "Closed")])),
        migrations.AddField("channelpost", "direction", models.CharField(blank=True, null=True, max_length=4, choices=[("BUY", "Buy"), ("SELL", "Sell")])),
        migrations.AddField("channelpost", "entry_price_min", models.DecimalField(blank=True, null=True, max_digits=24, decimal_places=8)),
        migrations.AddField("channelpost", "entry_price_max", models.DecimalField(blank=True, null=True, max_digits=24, decimal_places=8)),
        migrations.AddField("channelpost", "take_profit", models.DecimalField(blank=True, null=True, max_digits=24, decimal_places=8)),
        migrations.AddField("channelpost", "stop_loss", models.DecimalField(blank=True, null=True, max_digits=24, decimal_places=8)),
        migrations.AddField("channelpost", "currency_label", models.CharField(blank=True, null=True, max_length=40)),
        migrations.AddField("channelpost", "entry_warning", models.TextField(blank=True, null=True)),
        migrations.AddConstraint(
            model_name="channelpost",
            constraint=models.CheckConstraint(
                condition=(
                    (models.Q(entry_price_min__gte=0) | models.Q(entry_price_min__isnull=True))
                    & (models.Q(entry_price_max__gte=0) | models.Q(entry_price_max__isnull=True))
                    & (models.Q(take_profit__gte=0) | models.Q(take_profit__isnull=True))
                    & (models.Q(stop_loss__gte=0) | models.Q(stop_loss__isnull=True))
                    & (models.Q(entry_price_min__lte=models.F("entry_price_max"))
                       | models.Q(entry_price_min__isnull=True)
                       | models.Q(entry_price_max__isnull=True))
                ),
                name="internal_opportunity_valid_prices",
            ),
        ),
    ]
