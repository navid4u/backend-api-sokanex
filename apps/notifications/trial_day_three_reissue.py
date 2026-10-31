"""Requeue corrected day-three SMS only for the cancelled, unsent cohort."""

import hashlib
from collections import Counter

from django.db import transaction
from django.utils import timezone

from apps.accounts.market_access import (
    current_trial_grant, market_access_v2_enabled, with_market_access_relations,
)
from apps.accounts.market_trial import (
    ONE_TIME_ALL_USERS_RESTART_KEY, TrialCampaignConflict, _require_superadmin,
)
from apps.accounts.models import TrialCampaign, TrialGrant, User

from .models import SMSAutomationDelivery, TrialJourneyDay, TrialJourneyDispatch
from .sms_automation import _phone, _render
from .trial_day_three_cancel import CANCEL_CODE
from .trial_journey import journey_eligible


REISSUE_EVENT = "JOURNEY_DAY3_REISSUE"
REISSUE_PREFIX = "JOURNEY_DAY3_REISSUE"


def _event_key(campaign_id, grant_id):
    return f"{REISSUE_PREFIX}:{campaign_id}:3:{grant_id}"


def _campaign_and_rule():
    campaign = TrialCampaign.objects.get(
        operation_key=ONE_TIME_ALL_USERS_RESTART_KEY,
        status=TrialCampaign.Status.APPLIED,
    )
    rule = TrialJourneyDay.objects.get(day=3, is_active=True)
    if not rule.text.strip():
        raise TrialCampaignConflict("Day-three SMS text is empty; edit and preview it before reissuing.")
    return campaign, rule


def _cancelled_sources(campaign):
    return TrialJourneyDispatch.objects.filter(
        enrollment__grant__campaign=campaign,
        day=3, channel=TrialJourneyDispatch.Channel.SMS,
        sms_delivery__event="JOURNEY",
        sms_delivery__status=SMSAutomationDelivery.Status.SKIPPED,
        sms_delivery__failure_code=CANCEL_CODE,
    )


def _cohort(campaign, rule, *, now):
    source_rows = list(_cancelled_sources(campaign).values_list(
        "enrollment__grant__user_id", "enrollment__grant_id",
        "sms_delivery_id", "sms_delivery__text",
    ))
    sources = {
        user_id: (grant_id, delivery_id, old_text)
        for user_id, grant_id, delivery_id, old_text in source_rows
    }
    if len(source_rows) != len(sources):
        raise TrialCampaignConflict("Duplicate cancelled day-three sources; inspect before reissuing.")
    rows = []
    reasons = Counter()
    digest = hashlib.sha256()
    users = with_market_access_relations(User.objects.filter(pk__in=sources).order_by("pk"))
    for user in users.iterator(chunk_size=200):
        grant_id, source_id, old_text = sources[user.pk]
        current = current_trial_grant(user)
        phone = _phone(user)
        if not user.is_active:
            reason = "USER_INACTIVE"
        elif (not current or current.pk != grant_id
              or not journey_eligible(current, 3, now=now)):
            reason = "TRIAL_NO_LONGER_ELIGIBLE"
        elif not phone:
            reason = "INVALID_OR_MISSING_PHONE"
        else:
            reason = ""
        rendered = _render(
            rule.text, user, days_remaining=5,
            market=rule.market if rule.market != "ALL" else None,
        ) if not reason else ""
        if not reason and rendered == old_text:
            reason = "TEXT_UNCHANGED"
            rendered = ""
        rows.append((user.pk, grant_id, source_id, phone or "", rendered, reason))
        reasons[reason or "PENDING"] += 1
        digest.update(
            f"{user.pk}:{grant_id}:{source_id}:{phone or ''}:{reason}:"
            f"{hashlib.sha256(old_text.encode('utf-8')).hexdigest()}:"
            f"{hashlib.sha256(rendered.encode('utf-8')).hexdigest()};".encode("utf-8")
        )
    if len(rows) != len(sources):
        raise TrialCampaignConflict("A cancelled day-three user is missing; inspect before reissuing.")
    return rows, dict(reasons), digest.hexdigest()


