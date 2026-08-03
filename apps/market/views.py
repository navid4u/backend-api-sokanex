from datetime import datetime, time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.utils import timezone
from rest_framework import generics, serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import EconomicEvent
from .serializers import EconomicEventSerializer
from .services import MarketQuoteService
from common.serializers import EmptySerializer


class QuoteView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = EmptySerializer

    def get(self, request):
        symbols = [item.strip().lower() for item in request.query_params.get("symbols", "").split(",") if item.strip()]
        if not symbols or len(symbols) > 20:
            raise serializers.ValidationError({"symbols": "Provide between 1 and 20 comma-separated symbols."})
        return Response(MarketQuoteService.get_quotes(symbols))


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
