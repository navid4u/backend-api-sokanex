"""Durable, opt-in SMS automation. No provider call is made in an HTTP request."""

import hashlib
import logging
import string
from datetime import datetime, time, timedelta, timezone as dt_timezone

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Prefetch
from django.utils import timezone

from apps.accounts.market_access import (
    market_access_v2_enabled, resolve_market_access, with_market_access_relations,
)
from apps.accounts.models import TrialGrant, User
from common.phone import normalize_iran_phone
from common.sms import PayamitoSMSService, SMSProviderError

from .models import (
    Notification, SMSAutomationDelivery, SMSAutomationRule, SMSBroadcast,
    TrialJourneyDispatch,
)
from .services import NotificationService

logger = logging.getLogger(__name__)
ALLOWED_VARIABLES = frozenset({
    "first_name", "last_name", "days_remaining", "support_link",
    "membership_tier", "market_name",
})
TIERS = frozenset({"LEVEL_1", "BASIC", "PRO", "GOLD", "ELITE"})
MARKET_NAMES = {"internal": "بازار داخلی", "forex": "فارکس", "crypto": "کریپتو"}


def validate_template(text):
    if not isinstance(text, str) or not text.strip() or len(text) > 500:
        raise ValidationError("متن پیامک باید بین ۱ تا ۵۰۰ کاراکتر باشد.")
    if "<" in text or ">" in text:
        raise ValidationError("HTML در متن پیامک مجاز نیست.")
    try:
        for _, field, spec, conversion in string.Formatter().parse(text):
            if field is not None and (field not in ALLOWED_VARIABLES or spec or conversion):
                raise ValidationError(f"متغیر مجاز نیست: {field}")
    except ValueError as exc:
        raise ValidationError("ساختار متغیرهای متن پیامک نامعتبر است.") from exc
    return text.strip()


def _phone(user):
    try:
        return normalize_iran_phone(user.phone)
    except (TypeError, ValueError, ValidationError):
        return None


def _preferred_market(user):
    selected = sorted(p.market for p in user.market_preferences_v2.all() if p.market in MARKET_NAMES)
    if user.market_type in selected:
        return user.market_type
    if selected:
        return selected[0]
    return user.market_type if user.market_type in MARKET_NAMES else None


def _rule(rules, slot, user):
    market = _preferred_market(user)
    return rules.get((slot, market)) or rules.get((slot, "ALL"))


def _render(text, user, *, days_remaining=0, market=None):
    state = resolve_market_access(user) if market_access_v2_enabled() else None
    result = validate_template(text).format(
        first_name=user.first_name or "",
        last_name=user.last_name or "",
        days_remaining=days_remaining,
        support_link=settings.SMS_AUTOMATION_SUPPORT_LINK,
        membership_tier=state.membership_tier if state else f"LEVEL_{user.access_level}",
        market_name=MARKET_NAMES.get(market or _preferred_market(user), "سوکانکس"),
    ).strip()
    if not result or len(result) > 500:
        raise ValidationError("متن نهایی پیامک خالی یا بیش از ۵۰۰ کاراکتر است.")
    return result


def _enabled_rules():
    return {(r.slot, r.market): r for r in SMSAutomationRule.objects.filter(enabled=True)}


