from django_filters.rest_framework import DjangoFilterBackend
from django.shortcuts import get_object_or_404
from rest_framework import generics
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.permissions import IsAuthenticated

from apps.accounts.models import User
from common.content_access import restrict_queryset_for_user
from common.permissions import CanTeachAcademy

from .models import Course, CourseSession
from .serializers import (
    CourseListSerializer,
    CourseSessionSerializer,
    CourseWriteSerializer,
)


def can_manage_all_academy(user):
    return user.has_platform_permission(
        User.Permission.ACADEMY_MANAGE
    )


def manageable_courses(user):
    queryset = Course.objects.select_related("instructor")
    if can_manage_all_academy(user):
        return queryset
    return queryset.filter(instructor=user)


def visible_courses(user):
    queryset = Course.objects.filter(
        status=Course.Status.PUBLISHED
    ).select_related("instructor")
    return restrict_queryset_for_user(queryset, user)


class CourseListCreateView(generics.ListCreateAPIView):
    filter_backends = [
        DjangoFilterBackend,
        SearchFilter,
        OrderingFilter,
    ]
    filterset_fields = ["status", "instructor"]
    search_fields = ["title", "description", "instructor__username"]
    ordering_fields = ["created_at", "updated_at", "title"]

    def get_permissions(self):
        permissions = [IsAuthenticated()]
        if self.request.method == "POST":
            permissions.append(CanTeachAcademy())
        return permissions

    def get_serializer_class(self):
        if self.request.method == "POST":
            return CourseWriteSerializer
        return CourseListSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Course.objects.none()
        return visible_courses(self.request.user)

    def perform_create(self, serializer):
        serializer.save(instructor=self.request.user)


class CourseManagementListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated, CanTeachAcademy]
    serializer_class = CourseListSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["status"]
    search_fields = ["title", "description"]
    ordering_fields = ["created_at", "updated_at", "title"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Course.objects.none()
        return manageable_courses(self.request.user)


class CourseDetailView(generics.RetrieveUpdateDestroyAPIView):
    lookup_field = "slug"

    def get_permissions(self):
        permissions = [IsAuthenticated()]
        if self.request.method in ("PUT", "PATCH", "DELETE"):
            permissions.append(CanTeachAcademy())
        return permissions

    def get_serializer_class(self):
        if self.request.method in ("PUT", "PATCH"):
            return CourseWriteSerializer
        return CourseListSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Course.objects.none()
        if self.request.method in ("PUT", "PATCH", "DELETE"):
            return manageable_courses(self.request.user)

        visible = visible_courses(self.request.user)
        if self.request.user.has_platform_permission(
            User.Permission.ACADEMY_TEACH
        ):
            return (visible | manageable_courses(self.request.user)).distinct()
        return visible


class CourseSessionListCreateView(generics.ListCreateAPIView):
    serializer_class = CourseSessionSerializer

    def get_permissions(self):
        permissions = [IsAuthenticated()]
        if self.request.method == "POST":
            permissions.append(CanTeachAcademy())
        return permissions

    def get_course(self):
        if hasattr(self, "_course"):
            return self._course
        if self.request.method == "POST":
            queryset = manageable_courses(self.request.user)
        else:
            queryset = visible_courses(self.request.user)
            if self.request.user.has_platform_permission(
                User.Permission.ACADEMY_TEACH
            ):
                queryset = (
                    queryset | manageable_courses(self.request.user)
                ).distinct()
        self._course = get_object_or_404(
            queryset,
            slug=self.kwargs["slug"],
        )
        return self._course

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return CourseSession.objects.none()
        queryset = CourseSession.objects.filter(course=self.get_course())
        if (
            self.request.method == "GET"
            and not manageable_courses(self.request.user).filter(
                pk=self.get_course().pk
            ).exists()
        ):
            queryset = queryset.filter(is_published=True)
        return queryset

    def perform_create(self, serializer):
        serializer.save(course=self.get_course())


class CourseSessionDetailView(
    generics.RetrieveUpdateDestroyAPIView
):
    serializer_class = CourseSessionSerializer

    def get_permissions(self):
        permissions = [IsAuthenticated()]
        if self.request.method in ("PUT", "PATCH", "DELETE"):
            permissions.append(CanTeachAcademy())
        return permissions

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return CourseSession.objects.none()
        if self.request.method in ("PUT", "PATCH", "DELETE"):
            courses = manageable_courses(self.request.user)
            return CourseSession.objects.filter(
                course__in=courses
            ).select_related("course")
        return CourseSession.objects.filter(
            course__in=visible_courses(self.request.user),
            is_published=True,
        ).select_related("course")
