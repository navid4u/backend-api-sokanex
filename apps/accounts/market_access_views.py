"""New, gated administrator APIs for market membership management."""

from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view, inline_serializer
from rest_framework import generics, serializers, status
from rest_framework.filters import SearchFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.exceptions import ValidationError
from django.db.models import Count, Prefetch, Q
from django.conf import settings
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache

from common.permissions import CanManageMarketAccess, CanStartMarketTrialCampaign, MarketAccessV2Enabled

from .market_access import market_access_payload, with_market_access_relations
from .market_access_admin import update_user_market_access
from .content_section_access import content_policy_rows, update_content_section_policy
from .market_preferences import update_market_preferences
from .market_access_serializers import (
    ContentSectionPolicySerializer,
    ContentSectionPolicyUpdateSerializer,
    MarketAccessStateSerializer,
    MyMarketPreferencesUpdateSerializer,
    UserMarketAccessReadSerializer,
    UserMarketAccessUpdateSerializer,
    TrialCampaignPreviewInputSerializer,
    TrialCampaignPreviewResponseSerializer,
    TrialCampaignStartInputSerializer,
    TrialCampaignStartResponseSerializer,
    TrialAutoStartSettingsSerializer,
)
from .market_trial import (
    auto_start_settings_payload, eligible_trial_users, preview_trial_campaign,
    start_existing_user_trial, start_trial_campaign,
    update_auto_start_settings,
)
from .market_access_requests import submit_market_access_request, review_market_access_request
from .models import MarketAccessRequest, TrialGrant, User
from common.pagination import DefaultPagination


def _with_trial_admin_diagnostics(queryset):
    return with_market_access_relations(queryset).select_related(
        "trial_auto_start_decision",
    ).prefetch_related(Prefetch(
        "trial_grants_v2",
        queryset=TrialGrant.objects.order_by("-started_at", "-pk"),
        to_attr="_all_trial_grants_v2",
    ))
from .market_access_serializers import (
    MarketAccessRequestCreateSerializer,
    MarketAccessRequestReadSerializer,
    MarketAccessRequestReviewSerializer,
)


class ContentSectionPolicyView(APIView):
    """Global article/video/live tier switches in User & Access Management."""

    permission_classes = [IsAuthenticated, CanManageMarketAccess, MarketAccessV2Enabled]

    @extend_schema(responses={200: ContentSectionPolicySerializer(many=True)})
    def get(self, request):
        return Response(ContentSectionPolicySerializer(content_policy_rows(), many=True).data)

    @extend_schema(
        request=ContentSectionPolicyUpdateSerializer,
        responses={200: ContentSectionPolicySerializer(many=True)},
    )
    def patch(self, request):
        incoming = ContentSectionPolicyUpdateSerializer(data=request.data)
        incoming.is_valid(raise_exception=True)
        update_content_section_policy(actor=request.user, **incoming.validated_data)
        return Response(ContentSectionPolicySerializer(content_policy_rows(), many=True).data)


@method_decorator(never_cache, name="dispatch")
class MyMarketPreferencesView(APIView):
    """User selections are requests/preferences, never direct entitlements."""

    permission_classes = [IsAuthenticated, MarketAccessV2Enabled]

    @extend_schema(responses={200: MarketAccessStateSerializer})
    def get(self, request):
        return Response(MarketAccessStateSerializer(market_access_payload(request.user)).data)

    @extend_schema(
        request=MyMarketPreferencesUpdateSerializer,
        responses={200: MarketAccessStateSerializer},
    )
    def put(self, request):
        incoming = MyMarketPreferencesUpdateSerializer(data=request.data)
        incoming.is_valid(raise_exception=True)
        user = update_market_preferences(
            user=request.user,
            selected_markets=incoming.validated_data["selected_markets"],
        )
        return Response(MarketAccessStateSerializer(market_access_payload(user)).data)


