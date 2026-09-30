from decimal import Decimal

import django.core.validators
from django.db import migrations, models
from django.utils import timezone


def remove_unspent_welcome_credits(apps, schema_editor):
    """Reverse remaining promotional grants without deleting ledger history."""
    Wallet = apps.get_model("wallet", "Wallet")
    UsdLedgerEntry = apps.get_model("wallet", "UsdLedgerEntry")
    database = schema_editor.connection.alias

    wallets = (
        Wallet.objects.using(database)
        .filter(usd_ledger_entries__kind="WELCOME_CREDIT")
        .distinct()
        .order_by("pk")
    )
    for wallet in wallets.iterator():
        remaining = wallet.balance_usd or Decimal("0.00")
        if remaining <= 0:
            continue
        UsdLedgerEntry.objects.using(database).get_or_create(
            wallet_id=wallet.pk,
            idempotency_key="WELCOME_CREDIT_REVOKE:trial-only",
            defaults={
                "direction": "DEBIT",
                "amount_usd": remaining,
                "balance_after": Decimal("0.00"),
                "kind": "WELCOME_CREDIT_REVOKED",
                "description": "Removed unspent promotional USD balance; Gold trial is free.",
                "metadata": {"reason": "trial_only_subscription_contract"},
            },
        )
        Wallet.objects.using(database).filter(pk=wallet.pk).update(
            balance_usd=Decimal("0.00"),
            updated_at=timezone.now(),
        )


class Migration(migrations.Migration):
    dependencies = [
        ("wallet", "0006_upgradeplan_plan_type_upgradeplan_price_usd_and_more"),
    ]

    operations = [
        migrations.RunPython(remove_unspent_welcome_credits, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="wallet",
            name="balance_usd",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0.00"),
                max_digits=18,
                validators=[
                    django.core.validators.MinValueValidator(Decimal("0.00")),
                ],
            ),
        ),
    ]
