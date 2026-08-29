from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class AISettings(models.Model):
    enabled = models.BooleanField(default=False)
    provider = models.CharField(max_length=30, default="GAPGPT")
    base_url = models.URLField(default="https://api.gapgpt.app/v1")
    api_token_encrypted = models.TextField(blank=True)
    model = models.CharField(max_length=150, blank=True)
    financial_system_prompt = models.TextField(default="به فارسی پاسخ بده و اصول مدیریت ریسک را رعایت کن.")
    technical_system_prompt = models.TextField(default="نمودار را به فارسی و با بیان عدم قطعیت تحلیل کن.")
    temperature = models.FloatField(default=0.3, validators=[MinValueValidator(0), MaxValueValidator(2)])
    max_tokens = models.PositiveIntegerField(default=1200, validators=[MinValueValidator(128), MaxValueValidator(8192)])
    daily_user_limit = models.PositiveIntegerField(default=20)
    image_daily_user_limit = models.PositiveIntegerField(default=5)
    request_timeout = models.PositiveSmallIntegerField(default=45, validators=[MinValueValidator(10), MaxValueValidator(120)])
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        return None


class AISettingsAuditLog(models.Model):
    ai_settings = models.ForeignKey(AISettings, on_delete=models.PROTECT, related_name="audit_logs")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    changed_fields = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)


class AIUsageLog(models.Model):
    class Mode(models.TextChoices):
        FINANCIAL = "financial", "Financial chat"
        TECHNICAL = "technical", "Technical image"

    class Status(models.TextChoices):
        SUCCESS = "success", "Success"
        ERROR = "error", "Error"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="ai_usage")
    mode = models.CharField(max_length=20, choices=Mode.choices, db_index=True)
    status = models.CharField(max_length=20, choices=Status.choices, db_index=True)
    input_tokens = models.PositiveIntegerField(default=0)
    output_tokens = models.PositiveIntegerField(default=0)
    latency_ms = models.PositiveIntegerField(default=0)
    provider_status = models.PositiveSmallIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [models.Index(fields=["user", "mode", "created_at"])]
