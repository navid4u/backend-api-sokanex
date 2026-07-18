from django.db.models import (
    Exists,
    OuterRef,
    Q,
)

from .models import (
    Notification,
    NotificationRead,
)


class NotificationService:

    @staticmethod
    def visible_notifications(user):
        read_record = (
            NotificationRead.objects.filter(
                notification_id=OuterRef("pk"),
                user=user,
            )
        )

        return (
            Notification.objects.filter(
                Q(recipient=user)
                | Q(
                    recipient__isnull=True,
                    target_role="",
                )
                | Q(
                    recipient__isnull=True,
                    target_role=user.role,
                ),
                is_active=True,
            )
            .select_related("created_by")
            .annotate(
                is_read=Exists(read_record)
            )
            .distinct()
        )

    @staticmethod
    def unread_count(user):
        return (
            NotificationService
            .visible_notifications(user)
            .filter(is_read=False)
            .count()
        )

    @staticmethod
    def mark_as_read(
        notification,
        user,
    ):
        record, _ = (
            NotificationRead.objects.get_or_create(
                notification=notification,
                user=user,
            )
        )

        return record

    @staticmethod
    def mark_all_as_read(user):
        unread_ids = list(
            NotificationService
            .visible_notifications(user)
            .filter(is_read=False)
            .values_list("id", flat=True)
        )

        NotificationRead.objects.bulk_create(
            [
                NotificationRead(
                    notification_id=notification_id,
                    user=user,
                )
                for notification_id in unread_ids
            ],
            ignore_conflicts=True,
        )

        return len(unread_ids)