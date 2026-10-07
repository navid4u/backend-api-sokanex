import io
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from .chart_services import MarketChartService, _request_json as chart_request_json
from .http import MAX_MARKET_JSON_BYTES, MarketResponseTooLarge, read_market_json
from .services import _request_json as market_request_json


class ResponseBuffer(io.BytesIO):
    def __init__(self, body, headers=None):
        super().__init__(body)
        self.headers = headers or {}
        self.read_size = None

    def read(self, size=-1):
        self.read_size = size
        return super().read(size)


class MarketHTTPSizeLimitTests(SimpleTestCase):
    def test_declared_oversized_response_is_rejected_before_body_read(self):
        response = ResponseBuffer(b"{}", {"Content-Length": str(MAX_MARKET_JSON_BYTES + 1)})
        with self.assertRaises(MarketResponseTooLarge):
            read_market_json(response)
        self.assertIsNone(response.read_size)

    def test_unadvertised_oversized_response_reads_at_most_limit_plus_one(self):
        response = ResponseBuffer(b"x" * (MAX_MARKET_JSON_BYTES + 200))
        with self.assertRaises(MarketResponseTooLarge):
            read_market_json(response)
        self.assertEqual(response.read_size, MAX_MARKET_JSON_BYTES + 1)
        self.assertEqual(response.tell(), MAX_MARKET_JSON_BYTES + 1)

    def test_market_and_chart_requests_still_parse_normal_json(self):
        with patch("apps.market.services.urlopen", return_value=ResponseBuffer(b'{"price":1}')):
            self.assertEqual(market_request_json("https://provider.example/data"), {"price": 1})
        with patch("apps.market.chart_services.urlopen", return_value=ResponseBuffer(b'{"points":[]}')):
            self.assertEqual(chart_request_json("https://provider.example/chart"), {"points": []})

    def test_oversized_market_response_is_not_retried(self):
        response = ResponseBuffer(b"{}", {"Content-Length": str(MAX_MARKET_JSON_BYTES + 1)})
        with patch("apps.market.services.urlopen", return_value=response) as opener:
            with self.assertRaises(MarketResponseTooLarge):
                market_request_json("https://provider.example/data", retries=2)
        opener.assert_called_once()

    @override_settings(TWELVE_DATA_API_KEY="test-key")
    def test_oversized_chart_response_is_not_retried(self):
        with patch("apps.market.chart_services._request_json", side_effect=MarketResponseTooLarge) as request_json:
            with self.assertRaises(MarketResponseTooLarge):
                MarketChartService._twelve_data("FX:EURUSD", "5d", "1h")
        request_json.assert_called_once()
