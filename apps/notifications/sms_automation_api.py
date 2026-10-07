"""Super-administrator SMS automation management API."""

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Q
from django.utils import timezone
from django.core.validators import RegexValidator
from drf_spectacular.utils import extend_schema
from rest_framework import generics, serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.market_access import market_access_v2_enabled
from apps.accounts.models import User
from common.pagination import DefaultPagination
from common.permissions import CanStartMarketTrialCampaign

from .models import SMSAutomationDelivery, SMSAutomationRule, SMSBroadcast
from .sms_automation import (
    TIERS, broadcast_candidates, broadcast_digest, create_broadcast, validate_template,
)


class SMSRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = SMSAutomationRule
        fields = (
            "id", "event", "market", "slot", "trial_day", "text", "enabled",
            "send_time_utc", "delay_minutes", "enabled_at", "updated_at", "updated_by",
        )
        read_only_fields = ("id", "event", "market", "slot", "enabled_at", "updated_at", "updated_by")

    def validate_text(self, value):
        try:
            return validate_template(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc

    def validate_trial_day(self, value):
        if value is not None and not 1 <= value <= 7:
            raise serializers.ValidationError("روز آزمایشی باید بین ۱ تا ۷ باشد.")
        return value

    def validate_delay_minutes(self, value):
        if value > 10080:
            raise serializers.ValidationError("حداکثر تأخیر یک هفته است.")
        return value

    def validate(self, attrs):
        if self.instance and self.instance.event == SMSAutomationRule.Event.TRIAL:
            if attrs.get("trial_day", self.instance.trial_day) is None:
                raise serializers.ValidationError({"trial_day": "روز آزمایشی الزامی است."})
            if "delay_minutes" in attrs:
                raise serializers.ValidationError({"delay_minutes": "برای Trial از ساعت UTC استفاده کنید."})
        elif "trial_day" in attrs:
            raise serializers.ValidationError({"trial_day": "این فیلد فقط برای Trial است."})
        elif "send_time_utc" in attrs:
            raise serializers.ValidationError({"send_time_utc": "برای پیام رویدادی از تأخیر دقیقه‌ای استفاده کنید."})
        return attrs

    def update(self, instance, validated_data):
        if validated_data.get("enabled") is True and not instance.enabled:
            instance.enabled_at = timezone.now()
        for key, value in validated_data.items():
            setattr(instance, key, value)
        instance.updated_by = self.context["request"].user
        instance.save()
        return instance


class SMSDeliverySerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)
    rule_slot = serializers.CharField(source="rule.slot", read_only=True, allow_null=True)

    class Meta:
        model = SMSAutomationDelivery
        fields = (
            "id", "user", "username", "phone", "event", "rule_slot", "broadcast",
            "text", "status", "scheduled_at", "claimed_at", "sent_at",
            "provider_message_id", "failure_code", "attempts", "created_at",
        )


