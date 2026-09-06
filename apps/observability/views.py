from datetime import timedelta

from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from common.permissions import IsSuperAdmin
from common.pagination import DefaultPagination
from apps.activity.services import ActivityService

from .models import LogEvent
from .serializers import (
    FrontendLogSerializer, LogEventSerializer, LogSummarySerializer,
    ResolveLogSerializer,
)
from .services import ObservabilityService
from .throttles import FrontendLogThrottle


class FrontendLogIngestView(generics.GenericAPIView):
    permission_classes = [AllowAny]
    throttle_classes = [FrontendLogThrottle]
    serializer_class = FrontendLogSerializer

    def post(self, request):
        origin = request.headers.get("Origin", "")
        allowed = {"https://app.sokanex.com", "http://localhost:5173", "http://127.0.0.1:5173"}
        if origin and origin not in allowed:
            return Response({"detail": "Origin is not allowed."}, status=status.HTTP_403_FORBIDDEN)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        user = request.user if request.user.is_authenticated else None
        event = ObservabilityService.record(
            source=LogEvent.Source.FRONTEND,
            user=user,
            ip_address=ActivityService.client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", "")[:500],
            **data,
        )
        if event is None and data.get("client_event_id"):
            event = LogEvent.objects.filter(
                source=LogEvent.Source.FRONTEND,
                client_event_id=data["client_event_id"],
            ).first()
        return Response({"accepted": True, "id": getattr(event, "pk", None)}, status=status.HTTP_202_ACCEPTED)


class LogEventListView(generics.ListAPIView):
    permission_classes = [IsSuperAdmin]
    serializer_class = LogEventSerializer
    pagination_class = DefaultPagination

    def get_queryset(self):
        queryset = LogEvent.objects.select_related("user", "resolved_by")
        params = self.request.query_params
        for field in ("source", "level", "category", "request_id"):
            value = params.get(field)
            if value not in (None, ""):
                queryset = queryset.filter(**{field: value})
        status_value = params.get("status_code")
        if status_value:
            try:
                queryset = queryset.filter(status_code=int(status_value))
            except (TypeError, ValueError):
                raise ValidationError({"status_code": "Must be an integer."})
        resolved_value = params.get("is_resolved")
        if resolved_value not in (None, ""):
            normalized = resolved_value.lower()
            if normalized not in {"true", "false"}:
                raise ValidationError({"is_resolved": "Must be true or false."})
            queryset = queryset.filter(is_resolved=normalized == "true")
        search = params.get("search", "").strip()
        if search:
            queryset = queryset.filter(
                Q(message__icontains=search) | Q(path__icontains=search)
                | Q(error_type__icontains=search) | Q(user__username__icontains=search)
                | Q(request_id__icontains=search)
            )
        return queryset


class LogEventDetailView(generics.RetrieveAPIView):
    permission_classes = [IsSuperAdmin]
    serializer_class = LogEventSerializer
    queryset = LogEvent.objects.select_related("user", "resolved_by")


class LogEventResolveView(generics.GenericAPIView):
    permission_classes = [IsSuperAdmin]
    serializer_class = ResolveLogSerializer

    def patch(self, request, pk):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        event = get_object_or_404(LogEvent, pk=pk)
        event.is_resolved = serializer.validated_data["is_resolved"]
        event.resolved_by = request.user if event.is_resolved else None
        event.resolved_at = timezone.now() if event.is_resolved else None
        event.save(update_fields=("is_resolved", "resolved_by", "resolved_at"))
        return Response(LogEventSerializer(event).data)


class LogSummaryView(generics.GenericAPIView):
    permission_classes = [IsSuperAdmin]
    serializer_class = LogSummarySerializer

    def get(self, request):
        since = timezone.now() - timedelta(hours=24)
        recent = LogEvent.objects.filter(created_at__gte=since)
        return Response({
            "last_24_hours": recent.count(),
            "unresolved": LogEvent.objects.filter(is_resolved=False).count(),
            "by_level": {row["level"]: row["count"] for row in recent.values("level").annotate(count=Count("id"))},
            "by_source": {row["source"]: row["count"] for row in recent.values("source").annotate(count=Count("id"))},
        })
