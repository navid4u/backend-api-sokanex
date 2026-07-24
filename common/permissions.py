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
                request.user.is_superuser
                or request.user.role in [
                    User.Role.EMPLOYEE,
                    User.Role.ADMIN,
                    User.Role.SUPER_ADMIN,
                ]
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
                or user.role in [
                    User.Role.EMPLOYEE,
                    User.Role.ADMIN,
                    User.Role.SUPER_ADMIN,
                ]
                or (
                    user.role == User.Role.TRADER
                    and obj.created_by_id == user.id
                )
            )
        )