def queue_event(user_id, slot, event_key):
    """Called after commit; an SMS configuration outage must not break login/signup."""
    try:
        user = with_market_access_relations(User.objects.filter(pk=user_id)).first()
        if not user:
            return
        from .models import TrialJourneyActivation, TrialJourneyDay, TrialJourneyEnrollment
        day_one = TrialJourneyDay.objects.filter(day=1, is_active=True).first()
        journey_owns_welcome = (
            slot == "WELCOME" and settings.TRIAL_JOURNEY_ENABLED
            and TrialJourneyActivation.objects.filter(pk=1).exists()
            and TrialJourneyEnrollment.objects.filter(grant__user_id=user_id).exists()
            and day_one is not None
            and (day_one.market == "ALL" or day_one.market == _preferred_market(user))
        )
        rule = _rule(_enabled_rules(), slot, user)
        phone = _phone(user)
        if not user.is_active:
            reason = "USER_INACTIVE"
        elif journey_owns_welcome:
            reason = "JOURNEY_OWNS_WELCOME"
        elif not settings.SMS_AUTOMATION_ENABLED:
            reason = "AUTOMATION_DISABLED"
        elif not all((settings.PAYAMITO_ENABLED, settings.PAYAMITO_USERNAME,
                      settings.PAYAMITO_API_KEY, settings.PAYAMITO_FROM_NUMBER)):
            reason = "PROVIDER_NOT_CONFIGURED"
        elif not phone:
            reason = "INVALID_OR_MISSING_PHONE"
        elif not rule:
            reason = "RULE_DISABLED_OR_MISSING"
        else:
            reason = None
        if reason:
            SMSAutomationDelivery.objects.get_or_create(
                user=user, event_key=event_key,
                defaults={"event": slot, "phone": phone or "", "text": "",
                          "status": SMSAutomationDelivery.Status.SKIPPED,
                          "failure_code": reason, "scheduled_at": timezone.now()},
            )
            return
        SMSAutomationDelivery.objects.get_or_create(
            user=user, event_key=event_key,
            defaults={
                "rule": rule, "event": rule.event, "phone": phone,
                "text": _render(rule.text, user),
                "scheduled_at": timezone.now() + timedelta(minutes=rule.delay_minutes),
            },
        )
    except Exception:
        logger.exception("sms_automation_queue_failed event=%s user_id=%s", slot, user_id)


def queue_due_trial_messages(*, now=None):
    """Materialize only today's still-eligible trial slot; never backfill old days."""
    if not settings.SMS_AUTOMATION_ENABLED or not market_access_v2_enabled():
        return 0
    from .models import TrialJourneyActivation
    if TrialJourneyActivation.objects.filter(pk=1).exists():
        return 0
    now = now or timezone.now()
    rules = _enabled_rules()
    if not any(slot.startswith("TRIAL_") for slot, _ in rules):
        return 0
    count = 0
    grants = (
        TrialGrant.objects.filter(
            invalidated_at__isnull=True, revoked_at__isnull=True,
            started_at__lte=now, ends_at__gte=now - timedelta(days=1), user__is_active=True
        )
        .select_related("user", "user__market_access_profile")
        .prefetch_related(
            Prefetch(
                "user__trial_grants_v2",
                queryset=TrialGrant.objects.filter(invalidated_at__isnull=True),
                to_attr="_current_trial_grants_v2",
            ),
            "user__market_preferences_v2", "user__market_grants_v2",
        )
    )
    for grant in grants.iterator(chunk_size=200):
        user = grant.user
        if not _phone(user):
            continue
        state = resolve_market_access(user, at=now)
        # A later paid/admin market grant replaces the trial SMS journey.
        if state.granted_markets:
            continue
        day = 7 if now >= grant.ends_at else (now - grant.started_at).days + 1
        if day < 7 and not state.trial_active:
            continue
        for slot_no in range(1, 8):
            rule = _rule(rules, f"TRIAL_{slot_no}", user)
            if not rule or rule.trial_day != day:
                continue
            send_date = (grant.started_at + timedelta(days=day - 1)).date()
            due = datetime.combine(send_date, rule.send_time_utc, tzinfo=dt_timezone.utc)
            due = max(due, grant.started_at + timedelta(days=day - 1))
            if day == 7:
                due = max(due, grant.ends_at)
            if now < due:
                continue
            _, created = SMSAutomationDelivery.objects.get_or_create(
                user=user, event_key=f"TRIAL:{grant.pk}:{rule.slot}",
                defaults={
                    "rule": rule, "event": rule.event, "phone": _phone(user),
                    "text": _render(rule.text, user, days_remaining=max(0, 8 - day)),
                    "scheduled_at": due,
                },
            )
            count += int(created)
    return count


