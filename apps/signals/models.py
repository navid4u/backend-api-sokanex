from django.db import models
from django.conf import settings
from common.content_access import LevelRestrictedContent
import uuid


def generate_signal_id():
    return f"SIG-{uuid.uuid4().hex[:12].upper()}"


class SignalStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    PENDING = "pending", "Pending"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"
    ACTIVE = "active", "Active"
    SUCCESSFUL = "successful", "Successful"
    FAILED = "failed", "Failed"
    CANCELLED = "cancelled", "Cancelled"


class MarketType(models.TextChoices):
    FOREX = "forex", "Forex"
    CRYPTO = "crypto", "Crypto"
    GOLD = "gold", "Gold"
    STOCK = "stock", "Stock"
    INDEX = "index", "Index"


class Direction(models.TextChoices):
    BUY = "buy", "Buy"
    SELL = "sell", "Sell"


class Signal(LevelRestrictedContent):

    signal_id = models.CharField(max_length=20, unique=True, null=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.signal_id:
            self.signal_id = generate_signal_id()
        super().save(*args, **kwargs)

    title = models.CharField(max_length=200)

    symbol = models.CharField(max_length=50)

    market = models.CharField(
        max_length=20,
        choices=MarketType.choices,
    )

    direction = models.CharField(
        max_length=10,
        choices=Direction.choices,
    )

    order_type = models.CharField(
        max_length=10,
        choices=(("market", "Market"), ("limit", "Limit"), ("stop", "Stop")),
        default="market",
    )
    timeframe = models.CharField(max_length=30, blank=True)

    entry_price = models.DecimalField(
        max_digits=20,
        decimal_places=8,
    )

    stop_loss = models.DecimalField(
        max_digits=20,
        decimal_places=8,
    )

    take_profit = models.DecimalField(
        max_digits=20,
        decimal_places=8,
    )

    description = models.TextField(blank=True)

    image = models.ImageField(
        upload_to="signals/",
        blank=True,
        null=True,
    )

    status = models.CharField(
        max_length=20,
        choices=SignalStatus.choices,
        default=SignalStatus.PENDING,
    )

    rejection_reason = models.TextField(
        blank=True,
    )
    result_price = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    result_percent = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="signals",
    )

    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_signals",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.symbol} - {self.direction}"


class SignalUpdate(models.Model):
    signal = models.ForeignKey(Signal, on_delete=models.CASCADE, related_name="updates")
    title = models.CharField(max_length=200)
    message = models.TextField()
    status = models.CharField(max_length=20, choices=SignalStatus.choices, blank=True)
    image = models.ImageField(upload_to="signals/updates/images/%Y/%m/", null=True, blank=True)
    audio = models.FileField(upload_to="signals/updates/audio/%Y/%m/", null=True, blank=True)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="signal_updates")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at", "id"]
