import uuid
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models


class Wallet(models.Model):

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="wallet",
    )

    balance = models.DecimalField(
        max_digits=20,
        decimal_places=8,
        default=Decimal("0"),
        validators=[
            MinValueValidator(Decimal("0")),
        ],
    )

    currency = models.CharField(
        max_length=10,
        default="IRT",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    def __str__(self):
        return (
            f"{self.user.username} - "
            f"{self.balance} {self.currency}"
        )


class Transaction(models.Model):

    class Type(models.TextChoices):
        CREDIT = "CREDIT", "Credit"
        DEBIT = "DEBIT", "Debit"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        COMPLETED = "COMPLETED", "Completed"
        FAILED = "FAILED", "Failed"

    wallet = models.ForeignKey(
        Wallet,
        on_delete=models.CASCADE,
        related_name="transactions",
    )

    transaction_type = models.CharField(
        max_length=10,
        choices=Type.choices,
    )

    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.PENDING,
    )

    amount = models.DecimalField(
        max_digits=20,
        decimal_places=8,
        validators=[
            MinValueValidator(
                Decimal("0.00000001")
            ),
        ],
    )

    balance_after = models.DecimalField(
        max_digits=20,
        decimal_places=8,
        null=True,
        blank=True,
    )

    reference = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
    )

    description = models.CharField(
        max_length=255,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = [
            "-created_at",
        ]

        indexes = [
            models.Index(
                fields=["wallet", "-created_at"]
            ),
            models.Index(
                fields=["status"]
            ),
        ]

    def __str__(self):
        return (
            f"{self.reference} - "
            f"{self.transaction_type}"
        )


class LedgerTransaction(models.Model):
    reference = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    kind = models.CharField(max_length=40)
    description = models.CharField(max_length=255, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def delete(self, *args, **kwargs):
        raise RuntimeError("Ledger transactions are immutable.")


class LedgerEntry(models.Model):
    class Direction(models.TextChoices):
        DEBIT = "DEBIT", "Debit"
        CREDIT = "CREDIT", "Credit"

    transaction = models.ForeignKey(LedgerTransaction, on_delete=models.PROTECT, related_name="entries")
    wallet = models.ForeignKey(Wallet, null=True, blank=True, on_delete=models.PROTECT, related_name="ledger_entries")
    account_code = models.CharField(max_length=80, db_index=True)
    direction = models.CharField(max_length=6, choices=Direction.choices)
    amount_irt = models.PositiveBigIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["wallet", "direction", "created_at"])]

    def save(self, *args, **kwargs):
        if self.pk:
            raise RuntimeError("Ledger entries are immutable.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise RuntimeError("Ledger entries are immutable.")


class BankCard(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="bank_cards")
    title = models.CharField(max_length=100, blank=True)
    card_last4 = models.CharField(max_length=4, blank=True)
    card_hash = models.CharField(max_length=64, blank=True, db_index=True)
    iban = models.CharField(max_length=26, blank=True)
    is_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)


class Withdrawal(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"
        PAID = "PAID", "Paid"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="withdrawals")
    bank_card = models.ForeignKey(BankCard, on_delete=models.PROTECT, related_name="withdrawals")
    amount_irt = models.PositiveBigIntegerField()
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    ledger_transaction = models.ForeignKey(LedgerTransaction, null=True, blank=True, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class PaymentProvider(models.Model):
    class Code(models.TextChoices):
        ZARINPAL = "ZARINPAL", "Zarinpal"
        IDPAY = "IDPAY", "IDPay"

    code = models.CharField(max_length=20, choices=Code.choices, unique=True)
    title = models.CharField(max_length=100)
    is_active = models.BooleanField(default=False)
    sandbox = models.BooleanField(default=False)
    sort_order = models.PositiveSmallIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)


class Payment(models.Model):
    class Purpose(models.TextChoices):
        WALLET_DEPOSIT = "WALLET_DEPOSIT", "Wallet deposit"
        COURSE_PURCHASE = "COURSE_PURCHASE", "Course purchase"
        LEVEL_UPGRADE = "LEVEL_UPGRADE", "Level upgrade"

    class Status(models.TextChoices):
        CREATED = "CREATED", "Created"
        PENDING = "PENDING", "Pending"
        VERIFIED = "VERIFIED", "Verified"
        FAILED = "FAILED", "Failed"
        CANCELLED = "CANCELLED", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="payments")
    provider = models.ForeignKey(PaymentProvider, on_delete=models.PROTECT, related_name="payments")
    authority = models.CharField(max_length=120, blank=True, db_index=True)
    provider_reference = models.CharField(max_length=120, blank=True)
    amount_irt = models.PositiveBigIntegerField()
    purpose = models.CharField(max_length=30, choices=Purpose.choices)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.CREATED)
    idempotency_key = models.CharField(max_length=120)
    metadata = models.JSONField(default=dict, blank=True)
    ledger_transaction = models.ForeignKey(LedgerTransaction, null=True, blank=True, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    verified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "idempotency_key"], name="unique_payment_idempotency_per_user")]


class PaymentAuditLog(models.Model):
    payment = models.ForeignKey(Payment, on_delete=models.PROTECT, related_name="audit_logs")
    event = models.CharField(max_length=40)
    detail = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]


class UpgradePlan(models.Model):
    level = models.PositiveSmallIntegerField(unique=True)
    title = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    price_irt = models.PositiveBigIntegerField(default=0)
    active = models.BooleanField(default=True)
    features = models.JSONField(default=list, blank=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "level"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(level__gte=1, level__lte=5),
                name="upgrade_plan_level_between_1_and_5",
            ),
            models.CheckConstraint(
                condition=models.Q(level__gt=1) | models.Q(price_irt=0),
                name="upgrade_plan_level_1_is_free",
            ),
        ]

    def save(self, *args, **kwargs):
        if self.level == 1:
            self.price_irt = 0
        super().save(*args, **kwargs)
