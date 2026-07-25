from rest_framework.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import UpgradeRequest, User


class UserService:

    @staticmethod
    def list_users():
        return User.objects.select_related(
            "custom_role"
        ).order_by("-created_at")

    @staticmethod
    def toggle_active(user, performed_by):
        if user.pk == performed_by.pk:
            raise ValidationError(
                {
                    "user": (
                        "You cannot change your own active status."
                    )
                }
            )

        if user.is_superuser:
            raise ValidationError(
                {
                    "user": (
                        "A superuser cannot be deactivated here."
                    )
                }
            )

        user.is_active = not user.is_active

        user.save(
            update_fields=[
                "is_active",
                "updated_at",
            ]
        )

        return user

    @staticmethod
    def update_role(user, role, performed_by):
        if user.pk == performed_by.pk:
            raise ValidationError(
                {
                    "user": "You cannot change your own role."
                }
            )

        if user.is_superuser:
            raise ValidationError(
                {
                    "user": (
                        "A superuser role cannot be changed here."
                    )
                }
            )

        user.role = role

        user.save(
            update_fields=[
                "role",
                "updated_at",
            ]
        )

        return user

    @staticmethod
    def update_access_level(user, access_level):
        user.access_level = access_level
        user.save(update_fields=["access_level", "updated_at"])
        return user

    @staticmethod
    def update_custom_role(user, custom_role):
        user.custom_role = custom_role
        user.save(update_fields=["custom_role", "updated_at"])
        return user

    @staticmethod
    @transaction.atomic
    def review_upgrade_request(
        upgrade_request,
        status,
        reviewed_by,
        admin_note="",
    ):
        locked_request = UpgradeRequest.objects.select_for_update().get(
            pk=upgrade_request.pk
        )
        if locked_request.status != UpgradeRequest.Status.PENDING:
            raise ValidationError(
                {"status": "Only pending requests can be reviewed."}
            )

        locked_request.status = status
        locked_request.admin_note = admin_note.strip()
        locked_request.reviewed_by = reviewed_by
        locked_request.reviewed_at = timezone.now()
        locked_request.save(
            update_fields=[
                "status",
                "admin_note",
                "reviewed_by",
                "reviewed_at",
                "updated_at",
            ]
        )

        if status == UpgradeRequest.Status.APPROVED:
            UserService.update_access_level(
                locked_request.user,
                locked_request.requested_level,
            )

        return locked_request

    @staticmethod
    def get_statistics(user):
        return {
            "signals": user.signals.count(),

            "approved": user.signals.filter(
                status="approved"
            ).count(),

            "pending": user.signals.filter(
                status="pending"
            ).count(),

            "rejected": user.signals.filter(
                status="rejected"
            ).count(),
        }
