import json

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.market.chart_services import CHART_SYMBOLS, MarketChartService


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
                for source, provider in MarketChartService._providers(market, symbol):
                    try:
                        points = provider(symbol, options["range_value"], "1h")
                        normalized = MarketChartService._normalize(market, symbol, points, source)
                    except Exception:
                        continue  # Provider exceptions can contain credential-bearing URLs.
                    result.update({
                        "ok": True, "source": source, "points": len(normalized["points"]),
                        "checked_at": timezone.now().isoformat(),
                    })
                    break
                results.append(result)
        self.stdout.write(json.dumps({"results": results, "passed": sum(row["ok"] for row in results),
                                      "total": len(results)}, ensure_ascii=False))
        if any(not row["ok"] for row in results):
            raise CommandError("At least one symbol has no usable live provider history.")
