"""Seven-day V2 trial journey. Configuration alone never enables delivery.

The operator must explicitly activate the cohort and turn on the deployment
kill switch. Only grants enrolled after that activation are processed.
"""

from datetime import datetime, timedelta, timezone as dt_timezone
import logging

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from apps.accounts.market_access import current_trial_grant, market_access_v2_enabled, resolve_market_access
from apps.accounts.models import TrialGrant, User

from .models import (
    Notification, SMSAutomationDelivery, SMSAutomationRule,
    TrialJourneyActivation, TrialJourneyConfigAudit, TrialJourneyDay,
    TrialJourneyDispatch, TrialJourneyEnrollment, WebPushSubscription,
)
from .services import NotificationService
from .sms_automation import _phone, _render, validate_template

logger = logging.getLogger(__name__)


class TrialJourneyDaySerializer(serializers.ModelSerializer):
    class Meta:
        model = TrialJourneyDay
        fields = ("day", "text", "is_active", "send_time_utc", "market", "in_app_enabled", "push_enabled")
        extra_kwargs = {
            "day": {"required": True, "validators": []}, "text": {"required": True, "allow_blank": True},
            "is_active": {"required": True}, "send_time_utc": {"required": True},
            "market": {"required": True}, "in_app_enabled": {"required": True},
            "push_enabled": {"required": True},
        }

    def to_internal_value(self, data):
        if not isinstance(data, dict):
            raise serializers.ValidationError("Each day must be an object.")
        unexpected = set(data) - set(self.fields)
        if unexpected:
            raise serializers.ValidationError({key: "Unknown field." for key in sorted(unexpected)})
        return super().to_internal_value(data)

    def validate_day(self, value):
        if value not in range(1, 8):
            raise serializers.ValidationError("Day must be between 1 and 7.")
        return value

    def validate(self, attrs):
        text = attrs["text"]
        if attrs["is_active"] or text:
            try:
                attrs["text"] = validate_template(text)
            except DjangoValidationError as exc:
                raise serializers.ValidationError({"text": exc.messages}) from exc
        return attrs


class TrialJourneySerializer(serializers.Serializer):
    days = TrialJourneyDaySerializer(many=True, allow_empty=False)

    def validate(self, attrs):
        unexpected = set(self.initial_data) - {"days"}
        if unexpected:
            raise serializers.ValidationError({key: "Unknown field." for key in sorted(unexpected)})
        values = attrs["days"]
        if len(values) != 7 or {day["day"] for day in values} != set(range(1, 8)):
            raise serializers.ValidationError({"days": "Provide each day from 1 through 7 exactly once."})
        return attrs


def journey_payload():
    return {"days": TrialJourneyDaySerializer(TrialJourneyDay.objects.order_by("day"), many=True).data}


@transaction.atomic
def update_journey(*, actor, days):
    current = {row.day: row for row in TrialJourneyDay.objects.select_for_update().all()}
    before = list(journey_payload()["days"])
    for values in days:
        day = values["day"]
        obj = current.get(day) or TrialJourneyDay(day=day)
        for key, value in values.items():
            setattr(obj, key, value)
        obj.save()
    after = list(journey_payload()["days"])
    if before != after:
        TrialJourneyConfigAudit.objects.create(actor=actor, before=before, after=after)
    return {"days": after}


def enroll_new_grants(*, user_ids, campaign, started_at):
    """Called inside the grant transaction; creates a durable entry point."""
    activation = TrialJourneyActivation.objects.filter(pk=1).first()
    if activation is None or started_at < activation.activated_at:
        return 0
    grant_ids = TrialGrant.objects.filter(
        campaign=campaign, user_id__in=user_ids, started_at=started_at,
    ).values_list("pk", flat=True)
    return len(TrialJourneyEnrollment.objects.bulk_create(
        (TrialJourneyEnrollment(grant_id=grant_id) for grant_id in grant_ids),
        ignore_conflicts=True, batch_size=500,
    ))


def scheduled_at(grant, rule):
    if rule.day == 1:
        return grant.started_at
    base = grant.ends_at if rule.day == 7 else grant.started_at + timedelta(days=rule.day - 1)
    candidate = datetime.combine(base.date(), rule.send_time_utc, tzinfo=dt_timezone.utc)
    if rule.day == 7 and candidate < base:
        candidate += timedelta(days=1)
    return max(base, candidate)


