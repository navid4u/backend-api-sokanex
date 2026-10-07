from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase, override_settings

from .models import NewsSource


class AuditOutboundIPTests(TestCase):
    @override_settings(MARKET_DATA_PROVIDER_URL="https://secret:token@provider.example/path?key=DO_NOT_PRINT")
    @patch("apps.market.management.commands.audit_outbound_ip.socket.getaddrinfo")
    def test_reports_matching_service_and_news_source_without_secrets(self, getaddrinfo):
        getaddrinfo.return_value = [(None, None, None, None, ("31.7.66.189", 443))]
        source = NewsSource.objects.create(
            name="Feed", feed_url="https://feed.example/rss?token=DO_NOT_PRINT",
            language="fa", syndication_allowed=True, is_active=True,
        )
        output = StringIO()
        call_command("audit_outbound_ip", "31.7.66.189", stdout=output)
        result = output.getvalue()
        self.assertIn("setting:MARKET_DATA_PROVIDER_URL host=provider.example", result)
        self.assertIn(f"news-source:{source.pk} host=feed.example", result)
        self.assertNotIn("secret", result)
        self.assertNotIn("token", result)
        self.assertNotIn("DO_NOT_PRINT", result)

    def test_invalid_ip_is_rejected(self):
        from django.core.management.base import CommandError

        with self.assertRaises(CommandError):
            call_command("audit_outbound_ip", "not-an-ip", stdout=StringIO())
