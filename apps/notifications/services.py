import html
import json
import re
from urllib.parse import urljoin

from django.db.models import (
    Count,
    Exists,
    OuterRef,
    Q,
)
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.html import strip_tags

from .models import (
    Notification,
    NotificationRead,
    NotificationSMSDelivery,
    NotificationPushDelivery,
    WebPushSubscription,
)
from apps.accounts.models import User
from apps.accounts.market_access import has_basic_access, market_access_v2_enabled, users_with_basic_access
from common.sms import PayamitoSMSService, SMSProviderError, render_sms_template
from common.phone import normalize_iran_phone


class NotificationService:

    @staticmethod
    def _notification_url(target_url):
        target_url = (target_url or "").strip()
        if not target_url:
            return ""
        if target_url.startswith("/"):
            base_url = settings.PAYAMITO_NOTIFICATION_LINK_BASE_URL.rstrip("/") + "/"
            return urljoin(base_url, target_url.lstrip("/"))
        return target_url

    @staticmethod
    def _clean_message(message):
        plain_text = html.unescape(strip_tags(message or ""))
        return re.sub(r"\s+", " ", plain_text).strip()

    @staticmethod
    def _without_blank_lines(value):
        return "\n".join(line.strip() for line in value.splitlines() if line.strip())

    @classmethod
    def notification_sms_text(cls, notification):
        title = cls._without_blank_lines(strip_tags(notification.title or "")).strip()
        message = cls._clean_message(notification.message)
        target_url = cls._notification_url(notification.target_url)
        template = settings.PAYAMITO_NOTIFICATION_MESSAGE_TEMPLATE
        max_length = max(int(settings.PAYAMITO_NOTIFICATION_SMS_MAX_LENGTH), 1)

        def render(current_message):
            return cls._without_blank_lines(render_sms_template(
                template,
                title=title,
                message=current_message,
                target_url=target_url,
            ))

        text = render(message)
        if len(text) <= max_length:
            return text

        # Only message is shortened. If title + URL alone exceed the configured
        # ceiling, they remain intact as required.
        fixed_text = render("")
        available = max(max_length - len(fixed_text) - 1, 0)
        if not available:
            return fixed_text
        shortened = message[:available].rstrip()
        if len(shortened) < len(message) and available > 1:
            shortened = shortened[:-1].rstrip() + "…"
        text = render(shortened)
        while len(text) > max_length and shortened:
            shortened = shortened[:-1].rstrip(" …")
            text = render((shortened + "…") if shortened else "")
        return text

    @staticmethod
    def visible_notifications(user):
        read_record = (
            NotificationRead.objects.filter(
                notification_id=OuterRef("pk"),
                user=user,
            )
        )

        role_and_personal = Q(recipient=user) | Q(
            recipient__isnull=True, target_role=user.role
        )
        broadcast = Q(recipient__isnull=True, target_role="")
        if market_access_v2_enabled():
            audience = role_and_personal
            if has_basic_access(user):
                audience |= broadcast
            level_filter = Q()
        else:
            audience = role_and_personal | broadcast
            level_filter = (
                Q(allowed_level_1=True)
                | Q(allowed_level_2=True)
                | Q(allowed_level_3=True)
                | Q(allowed_level_4=True)
                | Q(allowed_level_5=True)
            ) if user.effective_access_level == User.AccessLevel.LEVEL_5 else Q(
                **{f"allowed_level_{user.effective_access_level}": True}
            )

        return (
            Notification.objects.filter(audience, is_active=True)
            .filter(level_filter)
            .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now()))
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
        return NotificationService.audience_users(notification).exclude(
            phone__isnull=True
        ).exclude(phone="")

    @staticmethod
    def audience_users(notification):
        queryset = User.objects.filter(is_active=True)
        if notification.recipient_id:
            return queryset.filter(pk=notification.recipient_id)
        if notification.target_role:
            return queryset.filter(role=notification.target_role)
        if market_access_v2_enabled():
            # V2 broadcasts are available at Basic+; old allowed_levels flags
            # are retained for legacy mode but must not determine V2 recipients.
            return users_with_basic_access(queryset)
        if notification.allowed_levels:
            requested_levels = set(notification.allowed_levels)
            actual_levels = set(requested_levels)
            # Level 2 keeps the same lower-tier notification access as Level 1.
            if 1 in requested_levels:
                actual_levels.add(2)
            matches = Q(access_level__in=actual_levels - {5})
            # Gold users inherit every tier's notifications; expired trials do not.
            if requested_levels:
                matches |= Q(
                    access_level=User.AccessLevel.LEVEL_5,
                    gold_trial_expires_at__gt=timezone.now(),
                )
                matches |= Q(
                    access_level=User.AccessLevel.LEVEL_3,
                    gold_permanent_granted_at__isnull=False,
                )
            return queryset.filter(matches)
        return queryset

    @classmethod
    def queue_push(cls, notification):
        subscriptions = WebPushSubscription.objects.filter(
            is_active=True,
            user__in=cls.audience_users(notification),
            user__is_active=True,
        ).only("pk", "user_id")
        queued = 0
        batch = []
        for subscription in subscriptions.iterator(chunk_size=1000):
            batch.append(NotificationPushDelivery(
                notification_id=notification.pk,
                subscription_id=subscription.pk,
                user_id=subscription.user_id,
            ))
            if len(batch) == 1000:
                NotificationPushDelivery.objects.bulk_create(batch, ignore_conflicts=True)
                queued += len(batch)
                batch = []
        if batch:
            NotificationPushDelivery.objects.bulk_create(batch, ignore_conflicts=True)
            queued += len(batch)
        return queued

    @staticmethod
    def send_pending_push(limit=100):
        if not settings.WEBPUSH_VAPID_PRIVATE_KEY_PATH or not settings.WEBPUSH_VAPID_SUBJECT:
            return 0
        from pywebpush import WebPushException, webpush
        queryset = NotificationPushDelivery.objects.filter(
            status=NotificationPushDelivery.Status.PENDING,
            attempts__lt=5,
            subscription__is_active=True,
            notification__is_active=True,
        ).filter(
            Q(notification__expires_at__isnull=True)
            | Q(notification__expires_at__gt=timezone.now())
        ).select_related("notification", "subscription")
        sent_count = 0
        for delivery in queryset.order_by("created_at")[:limit]:
            delivery.attempts += 1
            notification = delivery.notification
            target_url = notification.target_url.strip()
            if target_url.startswith("/"):
                target_url = urljoin(
                    settings.WEBPUSH_APP_BASE_URL.rstrip("/") + "/",
                    target_url.lstrip("/"),
                )
            payload = {
                "title": notification.title,
                "body": NotificationService._clean_message(notification.message)[:240],
                "url": target_url or settings.WEBPUSH_APP_BASE_URL,
                "icon": settings.WEBPUSH_ICON_URL,
                "tag": f"notification-{notification.pk}",
            }
            try:
                webpush(
                    subscription_info={
                        "endpoint": delivery.subscription.endpoint,
                        "keys": {
                            "p256dh": delivery.subscription.p256dh,
                            "auth": delivery.subscription.auth,
                        },
                    },
                    data=json.dumps(payload, ensure_ascii=False),
                    vapid_private_key=settings.WEBPUSH_VAPID_PRIVATE_KEY_PATH,
                    vapid_claims={"sub": settings.WEBPUSH_VAPID_SUBJECT},
                    ttl=3600,
                    timeout=8,
                )
                delivery.status = NotificationPushDelivery.Status.SENT
                delivery.sent_at = timezone.now()
                delivery.error_code = ""
                sent_count += 1
            except WebPushException as exc:
                code = getattr(exc, "response", None)
                delivery.provider_status_code = (
                    getattr(code, "status_code", None) or getattr(exc, "status_code", None)
                )
                delivery.error_code = f"HTTP_{delivery.provider_status_code}" if delivery.provider_status_code else "PROVIDER_ERROR"
                if delivery.provider_status_code in (404, 410):
                    delivery.subscription.is_active = False
                    delivery.subscription.save(update_fields=("is_active", "last_seen_at"))
                    delivery.status = NotificationPushDelivery.Status.FAILED
                elif delivery.attempts >= 5:
                    delivery.status = NotificationPushDelivery.Status.FAILED
            except Exception as exc:
                delivery.error_code = "DELIVERY_ERROR"
                if delivery.attempts >= 5:
                    delivery.status = NotificationPushDelivery.Status.FAILED
                import logging

                logging.getLogger("apps.notifications.push").warning(
                    "Web push delivery failed delivery_id=%s error_type=%s",
                    delivery.pk, type(exc).__name__,
                )
            delivery.save(update_fields=(
                "attempts", "status", "provider_status_code", "error_code",
                "sent_at", "updated_at",
            ))
        return sent_count

    @classmethod
    def queue_sms(cls, notification):
        if not notification.send_sms:
            return 0
        deliveries = []
        for user in cls.target_users(notification).iterator():
            try:
                phone = normalize_iran_phone(user.phone)
            except (TypeError, ValueError, ValidationError):
                continue
            deliveries.append(NotificationSMSDelivery(
                notification=notification, user=user, phone=phone
            ))
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
                result = PayamitoSMSService.send(
                    delivery.phone,
                    NotificationService.notification_sms_text(delivery.notification),
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
