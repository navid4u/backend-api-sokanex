from rest_framework.permissions import BasePermission

from apps.accounts.models import User
from common.content_access import user_can_access_gold_content


class CanAccessGoldContent(BasePermission):
    message = "اشتراک طلایی فعال برای دسترسی به این محتوا لازم است."

    def has_permission(self, request, view):
        return request.user.is_authenticated and user_can_access_gold_content(request.user)


class CanAccessBasicContent(BasePermission):
    """General V2 features are Basic+; preserve the legacy Gold gate."""

    message = "برای دسترسی به این بخش، عضویت Basic یا بالاتر لازم است."

    def has_permission(self, request, view):
        from apps.accounts.market_access import has_basic_access, market_access_v2_enabled

        user = request.user
        if not user.is_authenticated:
            return False
        if market_access_v2_enabled():
            return has_basic_access(user)
        self.message = CanAccessGoldContent.message
        return user_can_access_gold_content(user)


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


class CanManageMarketAccess(BasePermission):
    """V2 access-management capability without broadening legacy user admin."""

    def has_permission(self, request, view):
        from apps.accounts.market_access import user_can_manage_market_access

        return user_can_manage_market_access(request.user)


class CanStartMarketTrialCampaign(BasePermission):
    """Only the real super administrator may start a V2 trial campaign."""

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user.is_authenticated
            and (user.is_superuser or user.role == User.Role.SUPER_ADMIN)
        )


class MarketAccessV2Enabled(BasePermission):
    """Keep new management APIs unavailable until the coordinated cutover."""

    def has_permission(self, request, view):
        from apps.accounts.market_access import market_access_v2_enabled

        return market_access_v2_enabled()


class CanAccessMarketV2(BasePermission):
    """For V2 views with `required_market`; fail closed until cutover."""

    def has_permission(self, request, view):
        from apps.accounts.market_access import can_access_market, market_access_v2_enabled

        return bool(
            request.user.is_authenticated
            and market_access_v2_enabled()
            and can_access_market(request.user, getattr(view, "required_market", ""))
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


class CanManageInternalAnalysis(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        if not user.is_authenticated:
            return False
        if user.is_superuser or user.role == User.Role.SUPER_ADMIN:
            return True
        if user.has_platform_permission(User.Permission.INTERNAL_ANALYSIS_MANAGE):
            return True
        return (
            user.role in (User.Role.ADMIN, User.Role.EMPLOYEE)
            and user.has_platform_permission(User.Permission.CONTENT_MANAGE)
        )


class CanManageSupport(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.has_platform_permission(
            User.Permission.SUPPORT_MANAGE
        )


class CanManagePlatform(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.has_platform_permission(
            User.Permission.PLATFORM_SETTINGS_MANAGE
        )


class CanManageAIAssistant(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        return user.is_authenticated and (
            user.has_platform_permission(User.Permission.AI_ASSISTANT_MANAGE)
            or user.has_platform_permission(User.Permission.PLATFORM_SETTINGS_MANAGE)
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
                or user.role == User.Role.SUPER_ADMIN
                or user.has_platform_permission(
                    User.Permission.CONTENT_MANAGE
                )
                or user.has_platform_permission(
                    User.Permission.SIGNAL_REVIEW
                )
                or obj.created_by_id == user.id
            )
        )
