from django.urls import path

from .views import (
    CourseDetailView,
    CourseListCreateView,
    CourseManagementListView,
    CourseSessionDetailView,
    CourseSessionListCreateView,
)


urlpatterns = [
    path(
        "courses/manage/",
        CourseManagementListView.as_view(),
        name="academy-course-management",
    ),
    path(
        "courses/",
        CourseListCreateView.as_view(),
        name="academy-course-list-create",
    ),
    path(
        "courses/<str:slug>/sessions/",
        CourseSessionListCreateView.as_view(),
        name="academy-course-sessions",
    ),
    path(
        "courses/<str:slug>/",
        CourseDetailView.as_view(),
        name="academy-course-detail",
    ),
    path(
        "sessions/<int:pk>/",
        CourseSessionDetailView.as_view(),
        name="academy-session-detail",
    ),
]
