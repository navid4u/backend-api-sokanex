from django.db.models import Prefetch
from django.shortcuts import get_object_or_404
from rest_framework import generics
from rest_framework.permissions import AllowAny, IsAuthenticated

from common.permissions import CanManageLanding

from .models import LandingPage, LandingSection
from .serializers import (
    LandingPageSerializer,
    LandingSectionSerializer,
    PublicLandingPageSerializer,
)


def get_main_page():
    page, _ = LandingPage.objects.get_or_create(site_key="main")
    return page


class PublicLandingView(generics.RetrieveAPIView):
    permission_classes = [AllowAny]
    serializer_class = PublicLandingPageSerializer

    def get_object(self):
        return get_object_or_404(
            LandingPage.objects.prefetch_related(
                Prefetch(
                    "sections",
                    queryset=LandingSection.objects.filter(
                        is_active=True,
                    ).order_by("display_order", "id"),
                )
            ),
            site_key="main",
            is_active=True,
        )


class LandingPageManagementView(generics.RetrieveUpdateAPIView):
    permission_classes = [IsAuthenticated, CanManageLanding]
    serializer_class = LandingPageSerializer

    def get_object(self):
        return get_main_page()


class LandingSectionListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated, CanManageLanding]
    serializer_class = LandingSectionSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return LandingSection.objects.none()
        return LandingSection.objects.filter(
            page=get_main_page(),
        ).select_related("created_by")

    def perform_create(self, serializer):
        serializer.save(
            page=get_main_page(),
            created_by=self.request.user,
        )


class LandingSectionDetailView(
    generics.RetrieveUpdateDestroyAPIView
):
    permission_classes = [IsAuthenticated, CanManageLanding]
    serializer_class = LandingSectionSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return LandingSection.objects.none()
        return LandingSection.objects.filter(
            page=get_main_page(),
        ).select_related("created_by")
