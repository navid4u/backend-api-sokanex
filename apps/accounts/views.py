from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from django.db.models.deletion import ProtectedError
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django_filters.rest_framework import (
    DjangoFilterBackend,
)
from drf_spectacular.utils import (
    extend_schema,
    inline_serializer,
)
from common.throttles import (
    LoginRateThrottle,
    RegisterRateThrottle,
)
from rest_framework import (
    generics,
    serializers,
    status,
)
from rest_framework.filters import SearchFilter
from rest_framework.parsers import (
    FormParser,
    JSONParser,
    MultiPartParser,
)
from rest_framework.permissions import (
    AllowAny,
    IsAuthenticated,
)
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
)

from common.permissions import (
    CanManageRoles,
    CanManageUsers,
    IsAdmin,
    IsEmployee,
    IsSuperAdmin,
    IsTrader,
)

from .filters import UserFilter
from .serializers import (
    BadgeSerializer,
    AdminUpgradeRequestSerializer,
    CustomTokenObtainPairSerializer,
    LogoutSerializer,
    ProfileUpdateSerializer,
    PlatformRoleSerializer,
    RegisterSerializer,
    UserListSerializer,
    AdminUserWriteSerializer,
    UserRoleUpdateSerializer,
    UserAccessLevelUpdateSerializer,
    UserCustomRoleUpdateSerializer,
    UserProfileDetailsSerializer,
    UserSerializer,
    UpgradeRequestReviewSerializer,
    UpgradeRequestSerializer,
    SecuritySettingsSerializer,
    UserBadgeSerializer,
    UserDeviceSerializer,
    OTPRequestSerializer,
    OTPVerifySerializer,
    BrokerConnectionSerializer,
    BrokerConnectionReviewSerializer,
)
from .models import (
    Badge,
    PlatformRole,
    SecuritySettings,
    UpgradeRequest,
    UserBadge,
    UserDevice,
    UserProfile,
    BrokerConnection,
)
from django.utils import timezone
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from .services import UserService
from apps.activity.models import UserActivity
from apps.activity.services import ActivityService
from .authentication import issue_login_tokens
from .otp import OTPService
from common.responses import success_response


User = get_user_model()


class BrokerConnectionView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = BrokerConnectionSerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get(self, request):
        connection = BrokerConnection.objects.filter(user=request.user).first()
        if not connection:
            return Response({
                "status": BrokerConnection.Status.NOT_STARTED,
                "rejection_reason": "", "submitted_at": None, "reviewed_at": None,
                "broker_name": "", "account_number": "", "referral_code": "", "document_url": None,
            })
        return Response(self.get_serializer(connection).data)

    def post(self, request):
        instance = BrokerConnection.objects.filter(user=request.user).first()
        serializer = self.get_serializer(instance, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(
            user=request.user, status=BrokerConnection.Status.PENDING,
            rejection_reason="", reviewed_at=None, reviewed_by=None,
        )
        return Response(serializer.data, status=status.HTTP_200_OK if instance else status.HTTP_201_CREATED)


class BrokerConnectionAdminListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated, IsEmployee]
    serializer_class = BrokerConnectionSerializer
    queryset = BrokerConnection.objects.select_related("user", "reviewed_by")
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ["status", "broker_name"]
    search_fields = ["user__username", "account_number", "referral_code"]


class BrokerConnectionAdminDetailView(generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated, IsEmployee]
    serializer_class = BrokerConnectionSerializer
    queryset = BrokerConnection.objects.select_related("user", "reviewed_by")


class BrokerConnectionReviewView(generics.UpdateAPIView):
    permission_classes = [IsAuthenticated, IsEmployee]
    serializer_class = BrokerConnectionReviewSerializer
    queryset = BrokerConnection.objects.all()
    http_method_names = ["patch", "options"]

    def perform_update(self, serializer):
        serializer.save(reviewed_by=self.request.user, reviewed_at=timezone.now())


class CustomTokenObtainPairView(
    TokenObtainPairView
):
    permission_classes = [
        AllowAny,
    ]
    serializer_class = (
        CustomTokenObtainPairSerializer
    )
    throttle_classes = [
        LoginRateThrottle,
    ]

    @method_decorator(never_cache)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