def preview_day_three_reissue(*, actor):
    _require_superadmin(actor)
    campaign, rule = _campaign_and_rule()
    rows, reasons, digest = _cohort(campaign, rule, now=timezone.now())
    return {
        "operation": "DAY_THREE_SMS_REISSUE_20261029",
        "campaign_id": campaign.pk,
        "day": 3,
        "day_three_text": rule.text,
        "day_three_updated_at": rule.updated_at.isoformat(),
        "source_cancelled_count": len(rows),
        "new_pending_count": reasons.get("PENDING", 0),
        "new_skipped_by_reason": {key: value for key, value in reasons.items() if key != "PENDING"},
        "original_day_three_sent_preserved": TrialJourneyDispatch.objects.filter(
            enrollment__grant__campaign=campaign, day=3,
            channel=TrialJourneyDispatch.Channel.SMS,
            sms_delivery__status=SMSAutomationDelivery.Status.SENT,
        ).count(),
        "already_applied": SMSAutomationDelivery.objects.filter(
            event=REISSUE_EVENT,
            event_key__startswith=f"{REISSUE_PREFIX}:{campaign.pk}:3:",
        ).exists(),
        "other_pending_messages": SMSAutomationDelivery.objects.filter(
            status=SMSAutomationDelivery.Status.PENDING,
        ).count(),
        "candidate_digest": digest,
        "template_digest": hashlib.sha256(rule.text.encode("utf-8")).hexdigest(),
    }


@transaction.atomic
def apply_day_three_reissue(*, actor, expected_count, expected_candidate_digest,
                            expected_template_digest):
    _require_superadmin(actor)
    campaign, rule = _campaign_and_rule()
    TrialCampaign.objects.select_for_update().get(pk=campaign.pk)
    rule = TrialJourneyDay.objects.select_for_update().get(pk=rule.pk, is_active=True)
    if SMSAutomationDelivery.objects.filter(
        event=REISSUE_EVENT,
        event_key__startswith=f"{REISSUE_PREFIX}:{campaign.pk}:3:",
    ).exists():
        return {"already_applied": True, "campaign_id": campaign.pk}
    preview = preview_day_three_reissue(actor=actor)
    if (preview["source_cancelled_count"] != expected_count
            or preview["candidate_digest"] != expected_candidate_digest
            or preview["template_digest"] != expected_template_digest):
        raise TrialCampaignConflict("Day-three audience or text changed; preview again.")
    if not expected_count or not preview["new_pending_count"]:
        raise TrialCampaignConflict("No corrected day-three SMS is eligible for reissue.")
    rows, _, fresh_digest = _cohort(campaign, rule, now=timezone.now())
    if fresh_digest != expected_candidate_digest:
        raise TrialCampaignConflict("Day-three audience changed during application.")
    source_ids = [row[2] for row in rows]
    locked = list(SMSAutomationDelivery.objects.select_for_update().filter(
        pk__in=source_ids, status=SMSAutomationDelivery.Status.SKIPPED,
        failure_code=CANCEL_CODE,
    ).values_list("pk", flat=True))
    if len(locked) != expected_count:
        raise TrialCampaignConflict("A cancelled source SMS changed; preview again.")
    now = timezone.now()
    SMSAutomationDelivery.objects.bulk_create((
        SMSAutomationDelivery(
            user_id=user_id, event_key=_event_key(campaign.pk, grant_id),
            event=REISSUE_EVENT, phone=phone, text=rendered,
            status=(SMSAutomationDelivery.Status.SKIPPED if reason else SMSAutomationDelivery.Status.PENDING),
            failure_code=reason, scheduled_at=now,
        )
        for user_id, grant_id, _, phone, rendered, reason in rows
    ), batch_size=500)
    return {
        "already_applied": False,
        "campaign_id": campaign.pk,
        "new_pending": preview["new_pending_count"],
        "new_skipped": expected_count - preview["new_pending_count"],
        "original_day_three_sent_preserved": preview["original_day_three_sent_preserved"],
    }


def day_three_reissue_sms_eligible(delivery, *, now):
    if not market_access_v2_enabled():
        return False
    parts = delivery.event_key.split(":")
    if len(parts) != 4 or parts[0] != REISSUE_PREFIX or parts[2] != "3":
        return False
    try:
        campaign_id, grant_id = int(parts[1]), int(parts[3])
    except ValueError:
        return False
    grant = TrialGrant.objects.select_related("user", "campaign").filter(
        pk=grant_id, campaign_id=campaign_id,
        campaign__operation_key=ONE_TIME_ALL_USERS_RESTART_KEY,
        user_id=delivery.user_id,
    ).first()
    return bool(
        grant and TrialJourneyDay.objects.filter(day=3, is_active=True).exists()
        and _cancelled_sources(grant.campaign).filter(enrollment__grant=grant).exists()
        and journey_eligible(grant, 3, now=now)
    )
