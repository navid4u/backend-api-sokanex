import hashlib
import html
import ipaddress
import json
import re
import socket
import xml.etree.ElementTree as ET
from datetime import timedelta
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import APIException, ValidationError

from .models import CryptoMarketSnapshot, NewsArticle, NewsSource


BASE_SYMBOLS = ("usd-irr", "gold-18k", "half-coin", "coin-emami", "car-index", "tedpix")


class MarketProviderUnavailable(APIException):
    status_code = 503
    default_code = "PROVIDER_TIMEOUT"
    default_detail = "Licensed market data providers are temporarily unavailable."


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def plain_text(value, limit=700):
    parser = _TextExtractor()
    parser.feed(html.unescape(value or ""))
    return re.sub(r"\s+", " ", " ".join(parser.parts)).strip()[:limit]


def canonical_https_url(value):
    parsed = urlsplit((value or "").strip())
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        raise ValueError("Only absolute HTTPS URLs are accepted.")
    query = urlencode(sorted((key, val) for key, val in parse_qsl(parsed.query) if not key.lower().startswith("utm_")))
    return urlunsplit(("https", parsed.netloc.lower(), parsed.path or "/", query, ""))


def ensure_public_host(url):
    hostname = urlsplit(url).hostname
    for result in socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM):
        address = ipaddress.ip_address(result[4][0])
        if not address.is_global:
            raise ValueError("Feed host must resolve to a public address.")


def _request_json(url, headers=None):
    request = Request(url, headers={"Accept": "application/json", "User-Agent": settings.MARKET_HTTP_USER_AGENT, **(headers or {})})
    last_error = None
    for _ in range(settings.MARKET_DATA_RETRY_COUNT + 1):
        try:
            with urlopen(request, timeout=settings.MARKET_DATA_TIMEOUT_SECONDS) as response:
                return json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, ValueError) as exc:
            last_error = exc
    raise last_error


def _number(value):
    if value is None:
        return None
    normalized = str(value).translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))
    normalized = normalized.replace(",", "").replace("٬", "").strip()
    try:
        return float(normalized)
    except ValueError:
        return None


def _walk(node):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _walk(value)
    elif isinstance(node, list):
        for value in node:
            yield from _walk(value)


def _extract_rows(payload, aliases, source, rial_prices=False):
    found = {}
    reverse = {alias.lower(): symbol for symbol, values in aliases.items() for alias in values}
    now = timezone.now().isoformat()
    for row in _walk(payload):
        keys = {str(key).lower(): value for key, value in row.items()}
        identity = str(keys.get("symbol") or keys.get("name") or keys.get("key") or keys.get("title") or "").lower()
        symbol = reverse.get(identity)
        if not symbol:
            for key in keys:
                if key in reverse and not isinstance(keys[key], (dict, list)):
                    symbol = reverse[key]
                    row = {"price": keys[key]}
                    keys = {"price": keys[key]}
                    break
        if not symbol or symbol in found:
            continue
        price = _number(keys.get("price") or keys.get("value") or keys.get("current") or keys.get("p"))
        if price is None:
            continue
        if rial_prices:
            price /= 10
        change = _number(keys.get("change") or keys.get("d") or 0) or 0
        if rial_prices:
            change /= 10
        found[symbol] = {
            "symbol": symbol,
            "name": keys.get("name_fa") or keys.get("title") or symbol,
            "price": price,
            "unit": "تومان" if symbol in {"usd-irr", "gold-18k", "half-coin", "coin-emami"} else keys.get("unit", ""),
            "change": change,
            "change_percent": _number(keys.get("change_percent") or keys.get("percent") or keys.get("dp") or 0) or 0,
            "market_status": keys.get("market_status", "delayed"),
            "source_timestamp": keys.get("source_timestamp") or keys.get("time") or now,
            "source": source,
        }
    return found


