"""The dashboard and ingest endpoint must agree on tracking readiness."""

from django.conf import settings
from django.core.cache import cache
from django.db import DatabaseError, connection

from .models import PageViewDailyAggregate, PageViewEvent, PageViewReceipt


SCHEMA_READY_CACHE_KEY = "activity:page-view-schema-ready:v1"


def page_view_tracking_enabled():
    if not settings.ANALYTICS_PAGE_VIEW_TRACKING_ENABLED:
        return False
    ready = cache.get(SCHEMA_READY_CACHE_KEY)
    if ready is not None:
        return ready
    try:
        tables = set(connection.introspection.table_names())
    except DatabaseError:
        return False
    ready = {
        PageViewEvent._meta.db_table,
        PageViewDailyAggregate._meta.db_table,
        PageViewReceipt._meta.db_table,
    }.issubset(tables)
    # A migration applied after the flag was enabled can become visible shortly
    # afterwards without requiring another process restart.
    cache.set(SCHEMA_READY_CACHE_KEY, ready, timeout=30)
    return ready
