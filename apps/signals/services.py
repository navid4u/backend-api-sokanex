from django.db.models import Q

from rest_framework.exceptions import ValidationError

from apps.accounts.models import User

from .models import Signal, SignalStatus


class SignalService:

    @staticmethod
    def trader_signals(user):
        return (
            Signal.objects.filter(created_by=user)
            .select_related("created_by", "approved_by")
            .order_by("-created_at")
        )

    @staticmethod
    def approve(signal, admin):
        if signal.status != SignalStatus.PENDING:
            raise ValidationError(
                {
                    "status": "Only pending signals can be approved."
                }
            )

        signal.status = SignalStatus.APPROVED
        signal.approved_by = admin
        signal.rejection_reason = ""

        signal.save(
            update_fields=[
                "status",
                "approved_by",
                "rejection_reason",
                "updated_at",
            ]
        )

        return signal

    @staticmethod
    def reject(signal, admin, reason=""):
        if signal.status != SignalStatus.PENDING:
            raise ValidationError(
                {
                    "status": "Only pending signals can be rejected."
                }
            )

        reason = reason.strip()

        if not reason:
            raise ValidationError(
                {
                    "reason": "Rejection reason is required."
                }
            )

        signal.status = SignalStatus.REJECTED
        signal.rejection_reason = reason
        signal.approved_by = admin

        signal.save(
            update_fields=[
                "status",
                "approved_by",
                "rejection_reason",
                "updated_at",
            ]
        )

        return signal

    @staticmethod
    def list_signals():
        return (
            Signal.objects.filter(
                status=SignalStatus.APPROVED
            )
            .select_related("created_by")
        )

    @staticmethod
    def accessible_signals(user):
        queryset = Signal.objects.select_related(
            "created_by",
            "approved_by",
        )

        if (
            user.is_superuser
            or user.role in [
                User.Role.EMPLOYEE,
                User.Role.ADMIN,
                User.Role.SUPER_ADMIN,
            ]
        ):
            return queryset

        if user.role == User.Role.TRADER:
            return queryset.filter(
                Q(status=SignalStatus.APPROVED)
                | Q(created_by=user)
            )

        return queryset.filter(
            status=SignalStatus.APPROVED
        )

    @staticmethod
    def create_signal(user, serializer):
        return serializer.save(
            created_by=user,
            status=SignalStatus.PENDING,
        )

    @staticmethod
    def pending_signals():
        return (
            Signal.objects.filter(
                status=SignalStatus.PENDING
            )
            .select_related("created_by")
        )