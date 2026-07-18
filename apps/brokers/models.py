from decimal import Decimal

from django.core.validators import (
    MaxValueValidator,
    MinValueValidator,
)
from django.db import models
from django.utils.text import slugify


class Broker(models.Model):

    name = models.CharField(
        max_length=150,
        unique=True,
    )

    slug = models.SlugField(
        max_length=180,
        unique=True,
        allow_unicode=True,
        blank=True,
    )

    short_description = models.CharField(
        max_length=300,
        blank=True,
    )

    description = models.TextField(
        blank=True,
    )

    logo = models.ImageField(
        upload_to="brokers/",
        null=True,
        blank=True,
    )

    website_url = models.URLField(
        max_length=500,
    )

    registration_url = models.URLField(
        max_length=500,
        blank=True,
    )

    support_url = models.URLField(
        max_length=500,
        blank=True,
    )

    country = models.CharField(
        max_length=100,
        blank=True,
    )

    regulation = models.CharField(
        max_length=250,
        blank=True,
    )

    minimum_deposit = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[
            MinValueValidator(Decimal("0")),
        ],
    )

    rating = models.DecimalField(
        max_digits=2,
        decimal_places=1,
        default=Decimal("0"),
        validators=[
            MinValueValidator(Decimal("0")),
            MaxValueValidator(Decimal("5")),
        ],
    )

    features = models.JSONField(
        default=list,
        blank=True,
    )

    is_active = models.BooleanField(
        default=True,
    )

    sort_order = models.PositiveIntegerField(
        default=0,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = [
            "sort_order",
            "-rating",
            "name",
        ]

        indexes = [
            models.Index(
                fields=[
                    "is_active",
                    "sort_order",
                ]
            ),
            models.Index(
                fields=["country"]
            ),
        ]

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(
                self.name,
                allow_unicode=True,
            ) or "broker"

            slug = base_slug
            counter = 2

            while Broker.objects.filter(
                slug=slug
            ).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1

            self.slug = slug

        super().save(*args, **kwargs)

    def __str__(self):
        return self.name