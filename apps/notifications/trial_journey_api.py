from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from common.permissions import CanStartMarketTrialCampaign, MarketAccessV2Enabled

from .trial_journey import TrialJourneySerializer, journey_payload, update_journey


class TrialJourneyView(APIView):
    permission_classes = (IsAuthenticated, CanStartMarketTrialCampaign, MarketAccessV2Enabled)

    @extend_schema(responses={200: TrialJourneySerializer})
    def get(self, request):
        return Response(journey_payload())

    @extend_schema(request=TrialJourneySerializer, responses={200: TrialJourneySerializer})
    def put(self, request):
        incoming = TrialJourneySerializer(data=request.data)
        incoming.is_valid(raise_exception=True)
        return Response(update_journey(actor=request.user, days=incoming.validated_data["days"]))