class ProfileView(APIView):
    permission_classes = [
        IsAuthenticated,
    ]

    parser_classes = [
        JSONParser,
        MultiPartParser,
        FormParser,
    ]

    @extend_schema(
        responses=UserSerializer
    )
    def get(self, request):
        serializer = UserSerializer(
            request.user,
            context={
                "request": request,
            },
        )

        return Response(
            serializer.data
        )

    @extend_schema(
        request=ProfileUpdateSerializer,
        responses=inline_serializer(
            name="ProfileUpdateResponse",
            fields={
                "message": (
                    serializers.CharField()
                ),
                "user": UserSerializer(),
            },
        ),
    )
    def patch(self, request):
        serializer = ProfileUpdateSerializer(
            request.user,
            data=request.data,
            partial=True,
        )

        serializer.is_valid(
            raise_exception=True
        )
        serializer.save()

        ActivityService.record(
            request.user,
            UserActivity.Type.PROFILE_UPDATE,
            "Profile updated",
            ip_address=ActivityService.client_ip(request),
        )

        response_serializer = UserSerializer(
            request.user,
            context={
                "request": request,
            },
        )

        return Response(
            {
                "message": (
                    "Profile updated "
                    "successfully."
                ),
                "user": (
                    response_serializer.data
                ),
            }
        )


class RegisterView(
    generics.CreateAPIView
):
    permission_classes = [
        AllowAny,
    ]
    serializer_class = RegisterSerializer
    throttle_classes = [
        RegisterRateThrottle,
    ]

    @method_decorator(never_cache)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)


class OTPRequestView(APIView):
    permission_classes = [AllowAny]
    serializer_class = OTPRequestSerializer

    @method_decorator(never_cache)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    @extend_schema(request=OTPRequestSerializer)
    def post(self, request):
        serializer = OTPRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        OTPService.request_code(serializer.validated_data["phone"], request)
        return success_response(
            data={"expires_in": 120, "resend_after": 120},
            message="کد تأیید ارسال شد.",
        )


class OTPVerifyView(APIView):
    permission_classes = [AllowAny]
    serializer_class = OTPVerifySerializer

    @method_decorator(never_cache)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    @extend_schema(request=OTPVerifySerializer)
    def post(self, request):
        serializer = OTPVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        phone = serializer.validated_data["phone"]
        OTPService.verify_code(phone, serializer.validated_data["code"])
        user = User.objects.filter(phone=phone, is_active=True).first()
        if not user:
            raise serializers.ValidationError({"code": "کد تأیید نامعتبر یا منقضی است."})
        session = issue_login_tokens(user, request)
        session["user"] = UserSerializer(user, context={"request": request}).data
        return success_response(data=session, message="ورود موفق بود.")

class LogoutView(
    generics.GenericAPIView
):
    permission_classes = [
        IsAuthenticated,
    ]
    serializer_class = LogoutSerializer

    def post(self, request):
        serializer = self.get_serializer(
            data=request.data,
        )

        serializer.is_valid(
            raise_exception=True
        )
        serializer.save()

        ActivityService.record(
            request.user,
            UserActivity.Type.LOGOUT,
            "Account logout",
            ip_address=ActivityService.client_ip(request),
        )

        UserDevice.objects.filter(
            user=request.user,
            refresh_jti=str(serializer.token.get("jti", "")),
        ).update(revoked_at=timezone.now())

        return Response(
            {
                "message": (
                    "Logged out successfully."
                )
            },
            status=status.HTTP_200_OK,
        )


class MyDeviceListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = UserDeviceSerializer
    pagination_class = None

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return UserDevice.objects.none()
        return UserDevice.objects.filter(user=self.request.user)


class RevokeDeviceView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=None, responses=inline_serializer(name="DeviceLogoutResponse", fields={"message": serializers.CharField()}))
    def post(self, request, pk):
        device = get_object_or_404(UserDevice, pk=pk, user=request.user)
        if device.refresh_jti:
            outstanding = OutstandingToken.objects.filter(
                user=request.user, jti=device.refresh_jti
            ).first()
            if outstanding:
                BlacklistedToken.objects.get_or_create(token=outstanding)
        device.revoked_at = timezone.now()
        device.save(update_fields=["revoked_at"])
        return Response({"message": "Device logged out successfully."})


class RevokeOtherDevicesView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=None, responses=inline_serializer(name="OtherDeviceLogoutResponse", fields={"message": serializers.CharField(), "revoked_count": serializers.IntegerField()}))
    def post(self, request):
        current_device_id = request.headers.get("X-Device-ID", "").strip()
        queryset = UserDevice.objects.filter(user=request.user, revoked_at__isnull=True)
        if current_device_id:
            queryset = queryset.exclude(device_id=current_device_id)
        devices = list(queryset)
        jtids = [device.refresh_jti for device in devices if device.refresh_jti]
        for token in OutstandingToken.objects.filter(user=request.user, jti__in=jtids):
            BlacklistedToken.objects.get_or_create(token=token)
        count = queryset.update(revoked_at=timezone.now())
        return Response({"message": "Other devices logged out.", "revoked_count": count})


