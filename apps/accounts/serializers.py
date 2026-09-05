from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import (
    validate_password,
)
from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
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
    validate_attachment_upload,
    validate_image_upload,
)
from django.utils import timezone
from django.core.exceptions import ValidationError as DjangoValidationError
from common.phone import normalize_iran_phone
from .authentication import issue_login_tokens

from .models import (
    Badge,
    BrokerConnection,
    CrmContactSync,
    FinancialPersonalityAssessment,
    PlatformRole,
    SecuritySettings,
    UpgradeRequest,
    UserBadge,
    UserDevice,
    UserProfile,
)
from .services import FinancialPersonalityService, ProfileCompletionService
from apps.activity.models import UserActivity
from apps.activity.services import ActivityService

User = get_user_model()


class BrokerConnectionSerializer(serializers.ModelSerializer):
    document_url = serializers.SerializerMethodField()
    user = serializers.CharField(source="user.username", read_only=True)

    class Meta:
        model = BrokerConnection
        fields = (
            "id", "user", "status", "rejection_reason", "submitted_at", "reviewed_at",
            "broker_name", "account_number", "referral_code", "document_url",
        )
        read_only_fields = ("id", "user", "status", "rejection_reason", "submitted_at", "reviewed_at", "document_url")

    def get_document_url(self, obj) -> str | None:
        if not obj.document:
            return None
        request = self.context.get("request")
        return request.build_absolute_uri(obj.document.url) if request else obj.document.url

    def validate_document(self, value):
        allowed_types = {"image/jpeg", "image/png", "image/webp", "application/pdf"}
        content_type = getattr(value, "content_type", "").split(";", 1)[0].lower()
        if content_type not in allowed_types:
            raise serializers.ValidationError("Only JPEG, PNG, WebP, or PDF documents are allowed.")
        position = value.tell()
        signature = value.read(12)
        value.seek(position)
        if content_type == "application/pdf" and not signature.startswith(b"%PDF-"):
            raise serializers.ValidationError("The uploaded file is not a valid PDF.")
        if content_type.startswith("image/"):
            try:
                from PIL import Image
                Image.open(value).verify()
                value.seek(position)
            except Exception as exc:
                raise serializers.ValidationError("The uploaded file is not a valid image.") from exc
        return validate_attachment_upload(value, max_size_mb=10, file_label="Broker document")