class MarketQuoteService:
    fresh_cache_key = "market:v3:quotes:fresh"
    stale_cache_key = "market:v3:quotes:last-known"
    aliases = {
        "usd-irr": {"usd-irr", "price_dollar_rl", "usd", "دلار"},
        "gold-18k": {"gold-18k", "geram18", "geram_18", "طلای 18 عیار"},
        "coin-emami": {"coin-emami", "sekee", "sekke_emami", "سکه امامی"},
        "half-coin": {"half-coin", "nim", "نیم سکه"},
        "car-index": {"car-index", "car_index"},
        "tedpix": {"tedpix", "شاخص کل"},
    }

    @classmethod
    def get_quotes(cls, symbols):
        fresh = cache.get(cls.fresh_cache_key)
        if fresh and all(symbol in fresh["quotes"] for symbol in symbols):
            return cls._response(fresh, symbols, False)

        quotes = {}
        provider_errors = []
        providers = (
            ("generic", cls._generic_provider), ("brsapi", cls._brsapi_provider),
            ("tgju", cls._tgju_provider),
        )
        for provider_name, provider in providers:
            try:
                rows = cls._with_circuit_breaker(provider_name, provider)
                quotes.update({key: value for key, value in rows.items() if key not in quotes})
            except (HTTPError, URLError, TimeoutError, ValueError, KeyError, OSError) as exc:
                provider_errors.append(type(exc).__name__)
            if all(symbol in quotes for symbol in symbols):
                break
        if quotes:
            snapshot = {"updated_at": timezone.now().isoformat(), "quotes": quotes}
            cache.set(cls.fresh_cache_key, snapshot, settings.MARKET_DATA_CACHE_SECONDS)
            cache.set(cls.stale_cache_key, snapshot, settings.MARKET_DATA_STALE_SECONDS)
            return cls._response(snapshot, symbols, False)

        stale = cache.get(cls.stale_cache_key)
        if stale:
            return cls._response(stale, symbols, True)
        raise MarketProviderUnavailable()

    @classmethod
    def _with_circuit_breaker(cls, name, provider):
        state_key = f"market:v3:circuit:{name}"
        state = cache.get(state_key) or {"failures": 0, "opened_until": 0}
        now = int(timezone.now().timestamp())
        if state["opened_until"] > now:
            return {}
        try:
            rows = provider()
        except (HTTPError, URLError, TimeoutError, ValueError, KeyError, OSError):
            failures = state["failures"] + 1
            opened_until = now + settings.MARKET_CIRCUIT_BREAKER_SECONDS if failures >= settings.MARKET_CIRCUIT_BREAKER_FAILURES else 0
            cache.set(state_key, {"failures": failures, "opened_until": opened_until}, settings.MARKET_CIRCUIT_BREAKER_SECONDS)
            raise
        if rows:
            cache.delete(state_key)
        return rows

    @classmethod
    def _generic_provider(cls):
        if not settings.MARKET_DATA_PROVIDER_URL or not settings.MARKET_DATA_API_KEY:
            return {}
        url = f"{settings.MARKET_DATA_PROVIDER_URL}?{urlencode({'symbols': ','.join(BASE_SYMBOLS)})}"
        payload = _request_json(url, {"Authorization": f"Bearer {settings.MARKET_DATA_API_KEY}"})
        rows = payload if isinstance(payload, list) else payload.get("results", [])
        return {str(row["symbol"]).lower(): {**row, "source": settings.MARKET_DATA_PROVIDER or "licensed-provider"} for row in rows}

    @classmethod
    def _brsapi_provider(cls):
        if not settings.BRSAPI_API_KEY:
            return {}
        result = {}
        for path in ("Gold_Currency.php", "Cryptocurrency.php", "Commodity.php"):
            url = f"https://brsapi.ir/Api/Market/{path}?{urlencode({'key': settings.BRSAPI_API_KEY})}"
            result.update(_extract_rows(_request_json(url), cls.aliases, "BRSAPI", settings.BRSAPI_PRICES_IN_RIAL))
        return result

    @classmethod
    def _tgju_provider(cls):
        if not settings.TGJU_ENABLED:
            return {}
        payload = _request_json(settings.TGJU_API_URL)
        return _extract_rows(payload, cls.aliases, "TGJU", rial_prices=True)

    @staticmethod
    def _response(snapshot, symbols, is_stale):
        updated = timezone.datetime.fromisoformat(snapshot["updated_at"])
        age = max(0, int((timezone.now() - updated).total_seconds()))
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
                "source": row.get("source", "licensed-provider"),
                "source_timestamp": row.get("source_timestamp"), "is_stale": is_stale,
                "stale_age_seconds": age if is_stale else 0,
            })
        return {"updated_at": snapshot["updated_at"], "is_stale": is_stale, "stale_age_seconds": age if is_stale else 0, "results": results}


