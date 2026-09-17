import json
import math
import time
from datetime import timedelta, timezone as datetime_timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .models import MarketChartSnapshot


CHART_SYMBOLS = {
    "crypto": {
        "BINANCE:BTCUSDT": {"coingecko": "bitcoin", "coinbase": "BTC-USD"},
        "BINANCE:ETHUSDT": {"coingecko": "ethereum", "coinbase": "ETH-USD"},
        "BINANCE:SOLUSDT": {"coingecko": "solana", "coinbase": "SOL-USD"},
        "BINANCE:XRPUSDT": {"coingecko": "ripple", "coinbase": "XRP-USD"},
        "BINANCE:BNBUSDT": {"coingecko": "binancecoin", "coinbase": "BNB-USD"},
        "BINANCE:DOGEUSDT": {"coingecko": "dogecoin", "coinbase": "DOGE-USD"},
    },
    "forex": {
        "OANDA:XAUUSD": {"base": "XAU", "quote": "USD", "gold": True},
        "FX:EURUSD": {"base": "EUR", "quote": "USD"},
        "FX:GBPUSD": {"base": "GBP", "quote": "USD"},
        "FX:USDJPY": {"base": "USD", "quote": "JPY"},
        "FX:USDCHF": {"base": "USD", "quote": "CHF"},
        "FX:AUDUSD": {"base": "AUD", "quote": "USD"},
    },
}

FOREX_SYMBOL_ALIASES = {
    "EURUSD": "FX:EURUSD",
    "GBPUSD": "FX:GBPUSD",
    "USDJPY": "FX:USDJPY",
    "USDCHF": "FX:USDCHF",
    "AUDUSD": "FX:AUDUSD",
    "XAUUSD": "OANDA:XAUUSD",
}
RANGE_DAYS = {"1d": 1, "5d": 5, "7d": 7, "30d": 30}
COINBASE_GRANULARITY = {"1d": 3600, "5d": 3600, "7d": 21600, "30d": 86400}


class MarketChartUnavailable(Exception):
    code = "historical_series_unavailable"


def _request_json(url, headers=None):
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": settings.MARKET_HTTP_USER_AGENT,
            **(headers or {}),
        },
    )
    timeout = max(1, min(settings.MARKET_CHART_TIMEOUT_SECONDS, 7))
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _iso_timestamp(value):
    numeric = float(value)
    if numeric > 10_000_000_000:
        numeric /= 1000
    return timezone.datetime.fromtimestamp(
        numeric, tz=datetime_timezone.utc
    ).isoformat().replace("+00:00", "Z")


