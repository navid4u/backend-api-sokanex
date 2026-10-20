"""V2 management contract; deliberately separate from legacy user serializers."""

from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field

from .market_access import MARKETS, market_access_payload
from .models import MarketAccessRequest, User


class ContentSectionPolicySerializer(serializers.Serializer):
    section = serializers.ChoiceField(choices=("ARTICLES", "VIDEOS", "LIVESTREAMS"))
    allowed_tiers = serializers.ListField(child=serializers.ChoiceField(choices=("LEVEL_1", "BASIC", "PRO", "GOLD")), allow_empty=True, max_length=4)
    updated_at = serializers.DateTimeField(allow_null=True, read_only=True)


class ContentSectionPolicyUpdateSerializer(ContentSectionPolicySerializer):
    def validate_allowed_tiers(self, value):
        if len(value) != len(set(value)):
            raise serializers.ValidationError("Each tier may be selected only once.")
        return value

    def validate(self, attrs):
        unexpected = set(self.initial_data) - {"section", "allowed_tiers"}
        if unexpected:
            raise serializers.ValidationError(
                {field: "This field cannot be changed here." for field in sorted(unexpected)}
            )
        return attrs


class UserMarketAccessReadSerializer(serializers.ModelSerializer):
    legacy_access_level = serializers.IntegerField(source="access_level", read_only=True)
    access = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id", "username", "first_name", "last_name", "phone", "email", "role",
            "is_active", "date_joined", "legacy_access_level", "access",
        )
        read_only_fields = fields

    @extend_schema_field(serializers.DictField())
    def get_access(self, obj):
        from .market_access import current_trial_grant
        from .models import TrialGrant

        payload = market_access_payload(obj)
        trial = current_trial_grant(obj)
        all_grants = getattr(obj, "_all_trial_grants_v2", None)
        latest = trial or (
            (all_grants[0] if all_grants else None) if all_grants is not None
            else TrialGrant.objects.filter(user=obj).order_by("-started_at", "-pk").first()
        )
        decision = getattr(obj, "trial_auto_start_decision", None)
        if latest is None:
            trial_status = "NOT_STARTED"
        elif latest.revoked_at or latest.invalidated_at:
            trial_status = "CANCELED"
        elif payload.get("trial_active"):
            trial_status = "ACTIVE"
        else:
            trial_status = "EXPIRED"
        payload.update({
            "trial_status": trial_status,
            "trial_started_at": latest.started_at if latest else None,
            "trial_ends_at": latest.ends_at if latest else None,
            "trial_source": (latest.source or None) if latest else None,
            "trial_start_blocked_reason": (
                decision.reason if decision and decision.reason != "STARTED" else None
            ),
        })
        return payload


class UserMarketAccessUpdateSerializer(serializers.Serializer):
    approved_markets = serializers.ListField(
        child=serializers.ChoiceField(choices=sorted(MARKETS)),
        required=False,
        allow_empty=True,
        max_length=3,
    )
    is_elite = serializers.BooleanField(required=False)

    def validate_approved_markets(self, value):
        if len(value) != len(set(value)):
            raise serializers.ValidationError("Each market may be selected only once.")
        return value

    def validate(self, attrs):
        unexpected = set(self.initial_data) - {"approved_markets", "is_elite"}
        if unexpected:
            raise serializers.ValidationError(
                {field: "This field cannot be changed here." for field in sorted(unexpected)}
            )
        if not attrs:
            raise serializers.ValidationError("Provide approved_markets or is_elite.")
        return attrs


class MyMarketPreferencesUpdateSerializer(serializers.Serializer):
    selected_markets = serializers.ListField(
        child=serializers.ChoiceField(choices=sorted(MARKETS)),
        allow_empty=False,
        max_length=3,
    )

    def validate_selected_markets(self, value):
        if len(value) != len(set(value)):
            raise serializers.ValidationError("Each market may be selected only once.")
        return value

    def validate(self, attrs):
        unexpected = set(self.initial_data) - {"selected_markets"}
        if unexpected:
            raise serializers.ValidationError(
                {field: "This field cannot be changed here." for field in sorted(unexpected)}
            )
        return attrs


class MarketAccessStateSerializer(serializers.Serializer):
    enabled = serializers.BooleanField()
    membership_tier = serializers.CharField(allow_null=True)
    selected_markets = serializers.ListField(child=serializers.CharField())
    approved_markets = serializers.ListField(child=serializers.CharField())
    effective_markets = serializers.ListField(child=serializers.CharField())
    market_selection_confirmed = serializers.BooleanField()
    trial_used = serializers.BooleanField()
    trial_active = serializers.BooleanField()
    trial_started_at = serializers.DateTimeField(allow_null=True)
    trial_ends_at = serializers.DateTimeField(allow_null=True)
    is_elite = serializers.BooleanField()
    has_gold_features = serializers.BooleanField()
    special_role = serializers.CharField(allow_null=True)


