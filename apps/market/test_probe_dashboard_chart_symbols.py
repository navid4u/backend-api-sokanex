import io
import json
from unittest.mock import patch
from urllib.error import HTTPError

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase

from .chart_services import MarketChartService, MarketProviderResponseError
from .management.commands.probe_dashboard_chart_symbols import safe_failure_code


class ChartProbeDiagnosticTests(SimpleTestCase):
    def test_provider_response_code_is_sanitized(self):
        error = ValueError("Generic provider failure")
        error.__cause__ = MarketProviderResponseError(429)
        self.assertEqual(safe_failure_code(error), "PROVIDER_429")

    def test_probe_reports_http_code_without_url_or_secret(self):
        error = HTTPError(
            "https://provider.example/time_series?apikey=TOP_SECRET", 429,
            "TOP_SECRET", None, None,
        )
        output = io.StringIO()
        with patch.object(MarketChartService, "_providers", return_value=(("test-provider", lambda *args: (_ for _ in ()).throw(error)),)):
            with self.assertRaises(CommandError):
                call_command("probe_dashboard_chart_symbols", market="crypto", range_value="1d", stdout=output)
        rendered = output.getvalue()
        self.assertNotIn("TOP_SECRET", rendered)
        payload = json.loads(rendered)
        self.assertEqual(payload["passed"], 0)
        self.assertEqual(payload["total"], 10)
        self.assertEqual(payload["results"][0]["attempts"], [{"source": "test-provider", "code": "HTTP_429"}])
