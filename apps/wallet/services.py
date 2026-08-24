from django.db import transaction
from django.db.models import Q, Sum
from django.db.models.functions import Coalesce

from .models import LedgerEntry, LedgerTransaction, Wallet, Withdrawal


class WalletService:

    @staticmethod
    def get_wallet(user):
        wallet, _ = Wallet.objects.get_or_create(
            user=user,
        )

        return wallet

    @staticmethod
    def list_transactions(user):
        wallet = WalletService.get_wallet(user)

        return wallet.transactions.all()

    @staticmethod
    def balance_irt(wallet):
        totals = wallet.ledger_entries.aggregate(
            credits=Coalesce(Sum("amount_irt", filter=Q(direction=LedgerEntry.Direction.CREDIT)), 0),
            debits=Coalesce(Sum("amount_irt", filter=Q(direction=LedgerEntry.Direction.DEBIT)), 0),
        )
        return int(totals["credits"] - totals["debits"])

    @staticmethod
    @transaction.atomic
    def post(wallet, amount_irt, kind, description="", metadata=None, credit_wallet=True, counterparty="PLATFORM"):
        if int(amount_irt) <= 0:
            raise ValueError("Amount must be positive.")
        wallet = Wallet.objects.select_for_update().get(pk=wallet.pk)
        ledger = LedgerTransaction.objects.create(kind=kind, description=description, metadata=metadata or {})
        wallet_direction = LedgerEntry.Direction.CREDIT if credit_wallet else LedgerEntry.Direction.DEBIT
        counter_direction = LedgerEntry.Direction.DEBIT if credit_wallet else LedgerEntry.Direction.CREDIT
        LedgerEntry.objects.bulk_create([
            LedgerEntry(transaction=ledger, wallet=wallet, account_code=f"WALLET:{wallet.pk}", direction=wallet_direction, amount_irt=amount_irt),
            LedgerEntry(transaction=ledger, account_code=counterparty, direction=counter_direction, amount_irt=amount_irt),
        ])
        return ledger

    @staticmethod
    @transaction.atomic
    def review_withdrawal(withdrawal, target_status):
        locked = Withdrawal.objects.select_for_update().get(pk=withdrawal.pk)
        if locked.status != Withdrawal.Status.PENDING:
            raise ValueError("Only pending withdrawals can be reviewed.")
        if target_status == Withdrawal.Status.APPROVED:
            ledger = LedgerTransaction.objects.create(
                kind="WITHDRAWAL_CAPTURE", metadata={"withdrawal_id": locked.pk}
            )
            LedgerEntry.objects.bulk_create([
                LedgerEntry(transaction=ledger, account_code="WITHDRAWAL_HOLD", direction=LedgerEntry.Direction.DEBIT, amount_irt=locked.amount_irt),
                LedgerEntry(transaction=ledger, account_code="WITHDRAWAL_PAYABLE", direction=LedgerEntry.Direction.CREDIT, amount_irt=locked.amount_irt),
            ])
        elif target_status == Withdrawal.Status.REJECTED:
            WalletService.post(
                WalletService.get_wallet(locked.user), locked.amount_irt,
                "WITHDRAWAL_RELEASE", credit_wallet=True,
                counterparty="WITHDRAWAL_HOLD",
                metadata={"withdrawal_id": locked.pk},
            )
        else:
            raise ValueError("Unsupported withdrawal review status.")
        locked.status = target_status
        locked.save(update_fields=["status", "updated_at"])
        return locked
