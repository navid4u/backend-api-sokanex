from datetime import datetime, time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.utils import timezone
from rest_framework import generics, serializers
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer

from .models import EconomicEvent, NewsArticle
from .serializers import EconomicEventSerializer, NewsArticleSerializer
from .chart_services import MarketChartService, MarketChartUnavailable
from .services import BASE_SYMBOLS, CryptoSnapshotService, MarketNewsService, MarketQuoteService
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


class CryptoSnapshotView(APIView):
    permission_classes = [AllowAny]
    serializer_class = EmptySerializer
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "market_snapshot"

    @extend_schema(responses={200: inline_serializer(name="CryptoSnapshotResponse", fields={
        "market_cap": serializers.FloatField(), "market_cap_change_24h": serializers.FloatField(),
        "volume_24h": serializers.FloatField(), "volume_change_24h": serializers.FloatField(),
        "btc_dominance": serializers.FloatField(), "eth_dominance": serializers.FloatField(),
        "tether_price_irr": serializers.FloatField(), "fear_greed": serializers.DictField(),
        "updated_at": serializers.DateTimeField(), "source": serializers.CharField(), "stale": serializers.BooleanField(),
    })})
    def get(self, request):
        return Response(CryptoSnapshotService.get_snapshot())


class MarketChartView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = EmptySerializer
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "market_charts"

    @extend_schema(
        parameters=[
            OpenApiParameter("market", str, required=True, enum=["crypto", "forex"]),
            OpenApiParameter("symbol", str, required=True),
            OpenApiParameter("range", str, required=True, enum=["1d", "7d", "30d"]),
            OpenApiParameter("interval", str, required=False, enum=["5m", "15m", "1h", "4h", "1d"]),
        ],
        responses={
            200: inline_serializer(
                name="MarketChartSuccessResponse",
                fields={"success": serializers.BooleanField(), "data": serializers.DictField()},
            ),
            503: inline_serializer(
                name="MarketChartUnavailableResponse",
                fields={
                    "success": serializers.BooleanField(), "message": serializers.CharField(),
                    "errors": serializers.DictField(),
                },
            ),
        },
    )
    def get(self, request):
        try:
            data = MarketChartService.get_chart(
                request.query_params.get("market"),
                request.query_params.get("symbol"),
                request.query_params.get("range"),
                request.query_params.get("interval"),
            )
        except MarketChartUnavailable:
            return Response({
                "success": False,
                "message": "Market data is temporarily unavailable",
                "errors": {"source": ["No market provider is currently available."]},
            }, status=503)
        return Response({"success": True, "data": data})


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
