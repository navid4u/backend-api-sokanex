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
                request.user.is_superuser
                or request.user.role in [
                    User.Role.TRADER,
                    User.Role.SUPER_ADMIN,
                ]
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


class IsSuperAdmin(BasePermission):
    """
    Only super admin can access.
    """

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and (
                request.user.is_superuser
                or request.user.role == User.Role.SUPER_ADMIN
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
                request.user.is_superuser
                or request.user.role in [
                    User.Role.EMPLOYEE,
                    User.Role.ADMIN,
                    User.Role.SUPER_ADMIN,
                ]
            )
        )