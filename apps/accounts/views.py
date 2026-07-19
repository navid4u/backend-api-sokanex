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
    IsAdmin,
    IsSuperAdmin,
    IsTrader,
)

from .filters import UserFilter
from .serializers import (
    CustomTokenObtainPairSerializer,
    LogoutSerializer,
    ProfileUpdateSerializer,
    RegisterSerializer,
    UserListSerializer,
    UserRoleUpdateSerializer,
    UserSerializer,
)
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
        IsSuperAdmin,
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