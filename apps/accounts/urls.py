from django.urls import path

from .views import (
    LogoutView,
    ProfileView,
    RegisterView,
    ToggleUserStatusView,
    UpdateUserRoleView,
    UserListView,
)


urlpatterns = [
    path(
        "profile/",
        ProfileView.as_view(),
        name="profile",
    ),
    path(
        "register/",
        RegisterView.as_view(),
        name="register",
    ),
    path(
        "logout/",
        LogoutView.as_view(),
        name="logout",
    ),
    path(
        "users/",
        UserListView.as_view(),
        name="user-list",
    ),
    path(
        "users/<int:pk>/toggle/",
        ToggleUserStatusView.as_view(),
        name="user-status-toggle",
    ),
    path(
        "users/<int:pk>/role/",
        UpdateUserRoleView.as_view(),
        name="user-role-update",
    ),
]