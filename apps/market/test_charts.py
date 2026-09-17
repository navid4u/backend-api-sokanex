from datetime import timedelta
from unittest.mock import patch
from urllib.error import URLError

from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import User
from .chart_services import MarketChartService
from .models import MarketChartSnapshot


class MarketChartAPITests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(username="chart-user", password="StrongPass123!")
        self.client.force_authenticate(self.user)
        self.url = reverse("market-charts")
        self.params = {
            "market": "crypto", "symbol": "BINANCE:BTCUSDT", "range": "1d"
        }
        self.points = [
            {"timestamp": "2026-08-14T08:00:00Z", "value": 100},
            {"timestamp": "2026-08-14T09:00:00Z", "value": 110},
        ]

    def test_requires_authentication(self):
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.get(self.url, self.params).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_provider_fallback_normalizes_response(self):
        with patch.object(MarketChartService, "_coingecko", side_effect=URLError("down")), patch.object(
            MarketChartService, "_coinbase", return_value=self.points
        ):
            response = self.client.get(self.url, self.params)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["data"]["source"], "coinbase")
        self.assertEqual(response.data["data"]["price"], 110.0)
        self.assertEqual(response.data["data"]["change_percent"], 10.0)
        self.assertFalse(response.data["data"]["is_stale"])

    def test_fresh_cache_avoids_provider_request(self):
        with patch.object(MarketChartService, "_coingecko", return_value=self.points):
            self.client.get(self.url, self.params)
        with patch.object(MarketChartService, "_coingecko") as provider:
            response = self.client.get(self.url, self.params)
        provider.assert_not_called()
        self.assertFalse(response.data["data"]["is_stale"])

    def test_last_known_cache_is_returned_as_stale(self):
        with patch.object(MarketChartService, "_coingecko", return_value=self.points):
            self.client.get(self.url, self.params)
        cache.delete("market:chart:v1:fresh:crypto:BINANCE:BTCUSDT:1d:auto")
        with patch.object(MarketChartService, "_coingecko", side_effect=URLError("down")), patch.object(
            MarketChartService, "_coinbase", side_effect=URLError("down")
        ):
            response = self.client.get(self.url, self.params)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["data"]["is_stale"])

    def test_last_known_database_snapshot_survives_cache_loss(self):
        with patch.object(MarketChartService, "_coingecko", return_value=self.points):
            self.client.get(self.url, self.params)
        cache.clear()
        with patch.object(MarketChartService, "_coingecko", side_effect=URLError("down")), patch.object(
            MarketChartService, "_coinbase", side_effect=URLError("down")
        ):
            response = self.client.get(self.url, self.params)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(MarketChartSnapshot.objects.count(), 1)
        self.assertFalse(response.data["data"]["is_stale"])

    def test_invalid_symbol_is_rejected_before_provider_call(self):
        with patch.object(MarketChartService, "_coingecko") as provider:
            response = self.client.get(self.url, {**self.params, "symbol": "https://evil.test"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        provider.assert_not_called()

    def test_controlled_503_when_no_provider_or_cache_exists(self):
        with patch.object(MarketChartService, "_coingecko", side_effect=URLError("down")), patch.object(
            MarketChartService, "_coinbase", side_effect=URLError("down")
        ):
            response = self.client.get(self.url, self.params)
        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertFalse(response.data["success"])
        self.assertIn("source", response.data["errors"])

    def test_forex_twelve_data_returns_numeric_historical_series(self):
        points = [
            {"timestamp": f"2026-09-15T{hour:02d}:00:00Z", "value": 1.08 + hour / 10000}
            for hour in range(24)
        ]
        params = {"market": "forex", "symbol": "EURUSD", "range": "5d", "interval": "1h"}
        with patch.object(MarketChartService, "_twelve_data", return_value=points):
            response = self.client.get(self.url, params)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data["data"]
        self.assertEqual(data["symbol"], "EURUSD")
        self.assertEqual(data["source"], "TWELVE_DATA")
        self.assertGreaterEqual(len(data["points"]), 24)
        self.assertTrue(all(isinstance(value, float) for value in data["points"]))
        self.assertEqual(data["price"], data["points"][-1])
        self.assertFalse(data["stale"])

    def test_forex_prefixes_normalize_to_same_cache_identity(self):
        points = [
            {"timestamp": f"2026-09-15T{hour:02d}:00:00Z", "value": 1.1 + hour / 10000}
            for hour in range(24)
        ]
        params = {"market": "forex", "symbol": "FX:EURUSD", "range": "5d", "interval": "1h"}
        with patch.object(MarketChartService, "_twelve_data", return_value=points) as provider:
            prefixed = self.client.get(self.url, params)
            bare = self.client.get(self.url, {**params, "symbol": "EURUSD"})
        self.assertEqual(prefixed.status_code, status.HTTP_200_OK)
        self.assertEqual(bare.status_code, status.HTTP_200_OK)
        self.assertEqual(prefixed.data["data"], bare.data["data"])
        provider.assert_called_once()

    def test_gold_prefixed_and_bare_symbols_are_supported(self):
        points = [
            {"timestamp": f"2026-09-15T{hour:02d}:00:00Z", "value": 2300 + hour}
            for hour in range(24)
        ]
        params = {"market": "forex", "symbol": "OANDA:XAUUSD", "range": "5d", "interval": "1h"}
        with patch.object(MarketChartService, "_twelve_data", return_value=points) as provider:
            prefixed = self.client.get(self.url, params)
            bare = self.client.get(self.url, {**params, "symbol": "XAUUSD"})
        self.assertEqual(prefixed.status_code, status.HTTP_200_OK)
        self.assertEqual(bare.status_code, status.HTTP_200_OK)
        self.assertEqual(prefixed.data["data"]["symbol"], "XAUUSD")
        provider.assert_called_once()

    def test_forex_provider_failure_uses_stale_cache(self):
        points = [
            {"timestamp": f"2026-09-15T{hour:02d}:00:00Z", "value": 1.2 + hour / 10000}
            for hour in range(24)
        ]
        params = {"market": "forex", "symbol": "EURUSD", "range": "5d", "interval": "1h"}
        with patch.object(MarketChartService, "_twelve_data", return_value=points):
            self.client.get(self.url, params)
        cache.delete("market:chart:v1:fresh:forex:FX:EURUSD:5d:1h")
        MarketChartSnapshot.objects.update(updated_at=timezone.now() - timedelta(minutes=10))
        with patch.object(MarketChartService, "_twelve_data", side_effect=URLError("down")), patch.object(
            MarketChartService, "_configured_forex", side_effect=URLError("down")
        ):
            response = self.client.get(self.url, params)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["data"]["stale"])

    def test_forex_single_quote_without_cache_returns_precise_503(self):
        params = {"market": "forex", "symbol": "EURUSD", "range": "5d", "interval": "1h"}
        one_point = [{"timestamp": "2026-09-15T00:00:00Z", "value": 1.08}]
        with patch.object(MarketChartService, "_twelve_data", return_value=one_point), patch.object(
            MarketChartService, "_configured_forex", side_effect=URLError("down")
        ):
            response = self.client.get(self.url, params)
        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(response.data["error_code"], "historical_series_unavailable")
