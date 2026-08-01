from django.conf import settings
from django.db import models

from common.models import TimestampedModel


class LandingPage(TimestampedModel):
    site_key = models.SlugField(
        max_length=80,
        unique=True,
        default="main",
    )
    site_name = models.CharField(max_length=150, blank=True)
    page_title = models.CharField(max_length=250, blank=True)
    meta_title = models.CharField(max_length=250, blank=True)
    meta_description = models.TextField(blank=True)
    canonical_url = models.URLField(max_length=500, blank=True)
    logo = models.ImageField(
        upload_to="landing/branding/",
        null=True,
        blank=True,
    )
    favicon = models.ImageField(
        upload_to="landing/branding/",
        null=True,
        blank=True,
    )
    og_image = models.ImageField(
        upload_to="landing/seo/",
        null=True,
        blank=True,
    )
    support_email = models.EmailField(blank=True)
    support_phone = models.CharField(max_length=30, blank=True)
    social_links = models.JSONField(default=dict, blank=True)
    extra_settings = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["site_key"]

    def __str__(self):
        return self.site_name or self.site_key


class LandingSection(TimestampedModel):
    class Type(models.TextChoices):
        HERO = "HERO", "Hero"
        FEATURES = "FEATURES", "Features"
        STATS = "STATS", "Statistics"
        ABOUT = "ABOUT", "About"
        CTA = "CTA", "Call to action"
        FAQ = "FAQ", "FAQ"
        TESTIMONIALS = "TESTIMONIALS", "Testimonials"
        PARTNERS = "PARTNERS", "Partners"
        CUSTOM = "CUSTOM", "Custom"

    page = models.ForeignKey(
        LandingPage,
        on_delete=models.CASCADE,
        related_name="sections",
    )
    key = models.SlugField(max_length=120)
    section_type = models.CharField(
        max_length=30,
        choices=Type.choices,
        default=Type.CUSTOM,
    )
    title = models.CharField(max_length=250, blank=True)
    subtitle = models.TextField(blank=True)
    content = models.JSONField(default=dict, blank=True)
    image = models.ImageField(
        upload_to="landing/sections/",
        null=True,
        blank=True,
    )
    cta_label = models.CharField(max_length=120, blank=True)
    cta_url = models.CharField(max_length=500, blank=True)
    display_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_landing_sections",
    )

    class Meta:
        ordering = ["display_order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["page", "key"],
                name="unique_landing_section_key_per_page",
            )
        ]
        indexes = [
            models.Index(
                fields=["page", "is_active", "display_order"],
            )
        ]

    def __str__(self):
        return f"{self.page} - {self.key}"
