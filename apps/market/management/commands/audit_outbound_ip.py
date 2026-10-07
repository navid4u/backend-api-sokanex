"""Identify configured outbound services resolving to an IP without exposing URLs or keys."""

import ipaddress
import socket
from urllib.parse import urlsplit

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.market.models import NewsSource


URL_SETTINGS = (
    "MARKET_DATA_PROVIDER_URL",
    "FOREX_CHART_PROVIDER_URL",
    "GOLD_CHART_PROVIDER_URL",
    "TWELVE_DATA_BASE_URL",
    "COINGECKO_GLOBAL_URL",
    "COINPAPRIKA_GLOBAL_URL",
    "COINPAPRIKA_ETH_TICKER_URL",
    "FEAR_GREED_URL",
    "TETHER_PRICE_URL",
    "NOBITEX_USDT_IRT_URL",
    "TABDEAL_USDT_IRT_URL",
    "WALLEX_USDT_TMN_URL",
    "TGJU_API_URL",
    "CRM_BASE_URL",
)
HARDCODED_OUTBOUND_HOSTS = (
    "brsapi.ir",
    "api.exchange.coinbase.com",
    "api.frankfurter.app",
    "rest.payamak-panel.com",
)


class Command(BaseCommand):
    help = "Read-only check of configured outbound service DNS against one IP; never prints API keys or full URLs."

    def add_arguments(self, parser):
        parser.add_argument("ip", help="IPv4 or IPv6 address to investigate")

    def handle(self, *args, **options):
        try:
            target = str(ipaddress.ip_address(options["ip"]))
        except ValueError as exc:
            raise CommandError("A valid IP address is required.") from exc

        candidates = []
        for name in URL_SETTINGS:
            value = getattr(settings, name, "")
            if value:
                candidates.append((f"setting:{name}", str(value)))
        candidates.extend((f"built-in:{host}", f"https://{host}/") for host in HARDCODED_OUTBOUND_HOSTS)
        candidates.extend(
            (f"news-source:{source.pk}", source.feed_url)
            for source in NewsSource.objects.filter(is_active=True, syndication_allowed=True)
            .only("id", "feed_url").iterator()
        )
        from apps.ai_assistant.models import AISettings

        ai_settings = AISettings.objects.only("base_url").first()
        if ai_settings and ai_settings.base_url:
            candidates.append(("assistant:base_url", ai_settings.base_url))

        resolved = {}
        matches = 0
        failed = 0
        for label, url in candidates:
            hostname = urlsplit(url).hostname
            if not hostname:
                continue
            if hostname not in resolved:
                try:
                    resolved[hostname] = {
                        str(ipaddress.ip_address(result[4][0]))
                        for result in socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)
                    }
                except OSError:
                    resolved[hostname] = set()
                    failed += 1
            if target in resolved[hostname]:
                self.stdout.write(f"MATCH {label} host={hostname}")
                matches += 1

        self.stdout.write(
            f"Checked {len(candidates)} configured destinations; matches={matches}; "
            f"DNS failures={failed}. DNS results are current, not historical proof."
        )