def journey_eligible(grant, day, *, now):
    current = current_trial_grant(grant.user)
    if (not market_access_v2_enabled() or not grant.user.is_active or grant.revoked_at
            or grant.invalidated_at or current is None or current.pk != grant.pk):
        return False
    state = resolve_market_access(grant.user, at=now)
    if state.granted_markets:
        return False
    return (grant.started_at <= now < grant.ends_at and state.trial_active) if day < 7 else now >= grant.ends_at


def journey_sms_eligible(delivery, *, now):
    try:
        _, grant_id, day_string, channel = delivery.event_key.split(":")
        grant_id, day = int(grant_id), int(day_string)
    except (ValueError, TypeError):
        return False
    if channel != "SMS" or not settings.TRIAL_JOURNEY_ENABLED:
        return False
    activation = TrialJourneyActivation.objects.filter(pk=1).first()
    rule = TrialJourneyDay.objects.filter(day=day, is_active=True).first()
    grant = TrialGrant.objects.select_related("user").filter(pk=grant_id).first()
    if not activation or not rule or not grant or grant.started_at < activation.activated_at:
        return False
    if delivery.scheduled_at > now or _phone(grant.user) != delivery.phone:
        return False
    return journey_eligible(grant, day, now=now)


def _dispatch_channel(enrollment, rule, *, now, channel):
    grant = enrollment.grant
    user = grant.user
    if TrialJourneyDispatch.objects.filter(enrollment=enrollment, day=rule.day, channel=channel).exists():
        return False
    if not journey_eligible(grant, rule.day, now=now):
        return False
    # A day's market labels its message, not the audience. Every enrolled user
    # receives each active day regardless of their selected or preferred market.
    rendered = _render(rule.text, user, days_remaining=(0 if rule.day == 7 else 8 - rule.day),
                       market=rule.market if rule.market != "ALL" else None)
    if channel == TrialJourneyDispatch.Channel.SMS:
        phone = _phone(user)
        provider_ready = all((settings.PAYAMITO_ENABLED, settings.PAYAMITO_USERNAME,
                              settings.PAYAMITO_API_KEY, settings.PAYAMITO_FROM_NUMBER))
        if not phone or not settings.SMS_AUTOMATION_ENABLED or not provider_ready:
            reason = ("INVALID_OR_MISSING_PHONE" if not phone else
                      "AUTOMATION_DISABLED" if not settings.SMS_AUTOMATION_ENABLED else
                      "PROVIDER_NOT_CONFIGURED")
            SMSAutomationDelivery.objects.get_or_create(
                user=user, event_key=f"JOURNEY:{grant.pk}:{rule.day}:SMS",
                defaults={"event": "JOURNEY", "phone": phone or "", "text": "",
                          "status": SMSAutomationDelivery.Status.SKIPPED,
                          "failure_code": reason,
                          "scheduled_at": scheduled_at(grant, rule)},
            )
            TrialJourneyDispatch.objects.create(enrollment=enrollment, day=rule.day,
                                                channel=channel, status="SKIPPED")
            return False
        delivery, _ = SMSAutomationDelivery.objects.get_or_create(
            user=user, event_key=f"JOURNEY:{grant.pk}:{rule.day}:SMS",
            defaults={"event": "JOURNEY", "phone": phone, "text": rendered,
                      "scheduled_at": scheduled_at(grant, rule)},
        )
        TrialJourneyDispatch.objects.create(enrollment=enrollment, day=rule.day,
                                            channel=channel, sms_delivery=delivery)
        return True
    if channel == TrialJourneyDispatch.Channel.IN_APP:
        notification = Notification.objects.create(
            recipient=user, title="سوکانکس", message=rendered,
            notification_type=Notification.Type.SYSTEM, send_sms=False,
            show_in_app=True, target_url="/dashboard",
        )
        TrialJourneyDispatch.objects.create(enrollment=enrollment, day=rule.day,
                                            channel=channel, notification=notification)
        return True
    if channel == TrialJourneyDispatch.Channel.PUSH:
        in_app = TrialJourneyDispatch.objects.filter(
            enrollment=enrollment, day=rule.day, channel="IN_APP",
        ).select_related("notification").first()
        notification = in_app.notification if in_app else None
        if not WebPushSubscription.objects.filter(user=user, is_active=True).exists():
            TrialJourneyDispatch.objects.create(enrollment=enrollment, day=rule.day,
                                                channel=channel, status="SKIPPED")
            return False
        if notification is None:
            notification = Notification.objects.create(
                recipient=user, title="سوکانکس", message=rendered,
                notification_type=Notification.Type.SYSTEM, send_sms=False,
                show_in_app=False, target_url="/dashboard",
            )
        NotificationService.queue_push(notification)
        TrialJourneyDispatch.objects.create(enrollment=enrollment, day=rule.day,
                                            channel=channel, notification=notification)
        return True
    return False


