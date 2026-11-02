import uuid
from pathlib import Path

from django.conf import settings
from django.db import models


def platform_logo_path(instance, filename):
    extension = Path(filename).suffix.lower()
    return f"platforms/{uuid.uuid4().hex}{extension}"


class Platform(models.Model):
    class Type(models.TextChoices):
        BROKER = "BROKER", "Broker"
        EXCHANGE = "EXCHANGE", "Exchange"

    platform_type = models.CharField(max_length=8, choices=Type.choices)
    name = models.CharField(max_length=120)
    subtitle = models.CharField(max_length=180, blank=True)
    description = models.TextField(blank=True)
    logo = models.ImageField(upload_to=platform_logo_path, null=True, blank=True)
    rating = models.DecimalField(max_digits=2, decimal_places=1, null=True, blank=True)
    official_url = models.URLField(max_length=2048, blank=True)
    registration_url = models.URLField(max_length=2048, blank=True)
    is_active = models.BooleanField(default=True)
    is_popular = models.BooleanField(default=False)
    sort_order = models.PositiveIntegerField(default=0)
    details = models.JSONField(default=dict, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("sort_order", "-rating", "id")
        indexes = [models.Index(fields=("platform_type", "is_active", "sort_order"), name="mp_type_active_sort_idx")]


class FieldDefinition(models.Model):
    platform_type = models.CharField(max_length=8, choices=Platform.Type.choices)
    key = models.CharField(max_length=64)
    label = models.CharField(max_length=120)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("sort_order", "id")
        constraints = [models.UniqueConstraint(fields=("platform_type", "key"), name="unique_market_platform_field")]


class PlatformChangeAudit(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    action = models.CharField(max_length=20)
    object_id = models.PositiveBigIntegerField()
    object_type = models.CharField(max_length=20)
    platform = models.ForeignKey(Platform, on_delete=models.SET_NULL, null=True, blank=True)
    field_definition = models.ForeignKey(FieldDefinition, on_delete=models.SET_NULL, null=True, blank=True)
    changed_fields = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)
