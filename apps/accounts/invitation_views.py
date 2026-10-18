"""Capability-gated invitation management; tokens are not login credentials."""

from django.db.models import Count
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import generics, serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from common.pagination import DefaultPagination
from common.permissions import CanManageUsers

from .invitations import REGISTRATION_URL, create_invitation_link
from .models import InvitationLink, InvitationRegistration


class InvitationLinkCreateSerializer(serializers.Serializer):
    name = serializers.CharField(min_length=1, max_length=150, trim_whitespace=True)

    def validate(self, attrs):
        unexpected = set(self.initial_data) - {"name"}
        if unexpected:
            raise serializers.ValidationError({key: "This field is not accepted." for key in sorted(unexpected)})
        return attrs


class InvitationLinkSerializer(serializers.ModelSerializer):
    registration_url = serializers.SerializerMethodField()
    registrations_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = InvitationLink
        fields = ("id", "name", "registration_url", "registrations_count", "created_at")

    def get_registration_url(self, obj):
        return f"{REGISTRATION_URL}?invite={obj.token}"


class InvitationRegistrationSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(source="user.id", read_only=True)
    full_name = serializers.SerializerMethodField()
    username = serializers.CharField(source="user.username", read_only=True)
    registered_at = serializers.DateTimeField(source="user.date_joined", read_only=True)

    class Meta:
        model = InvitationRegistration
        fields = ("id", "full_name", "username", "registered_at")

    def get_full_name(self, obj):
        return obj.user.get_full_name().strip()


class InvitationLinkListCreateView(generics.ListAPIView):
    permission_classes = (IsAuthenticated, CanManageUsers)
    pagination_class = DefaultPagination
    serializer_class = InvitationLinkSerializer
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = "invitation_manage"

    def get_queryset(self):
        return InvitationLink.objects.annotate(
            registrations_count=Count("registrations")
        ).order_by("-created_at", "-pk")

    @extend_schema(request=InvitationLinkCreateSerializer, responses={201: InvitationLinkSerializer})
    def post(self, request):
        incoming = InvitationLinkCreateSerializer(data=request.data)
        incoming.is_valid(raise_exception=True)
        link = create_invitation_link(name=incoming.validated_data["name"], actor=request.user)
        link.registrations_count = 0
        return Response(self.get_serializer(link).data, status=status.HTTP_201_CREATED)


class InvitationRegistrationListView(generics.ListAPIView):
    permission_classes = (IsAuthenticated, CanManageUsers)
    pagination_class = DefaultPagination
    serializer_class = InvitationRegistrationSerializer

    def get_queryset(self):
        link = get_object_or_404(InvitationLink, pk=self.kwargs["pk"])
        return InvitationRegistration.objects.filter(link=link).select_related("user").order_by("user__date_joined", "user_id")
