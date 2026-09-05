from decimal import Decimal

from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import UsdLedgerEntry, Wallet


@receiver(post_save, sender=Wallet, dispatch_uid="wallet_welcome_usd_credit")
def create_welcome_usd_credit(sender, instance, created, **kwargs):
    if not created:
        return
    UsdLedgerEntry.objects.get_or_create(
        wallet=instance,
        idempotency_key="WELCOME_CREDIT",
        defaults={
            "direction": UsdLedgerEntry.Direction.CREDIT,
            "amount_usd": Decimal("100.00"),
            "balance_after": instance.balance_usd,
            "kind": "WELCOME_CREDIT",
            "description": "Initial Sokanex USD welcome credit",
        },
    )
