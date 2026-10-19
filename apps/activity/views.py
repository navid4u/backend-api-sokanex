from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.exceptions import Throttled, ValidationError
from rest_framework import status
from rest_framework.throttling import SimpleRateThrottle
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import serializers
from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from datetime import timedelta

from apps.accounts.models import User
from common.permissions import IsSuperAdmin

from .analytics import PERIODS, TEHRAN, overview
from .models import PageViewDailyAggregate, PageViewEvent, PageViewReceipt, UserActivity
from .serializers import PageViewIngestSerializer, UserActivitySerializer


class RecentActivityListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = UserActivitySerializer
    pagination_class = None

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return UserActivity.objects.none()
        return UserActivity.objects.filter(user=self.request.user)[:25]


class AdminAnalyticsOverviewView(APIView):
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    @extend_schema(
        parameters=[OpenApiParameter("period", str, enum=list(PERIODS), required=False)],
        responses={200: inline_serializer(name="AdminAnalyticsOverviewResponse", fields={
            "period": serializers.CharField(), "timezone": serializers.CharField(),
            "generated_at": serializers.DateTimeField(), "total_users": serializers.IntegerField(),
            "registrations": serializers.ListField(child=serializers.DictField()),
            "distributions": serializers.DictField(), "page_views": serializers.DictField(),
            "user_events": serializers.ListField(child=serializers.DictField()),
            "metadata": serializers.DictField(),
        })},
    )
    def get(self, request):
        period = request.query_params.get("period", "6m")
        if period not in PERIODS:
            raise ValidationError({"period": "Use 1m, 3m, 6m, 12m, 7d or 30d."})
        response = Response(overview(period))
        response["Cache-Control"] = "private, no-store"
        return response


class PageViewRequestThrottle(SimpleRateThrottle):
    """Bound duplicate/replay traffic as well as newly accepted events."""

    scope = "page_view_requests"
    rate = "60/min"

    def get_cache_key(self, request, view):
        if not settings.ANALYTICS_PAGE_VIEW_TRACKING_ENABLED:
            return None
        return self.cache_format % {"scope": self.scope, "ident": request.user.pk}


class PageViewIngestView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [PageViewRequestThrottle]

    @extend_schema(
        request=PageViewIngestSerializer,
        responses={200: inline_serializer(name="PageViewAcceptedResponse", fields={"accepted": serializers.BooleanField()}),
                   201: inline_serializer(name="PageViewCreatedResponse", fields={"accepted": serializers.BooleanField()}),
                   202: inline_serializer(name="PageViewDisabledResponse", fields={"enabled": serializers.BooleanField()})},
    )
    def post(self, request):
        if not settings.ANALYTICS_PAGE_VIEW_TRACKING_ENABLED:
            return Response({"enabled": False}, status=status.HTTP_202_ACCEPTED)
        incoming = PageViewIngestSerializer(data=request.data)
        incoming.is_valid(raise_exception=True)
        data = incoming.validated_data
        with transaction.atomic():
            # Serializing on the authenticated user makes the 60/min limit exact
            # across workers, independent of the process-local DRF cache.
            User.objects.select_for_update().only("pk").get(pk=request.user.pk)
            receipt = PageViewReceipt.objects.filter(event_id=data["event_id"]).first()
            if receipt:
                existing = PageViewEvent.objects.filter(event_id=data["event_id"]).first()
                if receipt.user_id != request.user.pk or (existing and (existing.session_id, existing.path) != (
                    data["session_id"], data["path"]
                )):
                    raise ValidationError({"event_id": "This event_id has already been used."})
                return Response({"accepted": True}, status=status.HTTP_200_OK)
            now = timezone.now()
            if PageViewEvent.objects.filter(user_id=request.user.pk, created_at__gte=now - timedelta(minutes=1)).count() >= 60:
                raise Throttled(wait=60)
            receipt, receipt_created = PageViewReceipt.objects.get_or_create(
                event_id=data["event_id"], defaults={"user_id": request.user.pk},
            )
            if not receipt_created:
                if receipt.user_id != request.user.pk:
                    raise ValidationError({"event_id": "This event_id has already been used."})
                return Response({"accepted": True}, status=status.HTTP_200_OK)
            event = PageViewEvent.objects.create(
                event_id=data["event_id"], session_id=data["session_id"],
                user_id=request.user.pk, path=data["path"],
            )
            day = timezone.localtime(event.created_at, TEHRAN).date()
            daily, _ = PageViewDailyAggregate.objects.get_or_create(
                user_id=request.user.pk, path=event.path, day=day,
            )
            PageViewDailyAggregate.objects.filter(pk=daily.pk).update(views=F("views") + 1)
            event.aggregated_at = now
            event.save(update_fields=("aggregated_at",))
        return Response({"accepted": True}, status=status.HTTP_201_CREATED)

