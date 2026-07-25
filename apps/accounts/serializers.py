from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import (
    validate_password,
)
from rest_framework import serializers
from django.db import IntegrityError, transaction
from rest_framework_simplejwt.exceptions import (
    TokenError,
)
from rest_framework_simplejwt.serializers import (
    TokenObtainPairSerializer,
)
from rest_framework_simplejwt.tokens import (
    RefreshToken,
)

from common.validators import (
    validate_image_upload,
)
from common.validators import (
    validate_image_upload,
)
from django.utils import timezone

from .models import PlatformRole, UpgradeRequest, UserProfile

User = get_user_model()


class PlatformRoleSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = PlatformRole
        fields = (
            "id",
            "name",
            "permissions",
        )


class UserSerializer(serializers.ModelSerializer):
    custom_role = PlatformRoleSummarySerializer(
        read_only=True,
        allow_null=True,
    )

    class Meta:
        model = User
        fields = (
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "phone",
            "avatar",
            "role",
            "access_level",
            "custom_role",
            "is_verified",
            "created_at",
        )
        read_only_fields = (
            "id",
            "username",
            "email",
            "role",
            "access_level",
            "is_verified",
            "created_at",
        )


class CustomTokenObtainPairSerializer(
    TokenObtainPairSerializer
):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)

        token["username"] = user.username
        token["role"] = user.role
        token["access_level"] = user.access_level
        token["custom_role_id"] = user.custom_role_id

        return token

    def validate(self, attrs):
        data = super().validate(attrs)

        data["user"] = UserSerializer(
            self.user,
            context=self.context,
        ).data

        return data


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(
        write_only=True,
        trim_whitespace=False,
        validators=[
            validate_password,
        ],
    )

    class Meta:
        model = User
        fields = (
            "id",
            "username",
            "email",
            "password",
            "first_name",
            "last_name",
            "role",
            "access_level",
        )
        read_only_fields = (
            "id",
            "role",
            "access_level",
        )

    def create(self, validated_data):
        with transaction.atomic():
            user = User.objects.create_user(
                username=validated_data["username"],
                email=validated_data["email"],
                password=validated_data["password"],
                first_name=validated_data.get(
                    "first_name",
                    "",
                ),
                last_name=validated_data.get(
                    "last_name",
                    "",
                ),
                role=User.Role.USER,
                access_level=User.AccessLevel.LEVEL_1,
            )
            UserProfile.objects.create(user=user)
            return user

    def validate_email(self, value):
        normalized_email = (
            value.strip().lower()
        )

        if User.objects.filter(
            email__iexact=normalized_email
        ).exists():
            raise serializers.ValidationError(
                (
                    "A user with this email "
                    "already exists."
                )
            )

        return normalized_email


class UserListSerializer(
    serializers.ModelSerializer
):
    custom_role = PlatformRoleSummarySerializer(
        read_only=True,
        allow_null=True,
    )

    class Meta:
        model = User
        fields = (
            "id",
            "username",
            "first_name",
            "last_name",
            "email",
            "role",
            "access_level",
            "custom_role",
            "is_active",
        )


class UserRoleUpdateSerializer(
    serializers.Serializer
):
    role = serializers.ChoiceField(
        choices=User.Role.choices,
    )


class UserAccessLevelUpdateSerializer(serializers.Serializer):
    access_level = serializers.ChoiceField(
        choices=User.AccessLevel.choices,
    )


class PlatformRoleSerializer(serializers.ModelSerializer):
    permissions = serializers.ListField(
        child=serializers.ChoiceField(
            choices=User.Permission.choices,
        ),
        allow_empty=True,
    )
    users_count = serializers.IntegerField(
        source="users.count",
        read_only=True,
    )

    class Meta:
        model = PlatformRole
        fields = (
            "id",
            "name",
            "slug",
            "description",
            "permissions",
            "is_active",
            "users_count",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "slug",
            "users_count",
            "created_at",
            "updated_at",
        )

    def validate_permissions(self, value):
        if len(value) != len(set(value)):
            raise serializers.ValidationError(
                "Each permission may only be selected once."
            )
        return sorted(value)


