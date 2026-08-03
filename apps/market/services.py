import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from rest_framework.exceptions import APIException


class MarketProviderUnavailable(APIException):
    status_code = 503
    default_code = "PROVIDER_TIMEOUT"
    default_detail = "Licensed market data provider is temporarily unavailable."


class MarketQuoteService:
    cache_key = "market:v2:quotes"

    @classmethod
    def get_quotes(cls, symbols):
        cached = cache.get(cls.cache_key)
        if cached and all(symbol in cached["quotes"] for symbol in symbols):
            return cls._response(cached, symbols, is_stale=False)
        if not settings.MARKET_DATA_PROVIDER_URL or not settings.MARKET_DATA_API_KEY:
            if cached:
                return cls._response(cached, symbols, is_stale=True)
            raise MarketProviderUnavailable("Market data provider is not configured.")
        url = f"{settings.MARKET_DATA_PROVIDER_URL}?{urlencode({'symbols': ','.join(symbols)})}"
        request = Request(url, headers={"Authorization": f"Bearer {settings.MARKET_DATA_API_KEY}", "Accept": "application/json"})
        try:
            with urlopen(request, timeout=settings.MARKET_DATA_TIMEOUT_SECONDS) as response:
                payload = json.loads(response.read().decode("utf-8"))
            rows = payload.get("results", payload if isinstance(payload, list) else [])
            quotes = {str(row["symbol"]).lower(): row for row in rows}
            snapshot = {"updated_at": timezone.now().isoformat(), "quotes": quotes}
            cache.set(cls.cache_key, snapshot, settings.MARKET_DATA_CACHE_SECONDS)
            return cls._response(snapshot, symbols, is_stale=False)
        except (HTTPError, URLError, TimeoutError, ValueError, KeyError) as exc:
            if cached:
                return cls._response(cached, symbols, is_stale=True)
            raise MarketProviderUnavailable() from exc

    @staticmethod
    def _response(snapshot, symbols, is_stale):
        results = []
        for symbol in symbols:
            if symbol not in snapshot["quotes"]:
                continue
            row = snapshot["quotes"][symbol]
            results.append({
                "symbol": symbol, "name": row.get("name", symbol), "price": row.get("price"),
                "unit": row.get("unit", ""), "change": row.get("change", 0),
                "change_percent": row.get("change_percent", 0),
                "market_status": row.get("market_status", "delayed"),
                "source_timestamp": row.get("source_timestamp"),
            })
        return {"updated_at": snapshot["updated_at"], "is_stale": is_stale, "results": results}