class BadgeListCreateView(generics.ListCreateAPIView):
    queryset = Badge.objects.all()
    serializer_class = BadgeSerializer
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get_permissions(self):
        permissions = [IsAuthenticated()]
        if self.request.method == "POST":
            permissions.append(CanManageUsers())
        return permissions


class BadgeDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Badge.objects.all()
    serializer_class = BadgeSerializer
    lookup_field = "slug"
    permission_classes = [IsAuthenticated, CanManageUsers]
    parser_classes = [JSONParser, MultiPartParser, FormParser]


class MyBadgeListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = UserBadgeSerializer
    pagination_class = None

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return UserBadge.objects.none()
        return UserBadge.objects.filter(user=self.request.user).select_related("badge", "awarded_by")


class UserBadgeListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated, CanManageUsers]
    serializer_class = UserBadgeSerializer
    pagination_class = None

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return UserBadge.objects.none()
        return UserBadge.objects.filter(user_id=self.kwargs["pk"]).select_related("badge", "awarded_by")

    def perform_create(self, serializer):
        target_user = get_object_or_404(User, pk=self.kwargs["pk"])
        serializer.save(user=target_user, awarded_by=self.request.user)


class UserBadgeDetailView(generics.DestroyAPIView):
    permission_classes = [IsAuthenticated, CanManageUsers]
    queryset = UserBadge.objects.all()
    serializer_class = UserBadgeSerializer


class SecuritySettingsView(generics.RetrieveUpdateAPIView):
    permission_classes = [IsAuthenticated, IsAdmin]
    serializer_class = SecuritySettingsSerializer

    def get_object(self):
        return SecuritySettings.load()

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)


class UserListView(
    generics.ListCreateAPIView
):
    permission_classes = [
        IsAuthenticated,
        CanManageUsers,
    ]

    filter_backends = [
        DjangoFilterBackend,
        SearchFilter,
    ]

    filterset_class = UserFilter

    search_fields = [
        "username",
        "email",
        "first_name",
        "last_name",
    ]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return AdminUserWriteSerializer
        return UserListSerializer

    def get_queryset(self):
        return UserService.list_users()


class UserDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated, CanManageUsers]
    queryset = User.objects.select_related("custom_role")

    def get_serializer_class(self):
        if self.request.method in ("PUT", "PATCH"):
            return AdminUserWriteSerializer
        return UserListSerializer

    def perform_destroy(self, instance):
        actor = self.request.user
        actor_is_super_admin = (
            actor.is_superuser
            or actor.role == User.Role.SUPER_ADMIN
        )
        if instance.pk == actor.pk:
            raise serializers.ValidationError(
                {"user": "You cannot delete your own account."}
            )
        if (
            instance.is_superuser
            or instance.role in (
                User.Role.SUPER_ADMIN,
                User.Role.ADMIN,
            )
        ) and not actor_is_super_admin:
            raise serializers.ValidationError(
                {
                    "user": (
                        "Only a super admin can delete an "
                        "administrator account."
                    )
                }
            )
        try:
            instance.delete()
        except ProtectedError:
            raise serializers.ValidationError(
                {
                    "user": (
                        "This user owns protected records, such as "
                        "academy courses. Reassign those records "
                        "before deleting the account."
                    )
                }
            )


class ToggleUserStatusView(APIView):
    permission_classes = [
        IsAuthenticated,
        IsSuperAdmin,
    ]

    @extend_schema(
        request=None,
        responses=inline_serializer(
            name="UserStatusUpdateResponse",
            fields={
                "message": (
                    serializers.CharField()
                ),
                "user": UserListSerializer(),
            },
        ),
    )
    def post(self, request, pk):
        user = get_object_or_404(
            User,
            pk=pk,
        )

        UserService.toggle_active(
            user,
            request.user,
        )

        return Response(
            {
                "message": (
                    "User status updated."
                ),
                "user": UserListSerializer(
                    user
                ).data,
            }
        )