class CryptoSnapshotService:
    cache_key = "market:v3:crypto-snapshot"
    circuit_key = "market:v3:crypto-snapshot:circuit"

    @classmethod
    def get_snapshot(cls):
        cached = cache.get(cls.cache_key)
        if cached:
            return {**cached, "stale": False}
        state = cache.get(cls.circuit_key) or {"failures": 0, "opened_until": 0}
        if state["opened_until"] <= int(timezone.now().timestamp()):
            try:
                snapshot = cls._fetch()
                row = CryptoMarketSnapshot.objects.create(**snapshot)
                payload = cls._serialize(row, False)
                cache.set(cls.cache_key, payload, settings.MARKET_SNAPSHOT_CACHE_SECONDS)
                cache.delete(cls.circuit_key)
                return payload
            except (HTTPError, URLError, TimeoutError, ValueError, KeyError, OSError, TypeError):
                failures = state["failures"] + 1
                opened = int(timezone.now().timestamp()) + settings.MARKET_CIRCUIT_BREAKER_SECONDS if failures >= settings.MARKET_CIRCUIT_BREAKER_FAILURES else 0
                cache.set(cls.circuit_key, {"failures": failures, "opened_until": opened}, settings.MARKET_CIRCUIT_BREAKER_SECONDS)
        last = CryptoMarketSnapshot.objects.first()
        if last and last.captured_at >= timezone.now() - timedelta(seconds=settings.MARKET_SNAPSHOT_STALE_SECONDS):
            return cls._serialize(last, True)
        raise MarketProviderUnavailable("No crypto market snapshot is available.")

    @classmethod
    def _fetch(cls):
        global_data = _request_json(settings.COINGECKO_GLOBAL_URL)["data"]
        fear = _request_json(settings.FEAR_GREED_URL)["data"][0]
        tether = settings.TETHER_PRICE_IRR
        if settings.TETHER_PRICE_URL:
            tether = _number(_request_json(settings.TETHER_PRICE_URL)["tether"]["irr"])
        if not tether:
            raise ValueError("Tether IRR price is unavailable.")
        market_cap = float(global_data["total_market_cap"]["usd"])
        volume = float(global_data["total_volume"]["usd"])
        market_change = float(global_data["market_cap_change_percentage_24h_usd"])
        # CoinGecko does not expose a separate total-volume change in /global.
        volume_change = global_data.get("volume_change_percentage_24h_usd")
        if volume_change is None:
            prior = CryptoMarketSnapshot.objects.filter(
                captured_at__lte=timezone.now() - timedelta(hours=23, minutes=30)
            ).first()
            volume_change = ((volume - float(prior.volume_24h)) / float(prior.volume_24h) * 100) if prior and prior.volume_24h else 0
        return {
            "market_cap": market_cap, "market_cap_change_24h": market_change,
            "volume_24h": volume, "volume_change_24h": volume_change,
            "btc_dominance": float(global_data["market_cap_percentage"]["btc"]),
            "eth_dominance": float(global_data["market_cap_percentage"]["eth"]),
            "tether_price_irr": tether, "fear_greed_value": int(fear["value"]),
            "source": "aggregated",
        }

    @staticmethod
    def _label(value):
        if value <= 24: return "ترس شدید"
        if value <= 44: return "ترس"
        if value <= 54: return "خنثی"
        if value <= 74: return "طمع"
        return "طمع شدید"

    @classmethod
    def _serialize(cls, row, stale):
        return {
            "market_cap": float(row.market_cap), "market_cap_change_24h": row.market_cap_change_24h,
            "volume_24h": float(row.volume_24h), "volume_change_24h": row.volume_change_24h,
            "btc_dominance": row.btc_dominance, "eth_dominance": row.eth_dominance,
            "tether_price_irr": float(row.tether_price_irr),
            "fear_greed": {"value": row.fear_greed_value, "label": cls._label(row.fear_greed_value)},
            "updated_at": row.captured_at.isoformat(), "source": row.source, "stale": stale,
        }


