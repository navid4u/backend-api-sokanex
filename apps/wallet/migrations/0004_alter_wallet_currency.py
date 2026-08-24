from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("wallet", "0003_paymentauditlog")]

    operations = [
        migrations.AlterField(
            model_name="wallet",
            name="currency",
            field=models.CharField(default="IRT", max_length=10),
        ),
    ]
