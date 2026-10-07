"""New, gated administrator APIs for market membership management."""

from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.filters import SearchFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

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
)
from .market_trial import preview_trial_campaign, start_trial_campaign
from .market_access_requests import submit_market_access_request, review_market_access_request
from .models import MarketAccessRequest, User
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


class MarketAccessUserListView(generics.ListAPIView):
    """Paginated admin list; no legacy user endpoint is changed."""

    permission_classes = [IsAuthenticated, CanManageMarketAccess, MarketAccessV2Enabled]
    serializer_class = UserMarketAccessReadSerializer
    filter_backends = [SearchFilter]
    search_fields = ["username", "first_name", "last_name", "phone"]

    def get_queryset(self):
        return with_market_access_relations(
            User.objects.all().order_by("-date_joined", "-pk")
        )


class MarketAccessUserDetailView(generics.RetrieveAPIView):
    """Read state or atomically replace approved markets and/or Elite."""

    permission_classes = [IsAuthenticated, CanManageMarketAccess, MarketAccessV2Enabled]
    serializer_class = UserMarketAccessReadSerializer

    def get_queryset(self):
        return with_market_access_relations(User.objects.all())

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
