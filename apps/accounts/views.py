from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
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
    IsSuperAdmin,
    IsTrader,
)

from .filters import UserFilter
from .serializers import (
    AdminUpgradeRequestSerializer,
    CustomTokenObtainPairSerializer,
    LogoutSerializer,
    ProfileUpdateSerializer,
    PlatformRoleSerializer,
    RegisterSerializer,
    UserListSerializer,
    UserRoleUpdateSerializer,
    UserAccessLevelUpdateSerializer,
    UserCustomRoleUpdateSerializer,
    UserSerializer,
    UpgradeRequestReviewSerializer,
    UpgradeRequestSerializer,
)
from .models import PlatformRole, UpgradeRequest
from .services import UserService


User = get_user_model()


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

        return Response(
            {
                "message": (
                    "Logged out successfully."
                )
            },
            status=status.HTTP_200_OK,
        )


class UserListView(
    generics.ListAPIView
):
    permission_classes = [
        IsAuthenticated,
        CanManageUsers,
    ]

    serializer_class = UserListSerializer

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

    def get_queryset(self):
        return UserService.list_users()


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
