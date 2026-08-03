from django.db import models


class EconomicEvent(models.Model):
    class Impact(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"

    external_id = models.CharField(max_length=150, unique=True)
    datetime = models.DateTimeField(db_index=True)
    currency = models.CharField(max_length=10, db_index=True)
    impact = models.CharField(max_length=10, choices=Impact.choices, db_index=True)
    title = models.CharField(max_length=300)
    actual = models.CharField(max_length=50, blank=True)
    forecast = models.CharField(max_length=50, blank=True)
    previous = models.CharField(max_length=50, blank=True)
    unit = models.CharField(max_length=30, blank=True)
    source_timestamp = models.DateTimeField()
    source = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["datetime", "id"]