@extend_schema_view(get=extend_schema(parameters=[
    OpenApiParameter("membership_tier", str, required=False, enum=["LEVEL_1", "BASIC", "PRO", "GOLD"]),
    OpenApiParameter("is_elite", bool, required=False),
    OpenApiParameter("ordering", str, required=False, enum=["created_at", "-created_at", "date_joined", "-date_joined"]),
]))
@method_decorator(never_cache, name="dispatch")
class MarketAccessUserListView(generics.ListAPIView):
    """Paginated admin list; no legacy user endpoint is changed."""

    permission_classes = [IsAuthenticated, CanManageMarketAccess, MarketAccessV2Enabled]
    serializer_class = UserMarketAccessReadSerializer
    filter_backends = [SearchFilter]
    search_fields = ["username", "first_name", "last_name", "phone", "email"]

    def get_queryset(self):
        params = self.request.query_params
        unexpected = set(params) - {"page", "page_size", "search", "membership_tier", "is_elite", "ordering"}
        if unexpected:
            raise ValidationError({field: "Unknown filter." for field in sorted(unexpected)})
        ordering = params.get("ordering") or "-created_at"
        ordering_fields = {
            "created_at": ("date_joined", "pk"),
            "-created_at": ("-date_joined", "-pk"),
            "date_joined": ("date_joined", "pk"),
            "-date_joined": ("-date_joined", "-pk"),
        }.get(ordering)
        if ordering_fields is None:
            raise ValidationError({"ordering": "Use created_at or -created_at."})
        tier = params.get("membership_tier")
        if tier is not None and tier not in ("LEVEL_1", "BASIC", "PRO", "GOLD"):
            raise ValidationError({"membership_tier": "Invalid membership tier."})
        elite = params.get("is_elite")
        if elite is not None and elite.lower() not in ("true", "false"):
            raise ValidationError({"is_elite": "Use true or false."})
        queryset = User.objects.all()
        if tier is not None:
            market_count = {"LEVEL_1": 0, "BASIC": 1, "PRO": 2, "GOLD": 3}[tier]
            queryset = queryset.annotate(
                _active_market_count=Count(
                    "market_grants_v2",
                    filter=Q(market_grants_v2__revoked_at__isnull=True),
                    distinct=True,
                )
            ).filter(_active_market_count=market_count)
            # Special roles have no count-based membership tier.
            queryset = queryset.exclude(Q(is_superuser=True) | Q(role__in=(User.Role.SUPER_ADMIN, User.Role.SUPPORT)))
        if elite is not None:
            if elite.lower() == "true":
                queryset = queryset.filter(market_access_profile__is_elite=True)
            else:
                queryset = queryset.filter(
                    Q(market_access_profile__is_elite=False)
                    | Q(market_access_profile__isnull=True)
                )
        return _with_trial_admin_diagnostics(queryset.order_by(*ordering_fields))


@method_decorator(never_cache, name="dispatch")
class MarketAccessUserDetailView(generics.RetrieveAPIView):
    """Read state or atomically replace approved markets and/or Elite."""

    permission_classes = [IsAuthenticated, CanManageMarketAccess, MarketAccessV2Enabled]
    serializer_class = UserMarketAccessReadSerializer

    def get_queryset(self):
        return _with_trial_admin_diagnostics(User.objects.all())

    @extend_schema(
        request=UserMarketAccessUpdateSerializer,
        responses={200: UserMarketAccessReadSerializer},
    )
    def patch(self, request, *args, **kwargs):
        incoming = UserMarketAccessUpdateSerializer(data=request.data)
        incoming.is_valid(raise_exception=True)
        target = update_user_market_access(
            actor=request.user,
            user_id=kwargs["pk"],
            approved_markets=incoming.validated_data.get("approved_markets"),
            is_elite=incoming.validated_data.get("is_elite"),
        )
        return Response(self.get_serializer(target).data, status=status.HTTP_200_OK)


class MarketTrialCampaignPreviewView(APIView):
    permission_classes = [IsAuthenticated, CanStartMarketTrialCampaign, MarketAccessV2Enabled]

    @extend_schema(
        request=TrialCampaignPreviewInputSerializer,
        responses={200: TrialCampaignPreviewResponseSerializer},
    )
    def post(self, request):
        incoming = TrialCampaignPreviewInputSerializer(data=request.data)
        incoming.is_valid(raise_exception=True)
        result = preview_trial_campaign(
            actor=request.user,
            registered_from=incoming.validated_data.get("registered_from"),
        )
        return Response(TrialCampaignPreviewResponseSerializer(result).data)


@method_decorator(never_cache, name="dispatch")
class MarketTrialEligibleUsersView(generics.ListAPIView):
    """Paginated people behind the preview count; the digest remains opaque."""

    permission_classes = [IsAuthenticated, CanStartMarketTrialCampaign, MarketAccessV2Enabled]
    serializer_class = UserMarketAccessReadSerializer
    pagination_class = DefaultPagination
    filter_backends = [SearchFilter]
    search_fields = ["username", "first_name", "last_name", "phone", "email"]

    def get_queryset(self):
        unexpected = set(self.request.query_params) - {
            "registered_from", "search", "page", "page_size",
        }
        if unexpected:
            raise ValidationError({field: "Unknown filter." for field in sorted(unexpected)})
        values = {}
        if "registered_from" in self.request.query_params:
            values["registered_from"] = self.request.query_params["registered_from"]
        incoming = TrialCampaignPreviewInputSerializer(data=values)
        incoming.is_valid(raise_exception=True)
        return _with_trial_admin_diagnostics(
            eligible_trial_users(
                registered_from=incoming.validated_data.get("registered_from"),
            ).order_by("pk")
        )


