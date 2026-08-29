from unittest.mock import patch
from urllib.error import HTTPError

from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APITestCase

from .models import CryptoMarketSnapshot
from .services import CryptoSnapshotService


@override_settings(MARKET_SNAPSHOT_CACHE_SECONDS=120, TETHER_PRICE_IRR=0)
class CryptoSnapshotTests(APITestCase):
    def setUp(self):
        cache.clear()

    @patch("apps.market.services._request_json")
    def test_fetch_and_shared_cache(self, request_json):
        request_json.side_effect = [
            {"data": {"total_market_cap": {"usd": 1000}, "total_volume": {"usd": 200}, "market_cap_change_percentage_24h_usd": 3.2, "market_cap_percentage": {"btc": 59.3, "eth": 8.15}}},
            {"data": [{"value": "52"}]},
            {"tether": {"irr": 900000}},
        ]
        first = self.client.get("/api/market/crypto-snapshot/")
        second = self.client.get("/api/market/crypto-snapshot/")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.data["fear_greed"], {"value": 52, "label": "خنثی"})
        self.assertFalse(first.data["stale"])
        self.assertEqual(request_json.call_count, 3)
        self.assertEqual(second.data["market_cap"], 1000.0)

    @patch("apps.market.services._request_json")
    def test_coinpaprika_fallback_when_coingecko_is_rate_limited(self, request_json):
        request_json.side_effect = [
            HTTPError("https://api.coingecko.com/api/v3/global", 429, "rate limit", {}, None),
            {"market_cap_usd": 2000, "volume_24h_usd": 500, "bitcoin_dominance_percentage": 55, "market_cap_change_24h": 1.5, "volume_24h_change_24h": 2.5},
            {"quotes": {"USD": {"market_cap": 200}}},
            {"data": [{"value": "60"}]},
            {"tether": {"irr": 910000}},
        ]
        response = self.client.get("/api/market/crypto-snapshot/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["eth_dominance"], 10.0)
        self.assertEqual(response.data["volume_change_24h"], 2.5)

    @patch("apps.market.services.CryptoSnapshotService._fetch", side_effect=TimeoutError)
    def test_database_fallback_is_stale(self, _fetch):
        CryptoMarketSnapshot.objects.create(market_cap=1000, market_cap_change_24h=1, volume_24h=200, volume_change_24h=2, btc_dominance=50, eth_dominance=10, tether_price_irr=900000, fear_greed_value=10)
        response = self.client.get("/api/market/crypto-snapshot/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["stale"])

    @patch("apps.market.services.CryptoSnapshotService._fetch", side_effect=TimeoutError)
    def test_no_history_returns_503(self, _fetch):
        response = self.client.get("/api/market/crypto-snapshot/")
        self.assertEqual(response.status_code, 503)
