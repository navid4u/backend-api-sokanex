from unittest.mock import patch
from urllib.error import HTTPError, URLError

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
            {"market_cap_usd": 1000, "volume_24h_usd": 200, "bitcoin_dominance_percentage": 59.3, "market_cap_change_24h": 3.2, "volume_24h_change_24h": 4.2},
            {"quotes": {"USD": {"market_cap": 81.5}}},
            {"data": [{"value": "52"}]},
            {"bids": [["899000", "1"]], "asks": [["901000", "1"]]},
        ]
        first = self.client.get("/api/market/crypto-snapshot/")
        second = self.client.get("/api/market/crypto-snapshot/")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.data["fear_greed"], {"value": 52, "label": "خنثی"})
        self.assertFalse(first.data["stale"])
        self.assertEqual(request_json.call_count, 4)
        self.assertEqual(second.data["market_cap"], 1000.0)

    @patch("apps.market.services._request_json")
    def test_coingecko_fallback_when_coinpaprika_is_unavailable(self, request_json):
        request_json.side_effect = [
            HTTPError("https://api.coinpaprika.com/v1/global", 503, "unavailable", {}, None),
            {"data": {"total_market_cap": {"usd": 2000}, "total_volume": {"usd": 500}, "market_cap_change_percentage_24h_usd": 1.5, "volume_change_percentage_24h_usd": 2.5, "market_cap_percentage": {"btc": 55, "eth": 10}}},
            {"data": [{"value": "60"}]},
            {"bids": [["909000", "1"]], "asks": [["911000", "1"]]},
        ]
        response = self.client.get("/api/market/crypto-snapshot/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["eth_dominance"], 10.0)
        self.assertEqual(response.data["volume_change_24h"], 2.5)

    @patch("apps.market.services._request_json")
    def test_tether_provider_chain_skips_dns_failures(self, request_json):
        request_json.side_effect = [
            URLError("tabdeal dns"),
            {"result": {"bid": [{"price": "920000"}], "ask": [{"price": "922000"}]}},
        ]
        self.assertEqual(CryptoSnapshotService._tether_irt_price(), 921000)

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
