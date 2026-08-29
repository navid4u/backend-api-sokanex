from django.contrib import admin
from .models import CryptoMarketSnapshot, EconomicEvent, NewsArticle, NewsSource

admin.site.register(EconomicEvent)
admin.site.register(CryptoMarketSnapshot)


@admin.register(NewsSource)
class NewsSourceAdmin(admin.ModelAdmin):
    list_display = ("name", "language", "is_active", "syndication_allowed", "last_fetched_at")
    list_filter = ("language", "is_active", "syndication_allowed")
    search_fields = ("name", "feed_url")
    readonly_fields = ("last_fetched_at", "last_error", "created_at", "updated_at")


@admin.register(NewsArticle)
class NewsArticleAdmin(admin.ModelAdmin):
    list_display = ("title", "source", "published_at", "fetched_at")
    list_filter = ("source__language", "source")
    search_fields = ("title", "summary", "canonical_url")
    readonly_fields = ("stable_id", "fetched_at")
