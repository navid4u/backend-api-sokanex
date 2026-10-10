from datetime import timedelta
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import Q, Sum
from django.db.models.functions import Coalesce

from django.utils import timezone

from .exceptions import PremiumPurchaseError
from .models import LedgerEntry, LedgerTransaction, UpgradePlan, UsdLedgerEntry, Wallet, Withdrawal


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
    def balance_usd_for_user(user):
        balance = Wallet.objects.filter(user=user).values_list("balance_usd", flat=True).first()
        return balance if balance is not None else Decimal("0.00")

    @staticmethod
    def premium_subscription(user):
        from apps.accounts.market_access import market_access_v2_enabled, resolve_market_access
        from apps.accounts.models import MarketAccessRequest, UpgradeRequest

        if market_access_v2_enabled():
            state = resolve_market_access(user)
            trial = getattr(user, "trial_grant_v2", None)
            now = timezone.now()
            expired_trial = bool(trial and trial.revoked_at is None and trial.ends_at <= now)
            remaining = 0
            if state.trial_active and trial:
                remaining_seconds = max((trial.ends_at - now).total_seconds(), 0)
                remaining = int((remaining_seconds + 86399) // 86400)
            pending = MarketAccessRequest.objects.filter(
                user=user, status=MarketAccessRequest.Status.PENDING
            ).exists()
            return {
                "active": state.has_gold_features,
                "tier": "GOLD" if state.has_gold_features else None,
                "plan_id": None,
                "purchased_at": None,
                "access_level": None,
                "trial": trial is not None,
                "trial_expires_at": trial.ends_at if trial and trial.revoked_at is None else None,
                "days_remaining": remaining,
                "status": "ACTIVE" if state.has_gold_features else "EXPIRED" if expired_trial else "INACTIVE",
                "can_start_trial": False,
                "can_request": bool(
                    state.special_role is None
                    and state.market_selection_confirmed
                    and state.selected_markets
                    and not state.trial_active
                    and not state.has_gold_features
                    and not pending
                ),
            }

        purchase = UpgradeRequest.objects.filter(
            user=user,
            request_type=UpgradeRequest.Type.PREMIUM,
            status=UpgradeRequest.Status.APPROVED,
        ).select_related("plan").order_by("-reviewed_at", "-created_at", "-pk").first()
        active = user.has_gold_access
        is_trial = bool(user.gold_trial_started_at and not user.gold_permanent_granted_at)
        expired_trial = bool(
            is_trial
            and user.gold_trial_expires_at
            and user.gold_trial_expires_at <= timezone.now()
        )
        remaining = 0
        if active and is_trial and user.gold_trial_expires_at:
            remaining_seconds = max(
                (user.gold_trial_expires_at - timezone.now()).total_seconds(), 0
            )
            remaining = int((remaining_seconds + 86399) // 86400)
        return {
            "active": active,
            "tier": "GOLD" if active or expired_trial else None,
            "plan_id": purchase.plan_id if purchase else None,
            "purchased_at": (
                user.gold_permanent_granted_at
                or user.gold_trial_started_at
                or (purchase.reviewed_at or purchase.created_at if purchase else None)
            ),
            "access_level": user.access_level,
            "trial": is_trial,
            "trial_expires_at": user.gold_trial_expires_at if is_trial else None,
            "days_remaining": remaining,
            "status": (
                "ACTIVE" if active
                else "EXPIRED" if expired_trial
                else "AVAILABLE" if (
                    user.gold_trial_started_at is None
                    and user.gold_permanent_granted_at is None
                )
                else "INACTIVE"
            ),
            "can_start_trial": (
                user.gold_trial_started_at is None
                and user.gold_permanent_granted_at is None
            ),
            "can_request": bool(
                user.access_level == 2
                and expired_trial
            ),
        }

    @staticmethod
    def _post_usd_locked(wallet, amount_usd, kind, direction, idempotency_key, description="", metadata=None):
        amount = Decimal(amount_usd).quantize(Decimal("0.01"))
        if amount <= 0:
            raise ValueError("Amount must be positive.")
        if direction == UsdLedgerEntry.Direction.DEBIT:
            if wallet.balance_usd < amount:
                raise PremiumPurchaseError(
                    "موجودی دلاری برای خرید این اشتراک کافی نیست.",
                    "INSUFFICIENT_BALANCE",
                    402,
                    required_usd=str(amount),
                    balance_usd=str(wallet.balance_usd),
                )
            wallet.balance_usd -= amount
        else:
            wallet.balance_usd += amount
        wallet.save(update_fields=["balance_usd", "updated_at"])
        return UsdLedgerEntry.objects.create(
            wallet=wallet,
            direction=direction,
            amount_usd=amount,
            balance_after=wallet.balance_usd,
            kind=kind,
            idempotency_key=idempotency_key,
            description=description,
            metadata=metadata or {},
        )

    @classmethod
    def purchase_premium(cls, user, idempotency_key, plan_id=None):
        from apps.accounts.market_access import market_access_v2_enabled
        from apps.accounts.services import LegacyGoldFlowDisabled

        if market_access_v2_enabled():
            raise LegacyGoldFlowDisabled()
        from apps.accounts.models import UpgradeRequest

        try:
            with transaction.atomic():
                wallet = cls.get_wallet(user)
                wallet = Wallet.objects.select_for_update().get(pk=wallet.pk)
                locked_user = type(user).objects.select_for_update().get(pk=user.pk)

                replay = UpgradeRequest.objects.select_related("plan").filter(
                    user=locked_user,
                    purchase_idempotency_key=idempotency_key,
                ).first()
                if replay:
                    if plan_id is not None and replay.plan_id != plan_id:
                        raise PremiumPurchaseError(
                            "این idempotency_key قبلاً برای پلن دیگری استفاده شده است.",
                            "IDEMPOTENCY_CONFLICT",
                            409,
                        )
                    return replay, wallet, False

                active_purchase = UpgradeRequest.objects.select_related("plan").filter(
                    user=locked_user,
                    request_type=UpgradeRequest.Type.PREMIUM,
                    status=UpgradeRequest.Status.APPROVED,
                ).order_by("-reviewed_at", "-pk").first()
                if active_purchase:
                    if locked_user.has_gold_access:
                        return active_purchase, wallet, False
                    raise PremiumPurchaseError(
                        "آزمایش اشتراک طلایی پایان یافته است؛ برای دریافت اشتراک دائمی درخواست ثبت کنید.",
                        "GOLD_TRIAL_EXPIRED",
                        409,
                    )

                plans = UpgradePlan.objects.select_for_update().filter(
                    plan_type=UpgradePlan.Type.PREMIUM,
                    level=5,
                    active=True,
                )
                if plan_id is not None:
                    plans = plans.filter(pk=plan_id)
                plan = plans.first()
                if not plan:
                    raise PremiumPurchaseError(
                        "پلن فعال اشتراک ویژه پیدا نشد.",
                        "PREMIUM_PLAN_NOT_AVAILABLE",
                        404,
                    )

                amount = plan.price_usd
                entry = None
                if amount > 0:
                    entry = cls._post_usd_locked(
                        wallet,
                        amount,
                        "PREMIUM_PURCHASE",
                        UsdLedgerEntry.Direction.DEBIT,
                        f"PREMIUM_PURCHASE:{idempotency_key}",
                        "Sokanex premium subscription purchase",
                        {"plan_id": plan.pk},
                    )
                purchased_at = timezone.now()
                pending = UpgradeRequest.objects.select_for_update().filter(
                    user=locked_user,
                    request_type=UpgradeRequest.Type.PREMIUM,
                    status=UpgradeRequest.Status.PENDING,
                ).first()
                purchase = pending or UpgradeRequest(user=locked_user)
                if pending and pending.price_snapshot_irt and pending.hold_ledger_transaction_id:
                    cls.post(
                        wallet,
                        pending.price_snapshot_irt,
                        "UPGRADE_RELEASE",
                        credit_wallet=True,
                        counterparty="UPGRADE_HOLD",
                        metadata={"upgrade_request_id": pending.pk, "reason": "premium_usd_purchase"},
                    )
                purchase.request_type = UpgradeRequest.Type.PREMIUM
                purchase.requested_level = 5
                purchase.grant_source = UpgradeRequest.GrantSource.WALLET_PURCHASE
                purchase.plan = plan
                purchase.price_snapshot_usd = amount
                purchase.price_snapshot_irt = 0
                purchase.hold_ledger_transaction = None
                purchase.purchase_idempotency_key = idempotency_key
                purchase.usd_ledger_entry = entry
                purchase.status = UpgradeRequest.Status.APPROVED
                purchase.reviewed_at = purchased_at
                purchase.admin_note = "Purchased instantly with USD wallet balance."
                purchase.save()
                locked_user.access_level = 5
                locked_user.gold_trial_started_at = purchased_at
                locked_user.gold_trial_expires_at = purchased_at + timedelta(days=7)
                locked_user.save(update_fields=[
                    "access_level", "gold_trial_started_at", "gold_trial_expires_at",
                    "updated_at"
                ])
                return purchase, wallet, True
        except IntegrityError:
            replay = UpgradeRequest.objects.select_related("plan").filter(
                user=user,
                purchase_idempotency_key=idempotency_key,
            ).first()
            if replay:
                return replay, Wallet.objects.get(user=user), False
            raise

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
