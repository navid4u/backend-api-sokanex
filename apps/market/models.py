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


class NewsSource(models.Model):
    class Language(models.TextChoices):
        FA = "fa", "Persian"
        EN = "en", "English"

    name = models.CharField(max_length=150)
    feed_url = models.URLField(max_length=500, unique=True)
    language = models.CharField(max_length=2, choices=Language.choices, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)
    syndication_allowed = models.BooleanField(
        default=False,
        help_text="Confirm that this source permits headline/summary syndication.",
    )
    terms_url = models.URLField(max_length=500, blank=True)
    fetch_interval_minutes = models.PositiveSmallIntegerField(default=5)
    last_fetched_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["language", "name", "id"]

    def __str__(self):
        return self.name


class NewsArticle(models.Model):
    stable_id = models.CharField(max_length=64, unique=True)
    source = models.ForeignKey(NewsSource, on_delete=models.CASCADE, related_name="articles")
    guid = models.CharField(max_length=500, blank=True)
    title = models.CharField(max_length=500)
    summary = models.TextField(blank=True)
    url = models.URLField(max_length=1000)
    canonical_url = models.URLField(max_length=1000, db_index=True)
    published_at = models.DateTimeField(db_index=True)
    fetched_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-published_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["source", "canonical_url"], name="unique_news_source_canonical_url"
            )
        ]

    def __str__(self):
        return self.title


class CryptoMarketSnapshot(models.Model):
    market_cap = models.DecimalField(max_digits=30, decimal_places=2)
    market_cap_change_24h = models.FloatField()
    volume_24h = models.DecimalField(max_digits=30, decimal_places=2)
    volume_change_24h = models.FloatField()
    btc_dominance = models.FloatField()
    eth_dominance = models.FloatField()
    tether_price_irr = models.DecimalField(max_digits=20, decimal_places=2)
    fear_greed_value = models.PositiveSmallIntegerField()
    source = models.CharField(max_length=40, default="aggregated")
    captured_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-captured_at", "-id"]