class UserCustomRoleUpdateSerializer(serializers.Serializer):
    custom_role_id = serializers.PrimaryKeyRelatedField(
        source="custom_role",
        queryset=PlatformRole.objects.filter(is_active=True),
        allow_null=True,
    )


class UserProfileDetailsSerializer(serializers.ModelSerializer):
    username = serializers.CharField(
        source="user.username",
        read_only=True,
    )
    email = serializers.EmailField(
        source="user.email",
        read_only=True,
    )
    profile_completion = serializers.SerializerMethodField()

    MARKET_CHOICES = {
        "FOREX",
        "CRYPTO",
        "STOCKS",
        "GOLD",
        "INDICES",
        "COMMODITIES",
    }

    class Meta:
        model = UserProfile
        fields = (
            "id",
            "username",
            "email",
            "bio",
            "birth_date",
            "gender",
            "country",
            "city",
            "address",
            "postal_code",
            "marital_status",
            "education_level",
            "occupation",
            "job_title",
            "company_name",
            "monthly_income_range",
            "income_currency",
            "income_sources",
            "financial_dependents",
            "trading_experience_years",
            "risk_tolerance",
            "investment_goal",
            "preferred_markets",
            "trading_frequency",
            "daily_free_time_minutes",
            "learning_hours_weekly",
            "preferred_learning_time",
            "exercise_days_per_week",
            "sleep_hours_average",
            "interests",
            "habits",
            "onboarding_answers",
            "profile_completion",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "username",
            "email",
            "profile_completion",
            "created_at",
            "updated_at",
        )

    def _validate_string_list(self, value, field_name, max_items=30):
        if not isinstance(value, list):
            raise serializers.ValidationError("Must be a list.")
        if len(value) > max_items:
            raise serializers.ValidationError(
                f"At most {max_items} items are allowed."
            )
        cleaned = []
        for item in value:
            if not isinstance(item, str) or not item.strip():
                raise serializers.ValidationError(
                    "Every item must be a non-empty string."
                )
            cleaned.append(item.strip())
        if len(cleaned) != len(set(cleaned)):
            raise serializers.ValidationError(
                "Duplicate items are not allowed."
            )
        return cleaned

    def validate_birth_date(self, value):
        if value and value > timezone.localdate():
            raise serializers.ValidationError(
                "Birth date cannot be in the future."
            )
        return value

    def validate_income_sources(self, value):
        return self._validate_string_list(value, "income_sources")

    def validate_interests(self, value):
        return self._validate_string_list(value, "interests")

    def validate_preferred_markets(self, value):
        value = self._validate_string_list(
            value,
            "preferred_markets",
            max_items=len(self.MARKET_CHOICES),
        )
        invalid = set(value) - self.MARKET_CHOICES
        if invalid:
            raise serializers.ValidationError(
                f"Unsupported markets: {', '.join(sorted(invalid))}."
            )
        return value

    def validate_habits(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("Must be an object.")
        return value

    def validate_onboarding_answers(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("Must be an object.")
        return value

    def _validate_maximum(self, value, maximum):
        if value is not None and value > maximum:
            raise serializers.ValidationError(
                f"Must be at most {maximum}."
            )
        return value

    def validate_exercise_days_per_week(self, value):
        return self._validate_maximum(value, 7)

    def validate_sleep_hours_average(self, value):
        return self._validate_maximum(value, 24)

    def validate_daily_free_time_minutes(self, value):
        return self._validate_maximum(value, 1440)

    def validate_learning_hours_weekly(self, value):
        return self._validate_maximum(value, 168)

    def get_profile_completion(self, obj) -> int:
        tracked_fields = (
            "birth_date",
            "country",
            "city",
            "education_level",
            "occupation",
            "monthly_income_range",
            "trading_experience_years",
            "risk_tolerance",
            "investment_goal",
            "preferred_markets",
            "trading_frequency",
            "preferred_learning_time",
        )
        completed = sum(
            bool(getattr(obj, field))
            for field in tracked_fields
        )
        return round(completed * 100 / len(tracked_fields))


class UpgradeRequestSerializer(serializers.ModelSerializer):
    reviewed_by = serializers.CharField(
        source="reviewed_by.username",
        read_only=True,
        allow_null=True,
    )

    class Meta:
        model = UpgradeRequest
        fields = (
            "id",
            "request_type",
            "requested_level",
            "message",
            "status",
            "admin_note",
            "reviewed_by",
            "reviewed_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "status",
            "admin_note",
            "reviewed_by",
            "reviewed_at",
            "created_at",
            "updated_at",
        )

    def validate(self, attrs):
        user = self.context["request"].user
        request_type = attrs.get(
            "request_type",
            UpgradeRequest.Type.UPGRADE,
        )
        requested_level = attrs["requested_level"]

        if (
            request_type == UpgradeRequest.Type.PREMIUM
            and requested_level != 5
        ):
            raise serializers.ValidationError(
                {"requested_level": "Premium subscription must request level 5."}
            )

        if requested_level <= user.access_level:
            raise serializers.ValidationError(
                {"requested_level": "Requested level must be above your current level."}
            )

        if UpgradeRequest.objects.filter(
            user=user,
            status=UpgradeRequest.Status.PENDING,
        ).exists():
            raise serializers.ValidationError(
                "You already have a pending request."
            )

        return attrs

    def create(self, validated_data):
        try:
            with transaction.atomic():
                return UpgradeRequest.objects.create(
                    user=self.context["request"].user,
                    **validated_data,
                )
        except IntegrityError:
            raise serializers.ValidationError(
                "You already have a pending request."
            )


class AdminUpgradeRequestSerializer(UpgradeRequestSerializer):
    user = UserListSerializer(read_only=True)

    class Meta(UpgradeRequestSerializer.Meta):
        fields = ("user",) + UpgradeRequestSerializer.Meta.fields


class UpgradeRequestReviewSerializer(serializers.Serializer):
    status = serializers.ChoiceField(
        choices=(
            UpgradeRequest.Status.APPROVED,
            UpgradeRequest.Status.REJECTED,
        )
    )
    admin_note = serializers.CharField(
        required=False,
        allow_blank=True,
    )


class ProfileUpdateSerializer(
    serializers.ModelSerializer
):
    phone = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
        max_length=20,
    )

    class Meta:
        model = User
        fields = (
            "first_name",
            "last_name",
            "phone",
            "avatar",
        )
        extra_kwargs = {
            "first_name": {
                "required": False,
            },
            "last_name": {
                "required": False,
            },
            "avatar": {
                "required": False,
                "allow_null": True,
            },
        }

    def validate_phone(self, value):
        if value in (
            None,
            "",
        ):
            return None

        normalized_phone = value.strip()

        queryset = User.objects.filter(
            phone=normalized_phone
        )

        if self.instance:
            queryset = queryset.exclude(
                pk=self.instance.pk
            )

        if queryset.exists():
            raise serializers.ValidationError(
                (
                    "A user with this phone "
                    "number already exists."
                )
            )

        return normalized_phone

    def validate_avatar(self, value):
        return validate_image_upload(
            value,
            max_size_mb=5,
            file_label="Avatar",
        )


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField(
        write_only=True,
        trim_whitespace=False,
    )

    default_error_messages = {
        "invalid_token": (
            "Invalid or expired refresh token."
        ),
        "wrong_user": (
            "This refresh token does not belong "
            "to the authenticated user."
        ),
    }

    def validate_refresh(self, value):
        try:
            token = RefreshToken(value)
        except TokenError:
            self.fail("invalid_token")

        request = self.context.get("request")
        token_user_id = token.get("user_id")

        if (
            request
            and request.user.is_authenticated
            and str(token_user_id)
            != str(request.user.pk)
        ):
            self.fail("wrong_user")

        self.token = token
        return value

    def save(self, **kwargs):
        self.token.blacklist()