@method_decorator(never_cache, name="dispatch")
class MyTrialEnsureView(APIView):
    """Idempotent app-entry hook for users who kept an existing JWT session."""

    permission_classes = [IsAuthenticated, MarketAccessV2Enabled]

    @extend_schema(responses={200: inline_serializer(
        name="MyTrialEnsureResponse",
        fields={
            "started": serializers.BooleanField(),
            "existing_user_auto_start_enabled": serializers.BooleanField(),
            "access": MarketAccessStateSerializer(),
        },
    )})
    def post(self, request):
        grant = start_existing_user_trial(request.user)
        if grant is not None:
            from apps.notifications.trial_journey import queue_trial_day_one
            from django.db import transaction

            transaction.on_commit(lambda grant_id=grant.pk: queue_trial_day_one(grant_id))
        return Response({
            "started": grant is not None,
            "existing_user_auto_start_enabled": settings.TRIAL_EXISTING_LOGIN_ENABLED,
            "access": market_access_payload(request.user),
        })


class MarketTrialCampaignStartView(APIView):
    permission_classes = [IsAuthenticated, CanStartMarketTrialCampaign, MarketAccessV2Enabled]

    @extend_schema(
        request=TrialCampaignStartInputSerializer,
        responses={201: TrialCampaignStartResponseSerializer},
    )
    def post(self, request):
        incoming = TrialCampaignStartInputSerializer(data=request.data)
        incoming.is_valid(raise_exception=True)
        result = start_trial_campaign(
            actor=request.user,
            registered_from=incoming.validated_data.get("registered_from"),
            expected_eligible_count=incoming.validated_data["expected_eligible_count"],
            expected_candidate_digest=incoming.validated_data["expected_candidate_digest"],
        )
        return Response(
            TrialCampaignStartResponseSerializer(result).data,
            status=status.HTTP_201_CREATED,
        )


@method_decorator(never_cache, name="dispatch")
class TrialAutoStartSettingsView(APIView):
    permission_classes = [IsAuthenticated, CanStartMarketTrialCampaign, MarketAccessV2Enabled]

    @extend_schema(responses={200: TrialAutoStartSettingsSerializer})
    def get(self, request):
        return Response(auto_start_settings_payload())

    @extend_schema(request=TrialAutoStartSettingsSerializer, responses={200: TrialAutoStartSettingsSerializer})
    def patch(self, request):
        incoming = TrialAutoStartSettingsSerializer(data=request.data)
        incoming.is_valid(raise_exception=True)
        return Response(update_auto_start_settings(
            actor=request.user,
            auto_start_new_users=incoming.validated_data["auto_start_new_users"],
        ))


@method_decorator(never_cache, name="dispatch")
class MyMarketAccessRequestView(generics.ListAPIView):
    """Applications only; no price, wallet hold or legacy level mutation."""

    permission_classes = [IsAuthenticated, MarketAccessV2Enabled]
    serializer_class = MarketAccessRequestReadSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return MarketAccessRequest.objects.none()
        return MarketAccessRequest.objects.filter(user=self.request.user).select_related("user", "reviewed_by")

    @extend_schema(
        request=MarketAccessRequestCreateSerializer,
        responses={200: MarketAccessRequestReadSerializer, 201: MarketAccessRequestReadSerializer},
    )
    def post(self, request):
        incoming = MarketAccessRequestCreateSerializer(data=request.data)
        incoming.is_valid(raise_exception=True)
        application, created = submit_market_access_request(
            user=request.user, **incoming.validated_data
        )
        return Response(
            self.get_serializer(application).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


@method_decorator(never_cache, name="dispatch")
class MarketAccessRequestManagementView(generics.ListAPIView):
    permission_classes = [IsAuthenticated, CanManageMarketAccess, MarketAccessV2Enabled]
    serializer_class = MarketAccessRequestReadSerializer
    filter_backends = [SearchFilter]
    search_fields = ["user__username", "user__phone", "user__first_name", "user__last_name"]

    def get_queryset(self):
        queryset = MarketAccessRequest.objects.select_related("user", "reviewed_by")
        requested_status = self.request.query_params.get("status", "")
        if requested_status in MarketAccessRequest.Status.values:
            queryset = queryset.filter(status=requested_status)
        return queryset


@method_decorator(never_cache, name="dispatch")
class MarketAccessRequestReviewView(APIView):
    permission_classes = [IsAuthenticated, CanManageMarketAccess, MarketAccessV2Enabled]

    @extend_schema(
        request=MarketAccessRequestReviewSerializer,
        responses={200: MarketAccessRequestReadSerializer},
    )
    def patch(self, request, pk):
        incoming = MarketAccessRequestReviewSerializer(data=request.data)
        incoming.is_valid(raise_exception=True)
        application = review_market_access_request(
            actor=request.user, request_id=pk, **incoming.validated_data
        )
        return Response(MarketAccessRequestReadSerializer(application).data)
