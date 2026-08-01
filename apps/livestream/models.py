from django.conf import settings
from django.db import models
from django.utils.text import slugify
from common.content_access import LevelRestrictedContent
import base64
import hashlib
from cryptography.fernet import Fernet, InvalidToken


class LiveEvent(LevelRestrictedContent):

    class Status(models.TextChoices):
        SCHEDULED = "SCHEDULED", "Scheduled"
        LIVE = "LIVE", "Live"
        ENDED = "ENDED", "Ended"
        CANCELLED = "CANCELLED", "Cancelled"

    title = models.CharField(
        max_length=250,
    )

    slug = models.SlugField(
        max_length=280,
        unique=True,
        allow_unicode=True,
        blank=True,
    )

    description = models.TextField(
        blank=True,
    )

    thumbnail = models.ImageField(
        upload_to="livestream/thumbnails/",
        null=True,
        blank=True,
    )

    stream_url = models.URLField(
        max_length=500,
        blank=True,
    )

    replay_url = models.URLField(
        max_length=500,
        blank=True,
    )
    provider = models.CharField(
        max_length=20,
        choices=(("MANUAL", "Manual"), ("ALOCOM", "Alocom")),
        default="MANUAL",
    )
    provider_event_id = models.CharField(max_length=150, blank=True)
    provider_join_url = models.URLField(max_length=500, blank=True)
    provider_metadata = models.JSONField(default=dict, blank=True)

    starts_at = models.DateTimeField()

    ends_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.SCHEDULED,
    )

    host = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="hosted_live_events",
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_live_events",
    )

    is_active = models.BooleanField(
        default=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ["starts_at"]

        indexes = [
            models.Index(
                fields=[
                    "status",
                    "starts_at",
                ]
            ),
            models.Index(
                fields=[
                    "is_active",
                    "starts_at",
                ]
            ),
        ]

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(
                self.title,
                allow_unicode=True,
            ) or "live-event"

            slug = base_slug
            counter = 2

            while LiveEvent.objects.filter(
                slug=slug
            ).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1

            self.slug = slug

        super().save(*args, **kwargs)

    def __str__(self):
        return self.title


class AlocomSettings(models.Model):
    api_base_url = models.URLField(default="https://pnlapi.alocom.co")
    api_token_encrypted = models.TextField(blank=True, editable=False)
    enabled = models.BooleanField(default=False)
    request_timeout_seconds = models.PositiveSmallIntegerField(default=20)
    verify_ssl = models.BooleanField(default=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="alocom_settings_updates",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Alocom settings"

    @staticmethod
    def _fernet():
        digest = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
        return Fernet(base64.urlsafe_b64encode(digest))

    def set_api_token(self, value):
        self.api_token_encrypted = self._fernet().encrypt(value.encode()).decode() if value else ""

    def get_api_token(self):
        if not self.api_token_encrypted:
            return ""
        try:
            return self._fernet().decrypt(self.api_token_encrypted.encode()).decode()
        except InvalidToken:
            return ""

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return "Alocom integration settings"