def _still_eligible(delivery, *, now):
    user = delivery.user
    if not user.is_active or _phone(user) != delivery.phone:
        return False
    if delivery.rule_id and not delivery.rule.enabled:
        return False
    if delivery.event == "JOURNEY":
        from .trial_journey import journey_sms_eligible
        return journey_sms_eligible(delivery, now=now)
    if delivery.event == SMSAutomationRule.Event.TRIAL:
        from .models import TrialJourneyActivation
        if TrialJourneyActivation.objects.filter(pk=1).exists():
            return False
        if not market_access_v2_enabled():
            return False
        from apps.accounts.market_access import current_trial_grant

        grant = current_trial_grant(user)
        if not grant or not delivery.event_key.startswith(f"TRIAL:{grant.pk}:"):
            return False
        state = resolve_market_access(user, at=now)
        is_expiry = delivery.event_key.endswith(":TRIAL_7")
        return (now >= grant.ends_at if is_expiry else state.trial_active) and not state.granted_markets
    if delivery.broadcast_id:
        # Broadcast is a frozen, approved snapshot; avoid sending to deleted/disabled users.
        return True
    return True


def send_pending(*, limit=100):
    """Claim before network I/O; ambiguous interrupted sends stay SENDING for review."""
    if not settings.SMS_AUTOMATION_ENABLED or not settings.PAYAMITO_ENABLED:
        return 0
    sent = 0
    for _ in range(limit):
        with transaction.atomic():
            delivery = (
                SMSAutomationDelivery.objects.select_for_update(skip_locked=True)
                # PostgreSQL cannot lock the nullable side of an outer join.
                # Load rule/broadcast lazily after claiming the delivery row.
                .select_related("user")
                .filter(status=SMSAutomationDelivery.Status.PENDING, scheduled_at__lte=timezone.now())
                .order_by("scheduled_at", "pk").first()
            )
            if delivery is None:
                break
            now = timezone.now()
            if not _still_eligible(delivery, now=now):
                delivery.status = SMSAutomationDelivery.Status.SKIPPED
                delivery.failure_code = "NO_LONGER_ELIGIBLE"
                delivery.save(update_fields=("status", "failure_code", "updated_at"))
                continue
            delivery.status = SMSAutomationDelivery.Status.SENDING
            delivery.claimed_at = now
            delivery.attempts += 1
            delivery.save(update_fields=("status", "claimed_at", "attempts", "updated_at"))
        try:
            result = PayamitoSMSService.send(delivery.phone, delivery.text)
        except SMSProviderError as exc:
            # No response body or rendered message is written to application logs.
            delivery.status = SMSAutomationDelivery.Status.FAILED
            delivery.failure_code = str(exc.provider_code or "PROVIDER_UNAVAILABLE")[:80]
            logger.warning("sms_automation_send_failed delivery_id=%s code=%s", delivery.pk, delivery.failure_code)
        except Exception:
            # Unknown failure may occur after the provider accepted the SMS.
            # Preserve SENDING instead of automatically risking a duplicate.
            logger.exception("sms_automation_ambiguous_failure delivery_id=%s", delivery.pk)
            continue
        else:
            delivery.status = SMSAutomationDelivery.Status.SENT
            delivery.sent_at = timezone.now()
            delivery.provider_message_id = str(result.get("message_id", ""))[:100]
            sent += 1
        delivery.save(update_fields=(
            "status", "sent_at", "provider_message_id", "failure_code", "updated_at",
        ))
        if delivery.status == SMSAutomationDelivery.Status.SENT:
            try:
                ensure_sent_sms_notification(delivery)
            except Exception:
                # Provider acceptance is final; a notification failure must
                # never make the SMS retryable or send a duplicate SMS.
                logger.exception("sms_automation_notification_failed delivery_id=%s", delivery.pk)
    return sent