class BrokerConnectionReviewSerializer(serializers.ModelSerializer):
    class Meta:
        model = BrokerConnection
        fields = ("status", "rejection_reason", "balance", "equity", "currency", "chart")

    def validate_status(self, value):
        if value not in (BrokerConnection.Status.CONNECTED, BrokerConnection.Status.REJECTED, BrokerConnection.Status.PENDING):
            raise serializers.ValidationError("Invalid review status.")
        return value

    def validate(self, attrs):
        if attrs.get("status") == BrokerConnection.Status.REJECTED and not attrs.get("rejection_reason", "").strip():
            raise serializers.ValidationError({"rejection_reason": "A rejection reason is required."})
        return attrs


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
    profile_completion = serializers.SerializerMethodField()
    profile_incomplete = serializers.SerializerMethodField()
    profile_complete = serializers.SerializerMethodField()
    missing_profile_fields = serializers.SerializerMethodField()
    capabilities = serializers.SerializerMethodField()
    crm_sync_status = serializers.SerializerMethodField()
    crm_synced_at = serializers.SerializerMethodField()
    wallet_balance_usd = serializers.SerializerMethodField()
    premium_subscription = serializers.SerializerMethodField()

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
            "profile_completion",
            "profile_incomplete",
            "profile_complete",
            "missing_profile_fields",
            "capabilities",
            "crm_sync_status",
            "crm_synced_at",
            "wallet_balance_usd",
            "premium_subscription",
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

    def _profile_status(self, obj):
        cache = getattr(self, "_profile_status_cache", {})
        if obj.pk not in cache:
            cache[obj.pk] = ProfileCompletionService.status(obj)
            self._profile_status_cache = cache
        return cache[obj.pk]

    def get_profile_completion(self, obj) -> int:
        return self._profile_status(obj)["profile_completion"]

    def get_profile_incomplete(self, obj) -> bool:
        return self._profile_status(obj)["profile_incomplete"]

    def get_profile_complete(self, obj) -> bool:
        return self._profile_status(obj)["profile_complete"]

    def get_missing_profile_fields(self, obj) -> list[str]:
        return self._profile_status(obj)["missing_profile_fields"]

    def get_capabilities(self, obj) -> dict:
        explicit = obj.has_platform_permission(User.Permission.INTERNAL_ANALYSIS_MANAGE)
        fallback = (
            obj.role in (User.Role.ADMIN, User.Role.EMPLOYEE)
            and obj.has_platform_permission(User.Permission.CONTENT_MANAGE)
        )
        return {
            "can_manage_internal_analysis": bool(
                obj.is_superuser
                or obj.role == User.Role.SUPER_ADMIN
                or explicit
                or fallback
            ),
            "can_manage_ai_assistant": obj.has_platform_permission(
                User.Permission.AI_ASSISTANT_MANAGE
            ) or obj.has_platform_permission(User.Permission.PLATFORM_SETTINGS_MANAGE),
        }

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_crm_sync_status(self, obj) -> str | None:
        sync = getattr(obj, "crm_contact_sync", None)
        return sync.status if sync else None

    @extend_schema_field(serializers.DateTimeField(allow_null=True))
    def get_crm_synced_at(self, obj):
        sync = getattr(obj, "crm_contact_sync", None)
        return sync.synced_at if sync else None

    @extend_schema_field(serializers.DecimalField(max_digits=18, decimal_places=2))
    def get_wallet_balance_usd(self, obj):
        from apps.wallet.services import WalletService

        return format(WalletService.balance_usd_for_user(obj), ".2f")

    def get_premium_subscription(self, obj) -> dict:
        from apps.wallet.services import WalletService

        return WalletService.premium_subscription(obj)


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
        identifier = str(attrs.get(self.username_field, "")).strip()
        try:
            attrs[self.username_field] = normalize_iran_phone(identifier)
        except DjangoValidationError:
            attrs[self.username_field] = identifier
        data = super().validate(attrs)
        session = issue_login_tokens(self.user, self.context["request"], data["refresh"])
        data.update(session)

        data["user"] = UserSerializer(
            self.user,
            context=self.context,
        ).data
        return data