def queue_trial_day_one(grant_id):
    """After-commit fast path; the periodic worker remains the durable recovery path."""
    if not settings.TRIAL_JOURNEY_ENABLED or not market_access_v2_enabled():
        return
    try:
        with transaction.atomic():
            enrollment = TrialJourneyEnrollment.objects.select_related("grant__user").filter(
                grant_id=grant_id,
            ).first()
            rule = TrialJourneyDay.objects.filter(day=1, is_active=True).first()
            if not enrollment or not rule:
                return
            User.objects.select_for_update().get(pk=enrollment.grant.user_id)
            now = timezone.now()
            for channel, enabled in (
                (TrialJourneyDispatch.Channel.SMS, True),
                (TrialJourneyDispatch.Channel.IN_APP, rule.in_app_enabled),
                (TrialJourneyDispatch.Channel.PUSH, rule.push_enabled),
            ):
                if enabled:
                    with transaction.atomic():
                        _dispatch_channel(enrollment, rule, now=now, channel=channel)
    except Exception:
        logger.exception("trial_day_one_queue_failed grant_id=%s", grant_id)


def queue_due_trial_journey(*, now=None):
    """Process current day only. No retrospective blast on activation/restart."""
    if not settings.TRIAL_JOURNEY_ENABLED or not market_access_v2_enabled():
        return 0
    activation = TrialJourneyActivation.objects.filter(pk=1).first()
    if activation is None:
        return 0
    now = now or timezone.now()
    rules = {row.day: row for row in TrialJourneyDay.objects.filter(is_active=True)}
    count = 0
    enrollment_ids = TrialJourneyEnrollment.objects.filter(
        grant__started_at__gte=max(activation.activated_at, now - timedelta(days=9)),
        grant__started_at__lte=now,
    ).order_by("pk").values_list("pk", flat=True)
    for enrollment_id in enrollment_ids.iterator(chunk_size=200):
        enrollment_start = TrialJourneyEnrollment.objects.filter(pk=enrollment_id).values_list(
            "grant__started_at", flat=True,
        ).first()
        if enrollment_start is None:
            continue
        day = min(7, (now - enrollment_start).days + 1)
        rule = rules.get(day)
        if rule is None:
            continue
        with transaction.atomic():
            # Same user-row lock order as access reviews and trial creation.
            user_id = TrialJourneyEnrollment.objects.filter(pk=enrollment_id).values_list("grant__user_id", flat=True).first()
            if user_id is None:
                continue
            User.objects.select_for_update().get(pk=user_id)
            enrollment = TrialJourneyEnrollment.objects.select_for_update().select_related("grant__user").get(pk=enrollment_id)
            due = scheduled_at(enrollment.grant, rule)
            end = (enrollment.grant.started_at + timedelta(days=rule.day)
                   if rule.day < 7 else due + timedelta(days=1))
            if not due <= now < end:
                continue
            for channel, enabled in (
                (TrialJourneyDispatch.Channel.SMS, True),
                (TrialJourneyDispatch.Channel.IN_APP, rule.in_app_enabled),
                (TrialJourneyDispatch.Channel.PUSH, rule.push_enabled),
            ):
                if enabled:
                    try:
                        # Independent savepoints keep an in-app/push failure from
                        # rolling back a successfully queued SMS (and vice versa).
                        with transaction.atomic():
                            count += int(_dispatch_channel(enrollment, rule, now=now, channel=channel))
                    except Exception:
                        logger.exception(
                            "trial_journey_channel_failed enrollment_id=%s day=%s channel=%s",
                            enrollment.pk, rule.day, channel,
                        )
    return count
