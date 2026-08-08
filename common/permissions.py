from rest_framework.permissions import BasePermission

from apps.accounts.models import User


class IsTrader(BasePermission):
    """
    Trader or super admin can access.
    """

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and (
                request.user.has_platform_permission(
                    User.Permission.SIGNAL_SUBMIT
                )
            )
        )


class IsAdmin(BasePermission):
    """
    Admin or super admin can access.
    """

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and (
                request.user.is_superuser
                or request.user.role in [
                    User.Role.ADMIN,
                    User.Role.SUPER_ADMIN,
                ]
            )
        )


class CanManageUsers(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.has_platform_permission(
                User.Permission.USER_MANAGE
            )
        )


class CanManageRoles(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.has_platform_permission(
                User.Permission.ROLE_MANAGE
            )
        )


class CanTeachAcademy(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and (
                request.user.has_platform_permission(
                    User.Permission.ACADEMY_TEACH
                )
                or request.user.has_platform_permission(
                    User.Permission.ACADEMY_MANAGE
                )
            )
        )


class CanReviewSignals(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.has_platform_permission(
                User.Permission.SIGNAL_REVIEW
            )
        )


class CanManageLive(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.has_platform_permission(User.Permission.LIVE_MANAGE)
        )


class CanManageLanding(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.has_platform_permission(
                User.Permission.LANDING_MANAGE
            )
        )


class IsSuperAdmin(BasePermission):
    """
    Only super admin can access.
    """

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and (
                request.user.is_superuser
                or request.user.role
                == User.Role.SUPER_ADMIN
            )
        )


class IsEmployee(BasePermission):
    """
    Employee, admin, or super admin can access.
    """

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and (
                request.user.has_platform_permission(
                    User.Permission.CONTENT_MANAGE
                )
            )
        )


class IsSignalOwnerOrEmployee(BasePermission):
    """
    Allows the signal owner or authorized employees
    to update and delete a signal.
    """

    def has_object_permission(
        self,
        request,
        view,
        obj,
    ):
        user = request.user

        return (
            user.is_authenticated
            and (
                user.is_superuser
                or user.has_platform_permission(
                    User.Permission.CONTENT_MANAGE
                )
                or user.has_platform_permission(
                    User.Permission.SIGNAL_REVIEW
                )
                or obj.created_by_id == user.id
            )
        )
