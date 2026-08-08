from datetime import datetime, time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.utils import timezone
from rest_framework import generics, serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .models import EconomicEvent, NewsArticle
from .serializers import EconomicEventSerializer, NewsArticleSerializer
from .services import BASE_SYMBOLS, MarketNewsService, MarketQuoteService
from common.serializers import EmptySerializer


class QuoteView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = EmptySerializer
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "market_quotes"

    def get(self, request):
        symbols = [item.strip().lower() for item in request.query_params.get("symbols", "").split(",") if item.strip()]
        if not symbols:
            symbols = list(BASE_SYMBOLS)
        if len(symbols) > 20:
            raise serializers.ValidationError({"symbols": "Provide at most 20 comma-separated symbols."})
        return Response(MarketQuoteService.get_quotes(symbols))


class MarketNewsView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = NewsArticleSerializer
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "market_news"

    def get(self, request):
        language = request.query_params.get("language")
        if language not in (None, "", "fa", "en"):
            raise serializers.ValidationError({"language": "Use fa or en."})
        try:
            limit = int(request.query_params.get("limit", 20))
        except ValueError as exc:
            raise serializers.ValidationError({"limit": "Use an integer between 1 and 100."}) from exc
        if not 1 <= limit <= 100:
            raise serializers.ValidationError({"limit": "Use an integer between 1 and 100."})
        MarketNewsService.refresh_due_sources(language or None)
        queryset = NewsArticle.objects.select_related("source").filter(
            source__is_active=True, source__syndication_allowed=True,
        )
        if language:
            queryset = queryset.filter(source__language=language)
        rows = list(queryset[:limit])
        updated_at = max((row.fetched_at for row in rows), default=timezone.now())
        return Response({"updated_at": updated_at, "results": NewsArticleSerializer(rows, many=True).data})


class EconomicCalendarView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = EconomicEventSerializer

    def get_queryset(self):
        queryset = EconomicEvent.objects.all()
        tz_name = self.request.query_params.get("timezone", "Asia/Tehran")
        try:
            selected_tz = ZoneInfo(tz_name)
        except ZoneInfoNotFoundError as exc:
            raise serializers.ValidationError({"timezone": "Unknown IANA timezone."}) from exc
        date_value = self.request.query_params.get("date")
        if date_value:
            try:
                selected_date = datetime.strptime(date_value, "%Y-%m-%d").date()
            except ValueError as exc:
                raise serializers.ValidationError({"date": "Use YYYY-MM-DD."}) from exc
            start = timezone.make_aware(datetime.combine(selected_date, time.min), selected_tz)
            end = timezone.make_aware(datetime.combine(selected_date, time.max), selected_tz)
            queryset = queryset.filter(datetime__range=(start, end))
        if self.request.query_params.get("currency"):
            queryset = queryset.filter(currency__iexact=self.request.query_params["currency"])
        if self.request.query_params.get("impact"):
            queryset = queryset.filter(impact=self.request.query_params["impact"])
        return queryset
