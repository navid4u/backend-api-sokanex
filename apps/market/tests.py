from unittest.mock import patch
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from .models import MarketQuoteSnapshot, NewsArticle, NewsSource
from .services import BASE_SYMBOLS, MarketQuoteService, _extract_rows


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
    def test_quotes_gracefully_return_empty_when_no_provider_or_cache_exists(self):
        response = self.client.get("/api/market/quotes/")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["available"])
        self.assertEqual(response.data["results"], [])

    @override_settings(
        MARKET_DATA_PROVIDER_URL="", MARKET_DATA_API_KEY="", BRSAPI_API_KEY="", TGJU_ENABLED=False,
    )
    def test_quotes_use_persistent_last_known_real_snapshot(self):
        MarketQuoteSnapshot.objects.create(
            quotes={
                "usd-irr": {
                    "symbol": "usd-irr", "name": "دلار", "price": 100000,
                    "unit": "تومان", "source": "verified-provider",
                    "source_timestamp": timezone.now().isoformat(),
                }
            },
            source_updated_at=timezone.now() - timedelta(minutes=5),
        )
        response = self.client.get("/api/market/quotes/?symbols=usd-irr")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["available"])
        self.assertTrue(response.data["is_stale"])
        self.assertEqual(response.data["results"][0]["price"], 100000)

    def test_tgju_keyed_payload_extracts_current_prices_in_toman(self):
        payload = {
            "current": {
                "price_dollar_rl": {"p": "2,185,000", "d": "35,000", "dp": 1.6, "ts": "2026-09-08 14:42:00"},
                "tgju_gold_irg18": {"p": "235,091,000", "d": "5,150,000", "dp": 2.24, "ts": "2026-09-08 14:42:00"},
            }
        }
        rows = _extract_rows(payload, MarketQuoteService.aliases, "TGJU", rial_prices=True)
        self.assertEqual(rows["usd-irr"]["price"], 218500)
        self.assertEqual(rows["gold-18k"]["price"], 23509100)
        self.assertEqual(rows["usd-irr"]["source_timestamp"], "2026-09-08 14:42:00")

    @override_settings(TGJU_ENABLED=True, TGJU_API_URL="https://example.com/ajax.json", MARKET_DATA_TIMEOUT_SECONDS=8)
    def test_tgju_uses_short_timeout_without_retry(self):
        with patch("apps.market.services._request_json", return_value={"current": {}}) as request_json:
            MarketQuoteService._tgju_provider()
        request_json.assert_called_once_with(
            "https://example.com/ajax.json", timeout=4, retries=0
        )

    @override_settings(
        MARKET_DATA_PROVIDER_URL="", MARKET_DATA_API_KEY="", BRSAPI_API_KEY="", TGJU_ENABLED=True,
    )
    def test_concurrent_quote_refresh_does_not_call_provider(self):
        cache.set(MarketQuoteService.refresh_lock_key, True, 10)
        with patch.object(MarketQuoteService, "_tgju_provider") as provider:
            response = MarketQuoteService.get_quotes(["usd-irr"])
        provider.assert_not_called()
        self.assertFalse(response["available"])

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