class SMSBroadcastInputSerializer(serializers.Serializer):
    membership_tiers = serializers.ListField(
        child=serializers.ChoiceField(choices=sorted(TIERS)), min_length=1, max_length=5,
    )
    market = serializers.ChoiceField(choices=SMSAutomationRule.Market.choices, default="ALL")
    text = serializers.CharField(max_length=500)

    def validate_text(self, value):
        try:
            return validate_template(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc

    def validate_membership_tiers(self, value):
        if len(set(value)) != len(value):
            raise serializers.ValidationError("سطوح تکراری مجاز نیستند.")
        return value


class SMSBroadcastCreateSerializer(SMSBroadcastInputSerializer):
    idempotency_key = serializers.CharField(
        min_length=8, max_length=64,
        validators=[RegexValidator(r"^[A-Za-z0-9_-]+$", "شناسه ارسال نامعتبر است.")],
    )
    expected_eligible_count = serializers.IntegerField(min_value=1)
    expected_candidate_digest = serializers.RegexField(r"^[0-9a-f]{64}$")
    confirm = serializers.BooleanField()

    def validate_confirm(self, value):
        if not value:
            raise serializers.ValidationError("تأیید صریح لازم است.")
        return value


class SMSAutomationStatusResponseSerializer(serializers.Serializer):
    automation_enabled = serializers.BooleanField()
    provider_configured = serializers.BooleanField()
    market_access_v2_enabled = serializers.BooleanField()
    enabled_rules = serializers.IntegerField()
    pending = serializers.IntegerField()
    needs_reconciliation = serializers.IntegerField()


class SMSBroadcastPreviewResponseSerializer(serializers.Serializer):
    eligible_count = serializers.IntegerField()
    candidate_digest = serializers.CharField()
    membership_tiers = serializers.ListField(child=serializers.CharField())
    market = serializers.CharField()
    text = serializers.CharField()


class SMSBroadcastCreatedResponseSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    status = serializers.CharField()
    recipient_count = serializers.IntegerField()


class SMSRuleListView(generics.ListAPIView):
    permission_classes = (IsAuthenticated, CanStartMarketTrialCampaign)
    serializer_class = SMSRuleSerializer
    pagination_class = None
    queryset = SMSAutomationRule.objects.select_related("updated_by").all()


class SMSRuleDetailView(generics.RetrieveUpdateAPIView):
    permission_classes = (IsAuthenticated, CanStartMarketTrialCampaign)
    serializer_class = SMSRuleSerializer
    http_method_names = ["get", "patch", "head", "options"]
    queryset = SMSAutomationRule.objects.select_related("updated_by").all()


class SMSDeliveryListView(generics.ListAPIView):
    permission_classes = (IsAuthenticated, CanStartMarketTrialCampaign)
    serializer_class = SMSDeliverySerializer
    pagination_class = DefaultPagination

    def get_queryset(self):
        qs = SMSAutomationDelivery.objects.select_related("user", "rule", "broadcast")
        params = self.request.query_params
        if params.get("status") in SMSAutomationDelivery.Status.values:
            qs = qs.filter(status=params["status"])
        if params.get("event"):
            qs = qs.filter(event=params["event"][:20])
        if params.get("user_id", "").isdigit():
            qs = qs.filter(user_id=int(params["user_id"]))
        if params.get("search"):
            term = params["search"][:80]
            qs = qs.filter(Q(user__username__icontains=term) | Q(phone__icontains=term))
        return qs


class SMSAutomationStatusView(APIView):
    permission_classes = (IsAuthenticated, CanStartMarketTrialCampaign)

    @extend_schema(responses={200: SMSAutomationStatusResponseSerializer})
    def get(self, request):
        return Response({
            "automation_enabled": settings.SMS_AUTOMATION_ENABLED,
            "provider_configured": bool(
                settings.PAYAMITO_ENABLED and settings.PAYAMITO_USERNAME
                and settings.PAYAMITO_API_KEY and settings.PAYAMITO_FROM_NUMBER
            ),
            "market_access_v2_enabled": market_access_v2_enabled(),
            "enabled_rules": SMSAutomationRule.objects.filter(enabled=True).count(),
            "pending": SMSAutomationDelivery.objects.filter(status="PENDING").count(),
            "needs_reconciliation": SMSAutomationDelivery.objects.filter(status="SENDING").count(),
        })


class SMSBroadcastPreviewView(APIView):
    permission_classes = (IsAuthenticated, CanStartMarketTrialCampaign)

    @extend_schema(request=SMSBroadcastInputSerializer, responses={200: SMSBroadcastPreviewResponseSerializer})
    def post(self, request):
        if not market_access_v2_enabled():
            return Response({"detail": "Market Access V2 is disabled."}, status=409)
        serializer = SMSBroadcastInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        ids = [user.pk for user in broadcast_candidates(
            tiers=set(data["membership_tiers"]), market=data["market"]
        )]
        return Response({
            "eligible_count": len(ids),
            "candidate_digest": broadcast_digest(
                ids, data["membership_tiers"], data["market"], data["text"]
            ),
            "membership_tiers": data["membership_tiers"],
            "market": data["market"],
            "text": data["text"],
        })


class SMSBroadcastCreateView(APIView):
    permission_classes = (IsAuthenticated, CanStartMarketTrialCampaign)

    @extend_schema(request=SMSBroadcastCreateSerializer, responses={200: SMSBroadcastCreatedResponseSerializer, 201: SMSBroadcastCreatedResponseSerializer})
    def post(self, request):
        if not settings.SMS_AUTOMATION_ENABLED:
            return Response({"detail": "SMS automation is disabled."}, status=409)
        if not market_access_v2_enabled():
            return Response({"detail": "Market Access V2 is disabled."}, status=409)
        serializer = SMSBroadcastCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            broadcast, created = create_broadcast(
                actor=request.user, tiers=set(data["membership_tiers"]),
                market=data["market"], text=data["text"],
                expected_count=data["expected_eligible_count"],
                expected_digest=data["expected_candidate_digest"],
                idempotency_key=data["idempotency_key"],
            )
        except ValueError as exc:
            if str(exc) == "AUDIENCE_CHANGED":
                return Response({"code": "AUDIENCE_CHANGED", "detail": "مخاطبان تغییر کرده‌اند؛ دوباره پیش‌نمایش بگیرید."}, status=409)
            if str(exc) == "IDEMPOTENCY_CONFLICT":
                return Response({"code": "IDEMPOTENCY_CONFLICT", "detail": "شناسه ارسال قبلاً برای پیام دیگری استفاده شده است."}, status=409)
            raise
        return Response({"id": broadcast.pk, "status": "QUEUED", "recipient_count": broadcast.recipient_count}, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class SMSBroadcastListView(generics.ListAPIView):
    permission_classes = (IsAuthenticated, CanStartMarketTrialCampaign)
    pagination_class = DefaultPagination
    queryset = SMSBroadcast.objects.order_by("-created_at", "-id")

    class BroadcastSerializer(serializers.ModelSerializer):
        class Meta:
            model = SMSBroadcast
            fields = ("id", "created_by", "membership_tiers", "market", "text", "recipient_count", "created_at")

    serializer_class = BroadcastSerializer
