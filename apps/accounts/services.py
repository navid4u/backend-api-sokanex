from rest_framework.exceptions import ValidationError

from .models import User


class UserService:

    @staticmethod
    def list_users():
        return User.objects.all().order_by("-created_at")

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