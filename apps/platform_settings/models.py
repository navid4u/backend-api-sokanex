from django.conf import settings
from django.db import models


class PlatformSettings(models.Model):
    site_name = models.CharField(max_length=120, default="Sokanex")
    support_email = models.EmailField(blank=True)
    support_phone = models.CharField(max_length=30, blank=True)
    maintenance_mode = models.BooleanField(default=False)
    minimum_deposit_irt = models.PositiveBigIntegerField(default=10000)
    minimum_withdrawal_irt = models.PositiveBigIntegerField(default=100000)
    maximum_withdrawal_irt = models.PositiveBigIntegerField(default=1000000000)
    withdrawal_fee_irt = models.PositiveBigIntegerField(default=0)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class SystemContent(models.Model):
    key = models.SlugField(max_length=160, unique=True)
    section = models.CharField(max_length=60, db_index=True)
    label = models.CharField(max_length=160)
    value = models.TextField(blank=True)
    multiline = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["section", "key"]

