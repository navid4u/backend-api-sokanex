from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("signals", "0003_signal_closed_at_signal_order_type_and_more")]
    operations = [
        migrations.AddField(model_name="signal", name="source", field=models.CharField(choices=[("LEGACY", "سامانه داخلی"), ("TELEGRAM_API", "API تلگرام")], db_index=True, default="LEGACY", max_length=20)),
        migrations.AddField(model_name="signal", name="external_id", field=models.CharField(blank=True, max_length=150, null=True, unique=True)),
    ]