class RegisterSerializer(serializers.ModelSerializer):
    username = serializers.CharField(required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    phone = serializers.CharField(required=False)
    first_name = serializers.CharField(required=False, allow_blank=True)
    last_name = serializers.CharField(required=False, allow_blank=True)
    password_confirm = serializers.CharField(write_only=True, required=False)
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
            "phone",
            "password",
            "password_confirm",
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
        validated_data.pop("password_confirm", None)
        phone = validated_data.get("phone")
        username = phone or validated_data["username"]
        with transaction.atomic():
            user = User.objects.create_user(
                username=username,
                phone=phone,
                email=validated_data.get("email", ""),
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
            ActivityService.record(
                user,
                UserActivity.Type.REGISTER,
                "Account registered",
            )
            return user

    def validate_phone(self, value):
        try:
            phone = normalize_iran_phone(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages[0])
        if User.objects.filter(phone=phone).exists() or User.objects.filter(username=phone).exists():
            raise serializers.ValidationError("کاربری با این شماره همراه قبلاً ثبت شده است.")
        return phone

    def validate(self, attrs):
        confirmation = attrs.get("password_confirm")
        if confirmation is not None and confirmation != attrs.get("password"):
            raise serializers.ValidationError({"password_confirm": "تکرار رمز عبور مطابقت ندارد."})
        if attrs.get("phone"):
            missing = {
                field: "این فیلد الزامی است."
                for field in ("first_name", "last_name")
                if not str(attrs.get(field, "")).strip()
            }
            if missing:
                raise serializers.ValidationError(missing)
            attrs["username"] = attrs["phone"]
        elif not str(attrs.get("username", "")).strip():
            raise serializers.ValidationError({"phone": "شماره همراه الزامی است."})
        return attrs

    def validate_email(self, value):
        normalized_email = (
            value.strip().lower()
        )

        if not normalized_email:
            return ""

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
    wallet_balance_usd = serializers.SerializerMethodField()
    premium_subscription = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id",
            "username",
            "first_name",
            "last_name",
            "email",
            "phone",
            "role",
            "access_level",
            "custom_role",
            "is_active",
            "is_verified",
            "wallet_balance_usd",
            "premium_subscription",
            "created_at",
        )

    @extend_schema_field(serializers.DecimalField(max_digits=18, decimal_places=2))
    def get_wallet_balance_usd(self, obj):
        from apps.wallet.services import WalletService

        return format(WalletService.balance_usd_for_user(obj), ".2f")

    def get_premium_subscription(self, obj) -> dict:
        from apps.wallet.services import WalletService

        return WalletService.premium_subscription(obj)


class AdminUserWriteSerializer(serializers.ModelSerializer):
    password = serializers.CharField(
        write_only=True,
        required=False,
        trim_whitespace=False,
        validators=[validate_password],
    )

    class Meta:
        model = User
        fields = (
            "id", "username", "email", "first_name", "last_name",
            "phone", "password", "role", "access_level",
            "custom_role", "is_active", "is_verified",
        )
        read_only_fields = ("id",)

    def validate(self, attrs):
        actor = self.context["request"].user
        target = self.instance
        actor_is_super_admin = (
            actor.is_superuser
            or actor.role == User.Role.SUPER_ADMIN
        )
        actor_is_system_admin = (
            actor_is_super_admin
            or actor.role == User.Role.ADMIN
        )

        if target and target.pk == actor.pk:
            protected_fields = (
                "role",
                "access_level",
                "custom_role",
                "is_active",
                "is_verified",
            )
            changed_fields = [
                field
                for field in protected_fields
                if field in attrs
                and attrs[field] != getattr(target, field)
            ]
            if changed_fields:
                raise serializers.ValidationError(
                    {
                        field: (
                            "You cannot change this field on your "
                            "own account through user management."
                        )
                        for field in changed_fields
                    }
                )

        if (
            target
            and (
                target.is_superuser
                or target.role in (
                    User.Role.SUPER_ADMIN,
                    User.Role.ADMIN,
                )
            )
            and target.pk != actor.pk
            and not actor_is_super_admin
        ):
            raise serializers.ValidationError(
                "Only a super admin can edit an administrator account."
            )

        requested_role = attrs.get(
            "role",
            getattr(target, "role", User.Role.USER),
        )
        if (
            requested_role in (
                User.Role.SUPER_ADMIN,
                User.Role.ADMIN,
            )
            and not actor_is_super_admin
        ):
            raise serializers.ValidationError(
                {
                    "role": (
                        "Only a super admin can assign an "
                        "administrator role."
                    )
                }
            )

        if (
            not actor_is_system_admin
            and requested_role != User.Role.USER
        ):
            raise serializers.ValidationError(
                {
                    "role": (
                        "Delegated user managers can only assign "
                        "the USER system role."
                    )
                }
            )

        requested_custom_role = attrs.get(
            "custom_role",
            getattr(target, "custom_role", None),
        )
        if requested_custom_role and not actor_is_system_admin:
            unauthorized_permissions = [
                permission
                for permission in requested_custom_role.permissions
                if not actor.has_platform_permission(permission)
            ]
            if unauthorized_permissions:
                raise serializers.ValidationError(
                    {
                        "custom_role": (
                            "You cannot assign a role containing "
                            "permissions you do not have."
                        )
                    }
                )

        if not target and not attrs.get("password"):
            raise serializers.ValidationError(
                {"password": "Password is required."}
            )
        return attrs

    def validate_username(self, value):
        queryset = User.objects.filter(username__iexact=value.strip())
        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise serializers.ValidationError(
                "A user with this username already exists."
            )
        return value.strip()

    def validate_email(self, value):
        normalized_email = value.strip().lower()
        if not normalized_email:
            return normalized_email
        queryset = User.objects.filter(email__iexact=normalized_email)
        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise serializers.ValidationError(
                "A user with this email already exists."
            )
        return normalized_email

    def validate_phone(self, value):
        if value in (None, ""):
            return None
        try:
            normalized_phone = normalize_iran_phone(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages[0])
        queryset = User.objects.filter(phone=normalized_phone)
        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise serializers.ValidationError(
                "A user with this phone number already exists."
            )
        return normalized_phone

    def create(self, validated_data):
        password = validated_data.pop("password")
        with transaction.atomic():
            user = User(**validated_data)
            user.set_password(password)
            user.save()
            UserProfile.objects.create(user=user)
            ActivityService.record(
                user,
                UserActivity.Type.CREATE,
                "User account created by administrator",
            )
            return user


    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        if password:
            instance.set_password(password)
        instance.save()
        return instance

    def to_representation(self, instance):
        return UserListSerializer(
            instance,
            context=self.context,
        ).data


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
    country = serializers.CharField(required=False, max_length=100)
    username = serializers.CharField(
        source="user.username",
        read_only=True,
    )
    email = serializers.EmailField(
        source="user.email",
        read_only=True,
    )
    profile_completion = serializers.SerializerMethodField()
    profile_incomplete = serializers.SerializerMethodField()
    profile_complete = serializers.SerializerMethodField()
    missing_profile_fields = serializers.SerializerMethodField()
    personality_result = serializers.SerializerMethodField()
    crm_sync_status = serializers.SerializerMethodField()
    crm_synced_at = serializers.SerializerMethodField()
    wallet_balance_usd = serializers.SerializerMethodField()
    premium_subscription = serializers.SerializerMethodField()

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
            "profile_incomplete",
            "profile_complete",
            "missing_profile_fields",
            "personality_result",
            "crm_sync_status",
            "crm_synced_at",
            "wallet_balance_usd",
            "premium_subscription",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "username",
            "email",
            "profile_completion",
            "profile_incomplete",
            "profile_complete",
            "missing_profile_fields",
            "personality_result",
            "crm_sync_status",
            "crm_synced_at",
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
        return ProfileCompletionService.status(obj.user)["profile_completion"]

    def get_profile_incomplete(self, obj) -> bool:
        return ProfileCompletionService.status(obj.user)["profile_incomplete"]

    def get_profile_complete(self, obj) -> bool:
        return ProfileCompletionService.status(obj.user)["profile_complete"]

    def get_missing_profile_fields(self, obj) -> list[str]:
        return ProfileCompletionService.status(obj.user)["missing_profile_fields"]

    @extend_schema_field({
        "type": "object",
        "nullable": True,
        "properties": {
            "personality_type": {"type": "string"},
            "title": {"type": "string"},
            "subtitle": {"type": "string"},
            "color": {"type": "string"},
            "scores": {
                "type": "object",
                "properties": {
                    name: {"type": "integer"}
                    for name in ("security", "planning", "risk", "discipline", "learning")
                },
            },
            "completed_at": {"type": "string", "format": "date-time"},
            "version": {"type": "integer"},
        },
    })
    def get_personality_result(self, obj):
        assessment = obj.user.financial_personality_assessments.filter(
            is_current=True
        ).first()
        return FinancialPersonalityResultSerializer(assessment).data if assessment else None

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_crm_sync_status(self, obj) -> str | None:
        sync = getattr(obj.user, "crm_contact_sync", None)
        return sync.status if sync else None

    @extend_schema_field(serializers.DateTimeField(allow_null=True))
    def get_crm_synced_at(self, obj):
        sync = getattr(obj.user, "crm_contact_sync", None)
        return sync.synced_at if sync else None

    @extend_schema_field(serializers.DecimalField(max_digits=18, decimal_places=2))
    def get_wallet_balance_usd(self, obj):
        from apps.wallet.services import WalletService

        return format(WalletService.balance_usd_for_user(obj.user), ".2f")

    def get_premium_subscription(self, obj) -> dict:
        from apps.wallet.services import WalletService

        return WalletService.premium_subscription(obj.user)


class CrmContactSyncSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)
    phone = serializers.CharField(source="user.phone", read_only=True)

    class Meta:
        model = CrmContactSync
        fields = (
            "id", "user", "username", "phone", "remote_ulid", "status",
            "attempts", "last_error", "last_response_code", "synced_at",
            "created_at", "updated_at",
        )
        read_only_fields = fields


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
            "plan",
            "price_snapshot_irt",
            "price_snapshot_usd",
            "purchase_idempotency_key",
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
            "plan",
            "price_snapshot_irt",
            "price_snapshot_usd",
            "purchase_idempotency_key",
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
                from apps.wallet.models import UpgradePlan
                from apps.wallet.services import WalletService
                user = self.context["request"].user
                plan = UpgradePlan.objects.select_for_update().get(
                    level=validated_data["requested_level"], active=True
                )
                hold = None
                if plan.price_irt:
                    wallet = WalletService.get_wallet(user)
                    if WalletService.balance_irt(wallet) < plan.price_irt:
                        raise serializers.ValidationError({"plan": "Insufficient wallet balance."})
                    hold = WalletService.post(
                        wallet, plan.price_irt, "UPGRADE_HOLD", credit_wallet=False,
                        counterparty="UPGRADE_HOLD", metadata={"level": plan.level},
                    )
                return UpgradeRequest.objects.create(
                    user=user, plan=plan, price_snapshot_irt=plan.price_irt,
                    hold_ledger_transaction=hold,
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

        try:
            normalized_phone = normalize_iran_phone(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages[0])

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


    def _validate_name(self, value, label):
        value = value.strip()
        if len(value) < 2:
            raise serializers.ValidationError(f"{label} باید حداقل ۲ کاراکتر باشد.")
        return value

    def validate_first_name(self, value):
        return self._validate_name(value, "نام")

    def validate_last_name(self, value):
        return self._validate_name(value, "نام خانوادگی")


class PremiumPurchaseSerializer(serializers.Serializer):
    idempotency_key = serializers.CharField(min_length=8, max_length=120)
    plan_id = serializers.IntegerField(min_value=1, required=False)

    def validate_idempotency_key(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("idempotency_key الزامی است.")
        return value


class PremiumSubscriptionSerializer(serializers.Serializer):
    active = serializers.BooleanField()
    tier = serializers.CharField(allow_null=True)
    plan_id = serializers.IntegerField(allow_null=True)
    purchased_at = serializers.DateTimeField(allow_null=True)


class PremiumPurchaseWalletSerializer(serializers.Serializer):
    balance_usd = serializers.DecimalField(max_digits=18, decimal_places=2)
    display_currency = serializers.CharField()


class PremiumPurchaseResponseSerializer(serializers.Serializer):
    wallet = PremiumPurchaseWalletSerializer()
    upgrade_request = UpgradeRequestSerializer()
    subscription = PremiumSubscriptionSerializer()


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


class BadgeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Badge
        fields = (
            "id", "name", "slug", "description", "icon", "color",
            "is_active", "created_at", "updated_at",
        )
        read_only_fields = ("id", "slug", "created_at", "updated_at")

    def validate_icon(self, value):
        return validate_image_upload(value, max_size_mb=4, file_label="Badge icon")


class UserBadgeSerializer(serializers.ModelSerializer):
    badge = BadgeSerializer(read_only=True)
    badge_id = serializers.PrimaryKeyRelatedField(
        source="badge", queryset=Badge.objects.filter(is_active=True), write_only=True
    )
    awarded_by = serializers.CharField(
        source="awarded_by.username", read_only=True, allow_null=True
    )

    class Meta:
        model = UserBadge
        fields = ("id", "badge", "badge_id", "note", "awarded_by", "awarded_at")
        read_only_fields = ("id", "awarded_by", "awarded_at")


class UserDeviceSerializer(serializers.ModelSerializer):
    is_active = serializers.BooleanField(read_only=True)

    class Meta:
        model = UserDevice
        fields = (
            "id", "device_id", "name", "user_agent", "ip_address",
            "is_active", "last_seen_at", "created_at", "revoked_at",
        )
        read_only_fields = fields


class SecuritySettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = SecuritySettings
        fields = (
            "max_active_devices", "session_lifetime_days", "notify_new_login",
            "require_verified_email_for_sensitive_actions", "maintenance_message", "updated_at",
        )
        read_only_fields = ("updated_at",)

    def validate_max_active_devices(self, value):
        if not 1 <= value <= 20:
            raise serializers.ValidationError("Must be between 1 and 20.")
        return value

    def validate_session_lifetime_days(self, value):
        if not 1 <= value <= 90:
            raise serializers.ValidationError("Must be between 1 and 90.")
        return value

    def validate_country(self, value):
        value = value.strip().upper()
        value = {"IRAN": "IR", "IRAN, ISLAMIC REPUBLIC OF": "IR"}.get(value, value)
        if len(value) != 2 or not value.isalpha():
            raise serializers.ValidationError("Use an ISO-3166 alpha-2 country code.")
        return value

    def validate_income_currency(self, value):
        value = value.strip().upper()
        if len(value) < 3 or len(value) > 10 or not value.isalpha():
            raise serializers.ValidationError("Enter a valid currency code.")
        return value

class OTPRequestSerializer(serializers.Serializer):
    phone = serializers.CharField()

    def validate_phone(self, value):
        try:
            return normalize_iran_phone(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages[0])


class OTPVerifySerializer(OTPRequestSerializer):
    code = serializers.RegexField(r"^\d{4}$", error_messages={"invalid": "کد باید چهار رقم باشد."})


class RegistrationOTPRequestSerializer(OTPRequestSerializer):
    pass


class RegistrationOTPVerifySerializer(RegistrationOTPRequestSerializer):
    code = serializers.RegexField(r"^\d{4}$", error_messages={"invalid": "کد باید چهار رقم باشد."})


class RegistrationOTPUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = (
            "id", "username", "phone", "first_name", "last_name", "email",
            "role", "access_level", "is_active", "is_verified",
        )
        read_only_fields = fields


class RegistrationOTPRequestResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    message = serializers.CharField()
    expires_in = serializers.IntegerField()
    resend_after = serializers.IntegerField()


class RegistrationOTPVerifyResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    access = serializers.CharField()
    refresh = serializers.CharField()
    device_id = serializers.CharField()
    created = serializers.BooleanField()
    profile_incomplete = serializers.BooleanField()
    profile_completion = serializers.IntegerField()
    missing_profile_fields = serializers.ListField(child=serializers.CharField())
    user = RegistrationOTPUserSerializer()


class FinancialPersonalityAnswerSerializer(serializers.Serializer):
    question_id = serializers.IntegerField(min_value=1, max_value=20)
    option_id = serializers.ChoiceField(choices=("a", "b", "c", "d"))


class FinancialPersonalitySubmitSerializer(serializers.Serializer):
    answers = FinancialPersonalityAnswerSerializer(many=True)

    def to_internal_value(self, data):
        if not isinstance(data, dict):
            raise serializers.ValidationError(
                {"non_field_errors": ["بدنه درخواست باید یک شیء JSON باشد."]}
            )
        unexpected_fields = set(data) - {"answers"}
        if unexpected_fields:
            raise serializers.ValidationError(
                {
                    field: ["ارسال این فیلد مجاز نیست؛ نتیجه فقط در سرور محاسبه می‌شود."]
                    for field in sorted(unexpected_fields)
                }
            )
        return super().to_internal_value(data)

    def validate_answers(self, value):
        if len(value) != 20:
            raise serializers.ValidationError("پاسخ هر ۲۰ سؤال الزامی است.")
        question_ids = [answer["question_id"] for answer in value]
        if len(question_ids) != len(set(question_ids)):
            raise serializers.ValidationError("هر سؤال فقط یک پاسخ می‌تواند داشته باشد.")
        if set(question_ids) != set(range(1, 21)):
            raise serializers.ValidationError("شناسه سؤال‌ها باید دقیقاً از ۱ تا ۲۰ باشد.")
        return sorted(value, key=lambda answer: answer["question_id"])


class FinancialPersonalityResultSerializer(serializers.Serializer):
    personality_type = serializers.CharField()
    title = serializers.SerializerMethodField()
    subtitle = serializers.SerializerMethodField()
    color = serializers.SerializerMethodField()
    scores = serializers.SerializerMethodField()
    completed_at = serializers.DateTimeField()
    version = serializers.IntegerField()

    def _metadata(self, obj):
        return FinancialPersonalityService.METADATA[obj.personality_type]

    def get_title(self, obj) -> str:
        return self._metadata(obj)["title"]

    def get_subtitle(self, obj) -> str:
        return self._metadata(obj)["subtitle"]

    def get_color(self, obj) -> str:
        return self._metadata(obj)["color"]

    def get_scores(self, obj) -> dict:
        return {
            "security": obj.score_security,
            "planning": obj.score_planning,
            "risk": obj.score_risk,
            "discipline": obj.score_discipline,
            "learning": obj.score_learning,
        }


class FinancialPersonalityCurrentResponseSerializer(
    FinancialPersonalityResultSerializer
):
    completed = serializers.BooleanField()
