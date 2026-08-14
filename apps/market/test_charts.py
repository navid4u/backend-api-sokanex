from unittest.mock import patch
from urllib.error import URLError

from django.core.cache import cache
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import User
from .chart_services import MarketChartService


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
