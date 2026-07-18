from django.db import models
from django.conf import settings


class SignalStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    PENDING = "pending", "Pending"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"


class MarketType(models.TextChoices):
    FOREX = "forex", "Forex"
    CRYPTO = "crypto", "Crypto"
    GOLD = "gold", "Gold"
    STOCK = "stock", "Stock"
    INDEX = "index", "Index"


class Direction(models.TextChoices):
    BUY = "buy", "Buy"
    SELL = "sell", "Sell"


class Signal(models.Model):

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