class UpdateUserRoleView(APIView):
    permission_classes = [
        IsAuthenticated,
        IsSuperAdmin,
    ]

    @extend_schema(
        request=UserRoleUpdateSerializer,
        responses=inline_serializer(
            name="UserRoleUpdateResponse",
            fields={
                "message": (
                    serializers.CharField()
                ),
                "user": UserListSerializer(),
            },
        ),
    )
    def patch(self, request, pk):
        user = get_object_or_404(
            User,
            pk=pk,
        )

        serializer = (
            UserRoleUpdateSerializer(
                data=request.data,
            )
        )

        serializer.is_valid(
            raise_exception=True
        )

        UserService.update_role(
            user,
            serializer.validated_data[
                "role"
            ],
            request.user,
        )

        return Response(
            {
                "message": (
                    "User role updated."
                ),
                "user": UserListSerializer(
                    user
                ).data,
            }
        )


class ProfileDetailsView(APIView):
    permission_classes = [IsAuthenticated]

    def get_object(self, user):
        profile, _ = UserProfile.objects.get_or_create(user=user)
        return profile

    @extend_schema(responses=UserProfileDetailsSerializer)
    def get(self, request):
        serializer = UserProfileDetailsSerializer(
            self.get_object(request.user)
        )
        return Response(serializer.data)

    @extend_schema(
        request=UserProfileDetailsSerializer,
        responses=UserProfileDetailsSerializer,
    )
    def patch(self, request):
        profile = self.get_object(request.user)
        serializer = UserProfileDetailsSerializer(
            profile,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        ActivityService.record(
            request.user,
            UserActivity.Type.PROFILE_UPDATE,
            "Profile details updated",
            ip_address=ActivityService.client_ip(request),
        )
        return Response(serializer.data)


class AdminUserProfileDetailsView(generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated, CanManageUsers]
    serializer_class = UserProfileDetailsSerializer

    def get_object(self):
        user = get_object_or_404(
            User,
            pk=self.kwargs["pk"],
        )
        profile, _ = UserProfile.objects.get_or_create(user=user)
        return profile


class UpdateUserAccessLevelView(APIView):
    permission_classes = [IsAuthenticated, CanManageUsers]

    @extend_schema(
        request=UserAccessLevelUpdateSerializer,
        responses=UserListSerializer,
    )
    def patch(self, request, pk):
        user = get_object_or_404(User, pk=pk)
        serializer = UserAccessLevelUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        UserService.update_access_level(
            user,
            serializer.validated_data["access_level"],
        )
        return Response(
            {
                "message": "User access level updated.",
                "user": UserListSerializer(user).data,
            }
        )


class MyUpgradeRequestListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = UpgradeRequestSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return UpgradeRequest.objects.none()
        return UpgradeRequest.objects.filter(
            user=self.request.user
        ).select_related("reviewed_by")


class UpgradeRequestManagementListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated, CanManageUsers]
    serializer_class = AdminUpgradeRequestSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ["status", "request_type", "requested_level"]
    search_fields = [
        "user__username",
        "user__email",
        "message",
    ]

    def get_queryset(self):
        return UpgradeRequest.objects.select_related(
            "user",
            "reviewed_by",
        )


class UpgradeRequestReviewView(APIView):
    permission_classes = [IsAuthenticated, CanManageUsers]

    @extend_schema(
        request=UpgradeRequestReviewSerializer,
        responses=AdminUpgradeRequestSerializer,
    )
    def patch(self, request, pk):
        upgrade_request = get_object_or_404(UpgradeRequest, pk=pk)
        serializer = UpgradeRequestReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reviewed = UserService.review_upgrade_request(
            upgrade_request,
            reviewed_by=request.user,
            **serializer.validated_data,
        )
        return Response(
            {
                "message": "Upgrade request reviewed.",
                "request": AdminUpgradeRequestSerializer(reviewed).data,
            }
        )


class PlatformRoleListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated, CanManageRoles]
    serializer_class = PlatformRoleSerializer
    queryset = PlatformRole.objects.all()

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class PlatformRoleDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated, CanManageRoles]
    serializer_class = PlatformRoleSerializer
    queryset = PlatformRole.objects.all()
    lookup_field = "slug"


class UpdateUserCustomRoleView(APIView):
    permission_classes = [IsAuthenticated, CanManageUsers]

    @extend_schema(
        request=UserCustomRoleUpdateSerializer,
        responses=UserListSerializer,
    )
    def patch(self, request, pk):
        user = get_object_or_404(User, pk=pk)
        serializer = UserCustomRoleUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        UserService.update_custom_role(
            user,
            serializer.validated_data["custom_role"],
        )
        return Response(
            {
                "message": "User custom role updated.",
                "user": UserListSerializer(user).data,
            }
        )
