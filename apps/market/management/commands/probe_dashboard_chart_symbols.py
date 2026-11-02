import json
from urllib.error import HTTPError, URLError

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.market.chart_services import CHART_SYMBOLS, MarketChartService, MarketProviderResponseError
from apps.market.http import MarketResponseTooLarge


def safe_failure_code(error):
    """Report only stable error categories/codes, never exception text or URL."""
    current = error
    while current is not None:
        if isinstance(current, MarketProviderResponseError):
            return f"PROVIDER_{current.safe_code}"
        if isinstance(current, HTTPError):
            return f"HTTP_{current.code}"
        if isinstance(current, MarketResponseTooLarge):
            return "RESPONSE_TOO_LARGE"
        if isinstance(current, TimeoutError):
            return "TIMEOUT"
        if isinstance(current, URLError):
            return "NETWORK_ERROR"
        current = current.__cause__
    if isinstance(error, (KeyError, TypeError, IndexError)):
        return "INVALID_PROVIDER_PAYLOAD"
    if isinstance(error, ValueError):
        return "INVALID_OR_INSUFFICIENT_HISTORY"
    return "PROVIDER_ERROR"


class Command(BaseCommand):
    help = "Read-only live-provider probe for dashboard chart symbols; never prints prices or API credentials."

    def add_arguments(self, parser):
        parser.add_argument("--range", dest="range_value", choices=("1d", "5d"), default="1d")
        parser.add_argument("--market", choices=("crypto", "forex", "all"), default="all")

    def handle(self, *args, **options):
        markets = CHART_SYMBOLS if options["market"] == "all" else {options["market"]: CHART_SYMBOLS[options["market"]]}
        results = []
        for market, symbols in markets.items():
            for symbol in symbols:
                result = {"market": market, "symbol": symbol, "range": options["range_value"], "ok": False}
                attempts = []
                for source, provider in MarketChartService._providers(market, symbol):
                    try:
                        points = provider(symbol, options["range_value"], "1h")
                    except Exception as error:
                        attempts.append({"source": source, "code": safe_failure_code(error)})
                        continue
                    try:
                        normalized = MarketChartService._normalize(market, symbol, points, source)
                    except (ValueError, KeyError, TypeError, IndexError):
                        attempts.append({"source": source, "code": "INVALID_OR_INSUFFICIENT_HISTORY"})
                        continue
                    result.update({
                        "ok": True, "source": source, "points": len(normalized["points"]),
                        "checked_at": timezone.now().isoformat(),
                    })
                    break
                if not result["ok"]:
                    result["attempts"] = attempts
                results.append(result)
        self.stdout.write(json.dumps({"results": results, "passed": sum(row["ok"] for row in results),
                                      "total": len(results)}, ensure_ascii=False))
        if any(not row["ok"] for row in results):
            raise CommandError("At least one symbol has no usable live provider history.")