class MarketChartService:
    @classmethod
    def get_chart(cls, market, symbol, range_value, interval=None):
        market = (market or "").lower()
        symbol = cls._normalize_symbol(market, symbol)
        range_value = (range_value or "").lower()
        if market not in CHART_SYMBOLS:
            raise ValidationError({"market": "Use crypto or forex."})
        if symbol not in CHART_SYMBOLS[market]:
            raise ValidationError({"symbol": "This symbol is not allowed for the selected market."})
        if range_value not in RANGE_DAYS:
            raise ValidationError({"range": "Use 1d, 7d, or 30d."})
        if interval and interval not in settings.MARKET_CHART_ALLOWED_INTERVALS:
            raise ValidationError({"interval": "Unsupported chart interval."})

        suffix = f"{market}:{symbol}:{range_value}:{interval or 'auto'}"
        fresh_key = f"market:chart:v1:fresh:{suffix}"
        stale_key = f"market:chart:v1:last-known:{suffix}"
        fresh = cache.get(fresh_key)
        if fresh and cls._is_usable_payload(market, fresh):
            return cls._with_stale_state(fresh, False)

        interval_key = interval or ""
        persisted = MarketChartSnapshot.objects.filter(
            market=market,
            symbol=symbol,
            range_value=range_value,
            interval=interval_key,
        ).first()
        ttl = (
            settings.MARKET_CHART_CRYPTO_TTL
            if market == "crypto"
            else settings.MARKET_CHART_FOREX_TTL
        )
        if (
            persisted
            and cls._is_usable_payload(market, persisted.payload)
            and persisted.updated_at >= timezone.now() - timedelta(seconds=ttl)
        ):
            cache.set(fresh_key, persisted.payload, ttl)
            return cls._with_stale_state(persisted.payload, False)

        providers = cls._providers(market, symbol)
        for source, provider in providers:
            try:
                points = provider(symbol, range_value, interval)
                normalized = cls._normalize(market, symbol, points, source)
                cache.set(fresh_key, normalized, ttl)
                cache.set(stale_key, normalized, settings.MARKET_CHART_STALE_TTL)
                MarketChartSnapshot.objects.update_or_create(
                    market=market,
                    symbol=symbol,
                    range_value=range_value,
                    interval=interval_key,
                    defaults={"payload": normalized},
                )
                return cls._with_stale_state(normalized, False)
            except (HTTPError, URLError, TimeoutError, OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
                continue

        stale = cache.get(stale_key)
        if stale and cls._is_usable_payload(market, stale):
            return cls._with_stale_state(stale, True)
        if (
            persisted
            and cls._is_usable_payload(market, persisted.payload)
            and persisted.updated_at >= timezone.now() - timedelta(seconds=settings.MARKET_CHART_STALE_TTL)
        ):
            cache.set(stale_key, persisted.payload, settings.MARKET_CHART_STALE_TTL)
            return cls._with_stale_state(persisted.payload, True)
        raise MarketChartUnavailable()

    @staticmethod
    def _normalize_symbol(market, symbol):
        normalized = (symbol or "").strip().upper()
        if market != "forex":
            return normalized
        bare = normalized.split(":", 1)[-1]
        return FOREX_SYMBOL_ALIASES.get(bare, normalized)

    @staticmethod
    def _with_stale_state(payload, stale):
        return {**payload, "stale": stale, "is_stale": stale}

    @staticmethod
    def _is_usable_payload(market, payload):
        points = payload.get("points") if isinstance(payload, dict) else None
        if not isinstance(points, list):
            return False
        if market == "forex":
            return len(points) >= 24 and all(
                isinstance(value, (int, float)) and math.isfinite(float(value))
                for value in points
            )
        return len(points) >= 2

    @classmethod
    def _providers(cls, market, symbol):
        if market == "crypto":
            return (("coingecko", cls._coingecko), ("coinbase", cls._coinbase))
        fallbacks = (
            (("gold-provider", cls._configured_gold),)
            if CHART_SYMBOLS[market][symbol].get("gold")
            else (("forex-provider", cls._configured_forex),)
        )
        return (("TWELVE_DATA", cls._twelve_data),) + fallbacks

    @staticmethod
    def _normalize(market, symbol, points, source):
        cleaned = []
        seen = set()
        for point in sorted(points, key=lambda item: str(item["timestamp"])):
            try:
                value = float(point["value"])
                timestamp = str(point["timestamp"])
            except (KeyError, TypeError, ValueError):
                continue
            if not timestamp or not math.isfinite(value) or timestamp in seen:
                continue
            seen.add(timestamp)
            cleaned.append({"timestamp": timestamp, "value": value})
        minimum = 24 if market == "forex" else 2
        if len(cleaned) < minimum:
            raise ValueError("Provider returned no chart points.")
        first, last = cleaned[0]["value"], cleaned[-1]["value"]
        change = ((last - first) / first * 100) if first else 0
        return {
            "market": market,
            "symbol": symbol.split(":", 1)[-1] if market == "forex" else symbol,
            "price": last,
            "change_percent": round(change, 4),
            "points": [point["value"] for point in cleaned] if market == "forex" else cleaned,
            "source": source,
            "updated_at": timezone.now().isoformat(),
        }

    @staticmethod
    def _twelve_data(symbol, range_value, interval):
        if not settings.TWELVE_DATA_API_KEY:
            raise ValueError("Twelve Data is not configured.")
        metadata = CHART_SYMBOLS["forex"][symbol]
        provider_symbol = f"{metadata['base']}/{metadata['quote']}"
        interval_value = interval or "1h"
        output_size = min(120, max(24, RANGE_DAYS[range_value] * 24))
        params = {
            "symbol": provider_symbol,
            "interval": interval_value,
            "outputsize": output_size,
            "order": "ASC",
            "apikey": settings.TWELVE_DATA_API_KEY,
        }
        url = f"{settings.TWELVE_DATA_BASE_URL.rstrip('/')}/time_series?{urlencode(params)}"
        last_error = None
        for attempt in range(2):
            try:
                payload = _request_json(url)
                if payload.get("status") == "error":
                    raise ValueError("Twelve Data returned an error.")
                return [
                    {"timestamp": row["datetime"], "value": row["close"]}
                    for row in payload.get("values", [])
                ]
            except (HTTPError, URLError, TimeoutError, OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
                last_error = exc
                if attempt == 0:
                    time.sleep(0.25)
        raise ValueError("Twelve Data historical series is unavailable.") from last_error

    @staticmethod
    def _coingecko(symbol, range_value, interval):
        coin_id = CHART_SYMBOLS["crypto"][symbol]["coingecko"]
        params = {"vs_currency": "usd", "days": RANGE_DAYS[range_value]}
        payload = _request_json(
            f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart?{urlencode(params)}"
        )
        return [
            {"timestamp": _iso_timestamp(timestamp), "value": value}
            for timestamp, value in payload["prices"]
        ]

    @staticmethod
    def _coinbase(symbol, range_value, interval):
        product = CHART_SYMBOLS["crypto"][symbol]["coinbase"]
        end = timezone.now()
        start = end - timedelta(days=RANGE_DAYS[range_value])
        params = {
            "start": start.isoformat(), "end": end.isoformat(),
            "granularity": COINBASE_GRANULARITY[range_value],
        }
        payload = _request_json(
            f"https://api.exchange.coinbase.com/products/{product}/candles?{urlencode(params)}"
        )
        return [
            {"timestamp": _iso_timestamp(candle[0]), "value": candle[4]}
            for candle in payload
        ]

    @staticmethod
    def _frankfurter(symbol, range_value, interval):
        metadata = CHART_SYMBOLS["forex"][symbol]
        end = timezone.localdate()
        start = end - timedelta(days=RANGE_DAYS[range_value])
        params = {"from": metadata["base"], "to": metadata["quote"]}
        payload = _request_json(
            f"https://api.frankfurter.app/{start.isoformat()}..{end.isoformat()}?{urlencode(params)}"
        )
        return [
            {"timestamp": f"{date_value}T00:00:00Z", "value": rates[metadata["quote"]]}
            for date_value, rates in payload["rates"].items()
        ]

    @staticmethod
    def _configured_forex(symbol, range_value, interval):
        if not settings.FOREX_CHART_PROVIDER_URL:
            raise ValueError("Secondary forex provider is not configured.")
        metadata = CHART_SYMBOLS["forex"][symbol]
        params = {
            "base": metadata["base"], "quote": metadata["quote"],
            "range": range_value, "interval": interval or "auto",
        }
        headers = {"Authorization": f"Bearer {settings.FOREX_CHART_PROVIDER_KEY}"} if settings.FOREX_CHART_PROVIDER_KEY else {}
        payload = _request_json(f"{settings.FOREX_CHART_PROVIDER_URL}?{urlencode(params)}", headers)
        return payload["points"]

    @staticmethod
    def _configured_gold(symbol, range_value, interval):
        if not settings.GOLD_CHART_PROVIDER_URL:
            raise ValueError("Gold provider is not configured.")
        params = {"symbol": "XAUUSD", "range": range_value, "interval": interval or "auto"}
        headers = {"Authorization": f"Bearer {settings.GOLD_CHART_PROVIDER_KEY}"} if settings.GOLD_CHART_PROVIDER_KEY else {}
        payload = _request_json(f"{settings.GOLD_CHART_PROVIDER_URL}?{urlencode(params)}", headers)
        return payload["points"]
