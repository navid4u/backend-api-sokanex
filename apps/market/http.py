"""Small, bounded JSON downloads for market-data providers."""

import json


MAX_MARKET_JSON_BYTES = 2 * 1024 * 1024


class MarketResponseTooLarge(ValueError):
    pass


def read_market_json(response):
    """Never read an unbounded provider response into a Gunicorn worker."""
    headers = getattr(response, "headers", None)
    declared_length = headers.get("Content-Length") if headers is not None else None
    try:
        declared_size = int(declared_length) if declared_length is not None else None
    except (TypeError, ValueError):
        # A malformed header is not trusted; the bounded read remains authoritative.
        declared_size = None
    if declared_size is not None and declared_size > MAX_MARKET_JSON_BYTES:
        raise MarketResponseTooLarge("Market provider response exceeds size limit.")
    body = response.read(MAX_MARKET_JSON_BYTES + 1)
    if len(body) > MAX_MARKET_JSON_BYTES:
        raise MarketResponseTooLarge("Market provider response exceeds size limit.")
    return json.loads(body.decode("utf-8"))
