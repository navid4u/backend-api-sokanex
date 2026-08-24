from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("wallet", "0004_alter_wallet_currency")]

    operations = [
        migrations.RunSQL(
            "UPDATE wallet_upgradeplan SET price_irt = 0 WHERE level = 1",
            migrations.RunSQL.noop,
        ),
        migrations.AddConstraint(
            model_name="upgradeplan",
            constraint=models.CheckConstraint(
                condition=models.Q(level__gte=1, level__lte=5),
                name="upgrade_plan_level_between_1_and_5",
            ),
        ),
        migrations.AddConstraint(
            model_name="upgradeplan",
            constraint=models.CheckConstraint(
                condition=models.Q(level__gt=1) | models.Q(price_irt=0),
                name="upgrade_plan_level_1_is_free",
            ),
        ),
    ]