class TrialCampaignPreviewInputSerializer(serializers.Serializer):
    registered_from = serializers.DateField(required=False, allow_null=True)

    def validate(self, attrs):
        unexpected = set(self.initial_data) - set(self.fields)
        if unexpected:
            raise serializers.ValidationError(
                {field: "This field is not accepted." for field in sorted(unexpected)}
            )
        return attrs


class TrialAutoStartSettingsSerializer(serializers.Serializer):
    auto_start_new_users = serializers.BooleanField()

    def validate(self, attrs):
        unexpected = set(self.initial_data) - {"auto_start_new_users"}
        if unexpected:
            raise serializers.ValidationError({key: "This field is not accepted." for key in sorted(unexpected)})
        return attrs


class TrialCampaignStartInputSerializer(TrialCampaignPreviewInputSerializer):
    expected_eligible_count = serializers.IntegerField(min_value=1)
    expected_candidate_digest = serializers.RegexField(r"^[a-f0-9]{64}$")
    confirm = serializers.BooleanField()

    def validate_confirm(self, value):
        if not value:
            raise serializers.ValidationError("Explicit confirmation is required.")
        return value


class TrialCampaignPreviewResponseSerializer(serializers.Serializer):
    registered_from = serializers.DateField(allow_null=True)
    duration_days = serializers.IntegerField()
    eligible_count = serializers.IntegerField()
    candidate_digest = serializers.CharField()


class TrialCampaignStartResponseSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    status = serializers.CharField()
    registered_from = serializers.DateField(allow_null=True)
    duration_days = serializers.IntegerField()
    started_at = serializers.DateTimeField()
    ends_at = serializers.DateTimeField()
    granted_count = serializers.IntegerField()


class MarketAccessRequestCreateSerializer(serializers.Serializer):
    requested_tier = serializers.ChoiceField(choices=MarketAccessRequest.RequestedTier.choices)
    message = serializers.CharField(required=False, allow_blank=True, max_length=1000)

    def validate(self, attrs):
        unexpected = set(self.initial_data) - set(self.fields)
        if unexpected:
            raise serializers.ValidationError(
                {field: "This field is not accepted." for field in sorted(unexpected)}
            )
        return attrs


class MarketAccessRequestReviewSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=("APPROVED", "REJECTED"))
    approved_markets = serializers.ListField(
        child=serializers.ChoiceField(choices=sorted(MARKETS)),
        required=False, allow_empty=False, max_length=3,
    )
    is_elite = serializers.BooleanField(required=False)
    admin_note = serializers.CharField(required=False, allow_blank=True, max_length=1000)

    def validate_approved_markets(self, value):
        if len(value) != len(set(value)):
            raise serializers.ValidationError("Each market may be approved only once.")
        return value

    def validate(self, attrs):
        unexpected = set(self.initial_data) - set(self.fields)
        if unexpected:
            raise serializers.ValidationError(
                {field: "This field is not accepted." for field in sorted(unexpected)}
            )
        return attrs


class MarketAccessRequestUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "username", "first_name", "last_name", "phone")
        read_only_fields = fields


class MarketAccessRequestReadSerializer(serializers.ModelSerializer):
    user = MarketAccessRequestUserSerializer(read_only=True)
    reviewed_by = serializers.CharField(source="reviewed_by.username", read_only=True, allow_null=True)
    tier_description = serializers.SerializerMethodField()

    class Meta:
        model = MarketAccessRequest
        fields = (
            "id", "user", "requested_tier", "tier_description", "requested_markets",
            "message", "status", "approved_markets", "approved_elite", "admin_note",
            "reviewed_by", "reviewed_at", "created_at", "updated_at",
        )
        read_only_fields = fields

    @extend_schema_field(serializers.CharField())
    def get_tier_description(self, obj):
        return {
            "PRO": "دسترسی به دو بازار تأییدشده؛ سطح از تعداد بازارها محاسبه می‌شود.",
            "GOLD": "درخواست عضویت اولیه؛ بازارها و سطح نهایی را مدیر تعیین می‌کند.",
            "ELITE": "نشان ویژهٔ مستقل از تعداد بازارها؛ دسترسی بازار جداگانه تعیین می‌شود.",
        }[obj.requested_tier]