class MarketNewsService:
    @classmethod
    def refresh_due_sources(cls, language=None):
        sources = NewsSource.objects.filter(is_active=True, syndication_allowed=True)
        if language:
            sources = sources.filter(language=language)
        now = timezone.now()
        for source in sources:
            if source.last_fetched_at and source.last_fetched_at + timedelta(minutes=source.fetch_interval_minutes) > now:
                continue
            cls._refresh_source(source)

    @classmethod
    def _refresh_source(cls, source):
        now = timezone.now()
        try:
            feed_url = canonical_https_url(source.feed_url)
            ensure_public_host(feed_url)
            request = Request(feed_url, headers={"User-Agent": settings.MARKET_HTTP_USER_AGENT, "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml"})
            with urlopen(request, timeout=settings.MARKET_NEWS_TIMEOUT_SECONDS) as response:
                final_url = canonical_https_url(response.geturl())
                ensure_public_host(final_url)
                document = response.read(settings.MARKET_NEWS_MAX_BYTES + 1)
            if len(document) > settings.MARKET_NEWS_MAX_BYTES:
                raise ValueError("Feed exceeds maximum response size.")
            root = ET.fromstring(document)
            entries = root.findall(".//item") or root.findall(".//{http://www.w3.org/2005/Atom}entry")
            with transaction.atomic():
                for entry in entries[: settings.MARKET_NEWS_ITEMS_PER_SOURCE]:
                    cls._save_entry(source, entry, final_url, now)
                NewsSource.objects.filter(pk=source.pk).update(last_fetched_at=now, last_error="")
        except (ET.ParseError, HTTPError, URLError, TimeoutError, ValueError, OSError) as exc:
            NewsSource.objects.filter(pk=source.pk).update(last_fetched_at=now, last_error=str(exc)[:500])

    @staticmethod
    def _value(entry, *names):
        for name in names:
            node = entry.find(name)
            if node is not None:
                if node.text:
                    return node.text.strip()
                if node.attrib.get("href"):
                    return node.attrib["href"].strip()
        return ""

    @classmethod
    def _save_entry(cls, source, entry, feed_url, fetched_at):
        atom = "{http://www.w3.org/2005/Atom}"
        title = plain_text(cls._value(entry, "title", f"{atom}title"), 500)
        link = cls._value(entry, "link", f"{atom}link")
        url = canonical_https_url(urljoin(feed_url, link))
        guid = cls._value(entry, "guid", "id", f"{atom}id")
        summary = plain_text(cls._value(entry, "description", "summary", f"{atom}summary", f"{atom}content"))
        published_raw = cls._value(entry, "pubDate", "published", "updated", f"{atom}published", f"{atom}updated")
        try:
            published = parsedate_to_datetime(published_raw)
            if timezone.is_naive(published):
                published = timezone.make_aware(published)
        except (TypeError, ValueError, OverflowError):
            try:
                published = timezone.datetime.fromisoformat(published_raw.replace("Z", "+00:00"))
            except ValueError:
                published = fetched_at
        stable_id = hashlib.sha256((guid or url).encode("utf-8")).hexdigest()
        NewsArticle.objects.update_or_create(
            stable_id=stable_id,
            defaults={"source": source, "guid": guid[:500], "title": title, "summary": summary, "url": url, "canonical_url": url, "published_at": published},
        )
