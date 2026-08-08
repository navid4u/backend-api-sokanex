from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from .models import NewsArticle, NewsSource
from .services import BASE_SYMBOLS, MarketQuoteService


class MarketV2Tests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="market-user", password="StrongPass123!")
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        cache.clear()

    def test_quotes_without_symbols_requests_all_base_symbols(self):
        response_data = {"updated_at": "2026-08-08T00:00:00+00:00", "results": []}
        with patch.object(MarketQuoteService, "get_quotes", return_value=response_data) as mocked:
            response = self.client.get("/api/market/quotes/")
        self.assertEqual(response.status_code, 200)
        mocked.assert_called_once_with(list(BASE_SYMBOLS))

    @override_settings(
        MARKET_DATA_PROVIDER_URL="", MARKET_DATA_API_KEY="", BRSAPI_API_KEY="", TGJU_ENABLED=False,
    )
    def test_quotes_never_invent_values_when_no_provider_or_cache_exists(self):
        response = self.client.get("/api/market/quotes/")
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("results", response.data)

    def test_news_without_approved_sources_is_an_empty_real_list(self):
        response = self.client.get("/api/market/news/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["results"], [])

    def test_news_only_exposes_approved_active_sources(self):
        source = NewsSource.objects.create(
            name="Licensed Feed", feed_url="https://example.com/feed.xml", language="fa",
            syndication_allowed=True, is_active=True,
        )
        NewsArticle.objects.create(
            stable_id="a" * 64, source=source, title="خبر واقعی", summary="خلاصه",
            url="https://example.com/news/1", canonical_url="https://example.com/news/1",
            published_at="2026-08-08T00:00:00Z",
        )
        with patch("apps.market.views.MarketNewsService.refresh_due_sources"):
            response = self.client.get("/api/market/news/?language=fa&limit=5")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["results"][0]["id"], "a" * 64)
        self.assertEqual(response.data["results"][0]["source_name"], "Licensed Feed")

    def test_news_validates_language_and_limit(self):
        self.assertEqual(self.client.get("/api/market/news/?language=de").status_code, 400)
        self.assertEqual(self.client.get("/api/market/news/?limit=1000").status_code, 400)
