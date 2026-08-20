from django.db.models import (
    Count,
    Exists,
    OuterRef,
    Q,
)
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import (
    Notification,
    NotificationRead,
    NotificationSMSDelivery,
)
from apps.accounts.models import User
from common.sms import PayamitoPatternService, SMSProviderError


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
            ).filter(
                **{f"allowed_level_{user.access_level}": True}
            ).filter(Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now()))
            .select_related("created_by")
            .annotate(
                is_read=Exists(read_record),
                sms_total=Count("sms_deliveries", distinct=True),
                sms_sent=Count(
                    "sms_deliveries",
                    filter=Q(sms_deliveries__status=NotificationSMSDelivery.Status.SENT),
                    distinct=True,
                ),
                sms_failed=Count(
                    "sms_deliveries",
                    filter=Q(sms_deliveries__status=NotificationSMSDelivery.Status.FAILED),
                    distinct=True,
                ),
                sms_pending=Count(
                    "sms_deliveries",
                    filter=Q(sms_deliveries__status=NotificationSMSDelivery.Status.PENDING),
                    distinct=True,
                ),
            )
            .order_by("-created_at")
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

    @staticmethod
    def target_users(notification):
        queryset = User.objects.filter(is_active=True).exclude(phone__isnull=True).exclude(phone="")
        if notification.recipient_id:
            return queryset.filter(pk=notification.recipient_id)
        if notification.target_role:
            return queryset.filter(role=notification.target_role)
        if notification.allowed_levels:
            return queryset.filter(access_level__in=notification.allowed_levels)
        return queryset

    @classmethod
    def queue_sms(cls, notification):
        if not notification.send_sms:
            return 0
        deliveries = [
            NotificationSMSDelivery(notification=notification, user=user, phone=user.phone)
            for user in cls.target_users(notification).iterator()
        ]
        NotificationSMSDelivery.objects.bulk_create(deliveries, ignore_conflicts=True)
        # Production defaults to a durable outbox processed by the retry command.
        # Inline delivery is useful only for small/local installations and tests.
        if settings.PAYAMITO_SMS_SEND_INLINE:
            transaction.on_commit(lambda: cls.send_pending_sms(notification_id=notification.pk))
        return len(deliveries)

    @staticmethod
    def send_pending_sms(notification_id=None, limit=100):
        queryset = NotificationSMSDelivery.objects.filter(
            status__in=[NotificationSMSDelivery.Status.PENDING, NotificationSMSDelivery.Status.FAILED],
            attempts__lt=settings.PAYAMITO_SMS_RETRY_LIMIT,
        ).select_related("notification")
        if notification_id:
            queryset = queryset.filter(notification_id=notification_id)
        for delivery in queryset.order_by("created_at")[:limit]:
            delivery.attempts += 1
            try:
                result = PayamitoPatternService.send(
                    delivery.phone,
                    settings.PAYAMITO_NOTIFICATION_BODY_ID,
                    [delivery.notification.title],
                )
                delivery.status = NotificationSMSDelivery.Status.SENT
                delivery.provider_message_id = result["message_id"]
                delivery.provider_code = ""
                delivery.error_message = ""
                delivery.sent_at = timezone.now()
            except SMSProviderError as exc:
                delivery.status = NotificationSMSDelivery.Status.FAILED
                delivery.provider_code = exc.provider_code
                delivery.error_message = str(exc)[:500]
            delivery.save(update_fields=[
                "attempts", "status", "provider_message_id", "provider_code",
                "error_message", "sent_at", "updated_at",
            ])
