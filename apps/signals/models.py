from pathlib import Path
import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

from common.content_access import LevelRestrictedContent


def generate_signal_id():
    return f"SIG-{uuid.uuid4().hex[:12].upper()}"


def manual_signal_post_upload(instance, filename):
    extension = Path(filename).suffix.lower()
    return f"signals/manual/{uuid.uuid4().hex}{extension}"


def vip_signal_post_upload(instance, filename):
    extension = Path(filename).suffix.lower()
    return f"signals/vip/{instance.channel.lower()}/{uuid.uuid4().hex}{extension}"


def vip_signal_video_upload(instance, filename):
    extension = Path(filename).suffix.lower()
    return f"signals/vip/{instance.channel.lower()}/video/{uuid.uuid4().hex}{extension}"


def vip_signal_audio_upload(instance, filename):
    extension = Path(filename).suffix.lower()
    return f"signals/vip/{instance.channel.lower()}/audio/{uuid.uuid4().hex}{extension}"


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

    class Source(models.TextChoices):
        LEGACY = "LEGACY", "سامانه داخلی"
        TELEGRAM_API = "TELEGRAM_API", "API تلگرام"

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
    source = models.CharField(max_length=20, choices=Source.choices, default=Source.LEGACY, db_index=True)
    external_id = models.CharField(max_length=150, null=True, blank=True, unique=True)
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


class ManualSignalPost(models.Model):
    class Source(models.TextChoices):
        SUPER_ADMIN_MANUAL = "SUPER_ADMIN_MANUAL", "ثبت دستی سوپر ادمین"

    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="manual_signal_posts",
    )
    text = models.TextField(blank=True, max_length=4000)
    image = models.ImageField(
        upload_to=manual_signal_post_upload,
        null=True,
        blank=True,
    )
    source = models.CharField(
        max_length=30,
        choices=Source.choices,
        default=Source.SUPER_ADMIN_MANUAL,
        editable=False,
    )
    is_active = models.BooleanField(default=True, db_index=True)
    published_at = models.DateTimeField(default=timezone.now, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-published_at", "-id"]
        indexes = [
            models.Index(
                fields=["is_active", "-published_at"],
                name="signals_man_is_acti_81b9bb_idx",
            )
        ]

    def __str__(self):
        return self.text[:80] or f"Manual signal post {self.pk}"


class VIPSignalPost(models.Model):
    class Channel(models.TextChoices):
        CRYPTO = "CRYPTO", "کانال وی آی پی سوکانکس (کریپتو)"
        FOREX = "FOREX", "کانال وی آی پی سوکانکس (فارکس)"

    class Source(models.TextChoices):
        TELEGRAM_API = "TELEGRAM_API", "API تلگرام"

    channel = models.CharField(max_length=10, choices=Channel.choices, db_index=True)
    text = models.TextField(max_length=20000)
    image = models.ImageField(upload_to=vip_signal_post_upload, null=True, blank=True)
    video = models.FileField(upload_to=vip_signal_video_upload, null=True, blank=True)
    audio = models.FileField(upload_to=vip_signal_audio_upload, null=True, blank=True)
    external_id = models.CharField(max_length=180, null=True, blank=True)
    source = models.CharField(
        max_length=20,
        choices=Source.choices,
        default=Source.TELEGRAM_API,
        editable=False,
    )
    is_active = models.BooleanField(default=True, db_index=True)
    published_at = models.DateTimeField(default=timezone.now, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-published_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["channel", "external_id"],
                condition=models.Q(external_id__isnull=False),
                name="uniq_vip_signal_channel_external",
            )
        ]
        indexes = [
            models.Index(
                fields=["channel", "is_active", "-published_at"],
                name="vip_signal_channel_feed_idx",
            )
        ]

    def __str__(self):
        return f"{self.channel}: {self.text[:80]}"