def ensure_sent_sms_notification(delivery):
    """Create a private in-app receipt for a delivered non-OTP SMS exactly once."""
    if delivery.status != SMSAutomationDelivery.Status.SENT:
        return None
    if delivery.event == "JOURNEY":
        existing = TrialJourneyDispatch.objects.filter(
            sms_delivery=delivery, channel=TrialJourneyDispatch.Channel.SMS,
        ).first()
        if existing and TrialJourneyDispatch.objects.filter(
            enrollment=existing.enrollment, day=existing.day,
            channel=TrialJourneyDispatch.Channel.IN_APP,
            notification__isnull=False,
        ).exists():
            return None
    notification, created = Notification.objects.get_or_create(
        source_key=f"SMS_DELIVERY:{delivery.pk}",
        defaults={
            "recipient_id": delivery.user_id,
            "title": "پیامک سوکانکس",
            "message": delivery.text,
            "notification_type": Notification.Type.SYSTEM,
            "show_in_app": True,
            "send_sms": False,
            "target_url": "/notifications",
        },
    )
    if created and delivery.event != "JOURNEY":
        NotificationService.queue_push(notification)
    return notification


def broadcast_candidates(*, tiers, market, diagnostics=None):
    """Use the canonical V2 tier and report sequential exclusions when requested.

    Market targeting follows selected preferences, not grants or the legacy
    single ``market_type``. ``ALL`` adds no market restriction. Elite is an
    independent flag, so selecting it with the base tier is a union.
    """
    users = User.objects.filter(is_superuser=False).exclude(
        role__in=(User.Role.SUPER_ADMIN, User.Role.SUPPORT)
    )
    for user in with_market_access_relations(users).order_by("pk").iterator(chunk_size=200):
        state = resolve_market_access(user) if market_access_v2_enabled() else None
        memberships = ({state.membership_tier} | ({"ELITE"} if state.is_elite else set())) if state else {f"LEVEL_{user.access_level}"}
        if memberships.isdisjoint(tiers):
            continue
        if market != "ALL" and market not in (state.selected_markets if state else {_preferred_market(user)}):
            continue
        if diagnostics is not None:
            diagnostics["matched_count"] += 1
        # These reasons are exclusive and checked in the same order for every
        # candidate. The broadcast remains limited to active, valid phones.
        if not user.is_active:
            reason = "inactive"
        elif not user.phone:
            reason = "missing_phone"
        elif not _phone(user):
            reason = "invalid_phone"
        else:
            yield user
            continue
        if diagnostics is not None:
            diagnostics["excluded_counts"][reason] += 1


def broadcast_digest(user_ids, tiers, market, text):
    source = "|".join((",".join(map(str, user_ids)), ",".join(sorted(tiers)), market, text))
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


@transaction.atomic
def create_broadcast(*, actor, tiers, market, text, expected_count, expected_digest, idempotency_key):
    # Lock a stable row to serialize concurrent broadcasts against each other.
    User.objects.order_by("pk").select_for_update().values_list("pk", flat=True).first()
    prior = SMSBroadcast.objects.filter(idempotency_key=idempotency_key).first()
    if prior:
        if (
            prior.created_by_id == actor.pk and prior.membership_tiers == sorted(tiers)
            and prior.market == market and prior.text == text
            and prior.recipient_count == expected_count
        ):
            return prior, False
        raise ValueError("IDEMPOTENCY_CONFLICT")
    recipients = list(broadcast_candidates(tiers=tiers, market=market))
    ids = [user.pk for user in recipients]
    if not ids or len(ids) != expected_count or broadcast_digest(ids, tiers, market, text) != expected_digest:
        raise ValueError("AUDIENCE_CHANGED")
    campaign = SMSBroadcast.objects.create(
        created_by=actor, idempotency_key=idempotency_key,
        membership_tiers=sorted(tiers), market=market,
        text=text, recipient_count=len(ids),
    )
    now = timezone.now()
    SMSAutomationDelivery.objects.bulk_create((
        SMSAutomationDelivery(
            user=user, broadcast=campaign, event_key=f"BROADCAST:{campaign.pk}",
            event="BROADCAST", phone=_phone(user), text=_render(text, user, market=market),
            scheduled_at=now,
        ) for user in recipients
    ), batch_size=500)
    return campaign, True
