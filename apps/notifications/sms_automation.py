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

from .models import SMSAutomationDelivery, SMSAutomationRule, SMSBroadcast

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
        if not settings.SMS_AUTOMATION_ENABLED:
            return
        rules = _enabled_rules()
        user = with_market_access_relations(User.objects.filter(pk=user_id, is_active=True)).first()
        if not user or not _phone(user):
            return
        rule = _rule(rules, slot, user)
        if not rule:
            return
        SMSAutomationDelivery.objects.get_or_create(
            user=user, event_key=event_key,
            defaults={
                "rule": rule, "event": rule.event, "phone": _phone(user),
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
    now = now or timezone.now()
    rules = _enabled_rules()
    if not any(slot.startswith("TRIAL_") for slot, _ in rules):
        return 0
    count = 0
    grants = (
        TrialGrant.objects.filter(
            invalidated_at__isnull=True, revoked_at__isnull=True,
            started_at__lte=now, ends_at__gt=now, user__is_active=True
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
        if state.granted_markets or not state.trial_active:
            continue
        day = (now - grant.started_at).days + 1
        for slot_no in range(1, 8):
            rule = _rule(rules, f"TRIAL_{slot_no}", user)
            if not rule or rule.trial_day != day:
                continue
            send_date = (grant.started_at + timedelta(days=day - 1)).date()
            due = datetime.combine(send_date, rule.send_time_utc, tzinfo=dt_timezone.utc)
            due = max(due, grant.started_at + timedelta(days=day - 1))
            # Day seven is sent before the exact expiry instant.
            due = min(due, grant.ends_at - timedelta(minutes=1))
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
    if delivery.event == SMSAutomationRule.Event.TRIAL:
        if not market_access_v2_enabled():
            return False
        from apps.accounts.market_access import current_trial_grant

        grant = current_trial_grant(user)
        if not grant or not delivery.event_key.startswith(f"TRIAL:{grant.pk}:"):
            return False
        state = resolve_market_access(user, at=now)
        return state.trial_active and not state.granted_markets
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
                delivery.save(update_fields=("status", "updated_at"))
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
    return sent


def broadcast_candidates(*, tiers, market):
    """V2 tier is backend-derived; never use the obsolete numeric Gold level."""
    users = User.objects.filter(is_active=True, is_superuser=False).exclude(
        role__in=(User.Role.SUPER_ADMIN, User.Role.SUPPORT)
    ).exclude(phone__isnull=True).exclude(phone="")
    for user in with_market_access_relations(users).order_by("pk").iterator(chunk_size=200):
        state = resolve_market_access(user) if market_access_v2_enabled() else None
        memberships = ({state.membership_tier} | ({"ELITE"} if state.is_elite else set())) if state else {f"LEVEL_{user.access_level}"}
        if memberships.isdisjoint(tiers):
            continue
        if market != "ALL" and market not in (state.selected_markets if state else {_preferred_market(user)}):
            continue
        if _phone(user):
            yield user


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
