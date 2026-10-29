"""One-off, audited-in-place resend of the corrected day-one SMS.

This does not restart a TrialGrant or alter the remaining seven-day journey.
The original delivery rows remain in history; only unsent PENDING originals
are superseded. A fixed event key makes the reissue idempotent.
"""

import hashlib
from collections import Counter

from django.db import transaction
from django.utils import timezone

from apps.accounts.market_access import (
    current_trial_grant, market_access_v2_enabled, resolve_market_access, with_market_access_relations,
)
from apps.accounts.market_trial import ONE_TIME_ALL_USERS_RESTART_KEY, TrialCampaignConflict, _require_superadmin
from apps.accounts.models import TrialCampaign, TrialGrant, User

from .models import SMSAutomationDelivery, TrialJourneyActivation, TrialJourneyDay
from .sms_automation import _phone, _render
from .trial_journey import journey_eligible


REISSUE_EVENT = "JOURNEY_REISSUE"
REISSUE_PREFIX = "JOURNEY_REISSUE"
SUPERSEDED_CODE = "DAY1_REISSUED_WITH_NEW_TEXT"


def _event_key(campaign_id, grant_id):
    return f"{REISSUE_PREFIX}:{campaign_id}:1:{grant_id}"


def _campaign_and_rule():
    campaign = TrialCampaign.objects.get(
        operation_key=ONE_TIME_ALL_USERS_RESTART_KEY,
        status=TrialCampaign.Status.APPLIED,
    )
    rule = TrialJourneyDay.objects.get(day=1, is_active=True)
    if not TrialJourneyActivation.objects.filter(pk=1, activated_at__lte=timezone.now()).exists():
        raise TrialCampaignConflict("Trial Journey is not activated.")
    return campaign, rule


def _cohort(campaign, rule, *, now):
    """Build a PII-free fingerprint and per-user rendered delivery snapshots."""
    grants = dict(TrialGrant.objects.filter(campaign=campaign).values_list("user_id", "pk"))
    users = with_market_access_relations(User.objects.filter(pk__in=grants).order_by("pk"))
    digest = hashlib.sha256()
    rows = []
    reasons = Counter()
    for user in users.iterator(chunk_size=200):
        grant_id = grants[user.pk]
        current = current_trial_grant(user)
        phone = _phone(user)
        state = resolve_market_access(user, at=now) if user.is_active else None
        if not user.is_active:
            reason = "USER_INACTIVE"
        elif (not current or current.pk != grant_id or current.revoked_at
              or not current.started_at <= now < current.ends_at
              or not state.trial_active or state.granted_markets):
            reason = "TRIAL_NO_LONGER_ELIGIBLE"
        elif not phone:
            reason = "INVALID_OR_MISSING_PHONE"
        else:
            reason = ""
        rendered = _render(rule.text, user, days_remaining=7,
                           market=rule.market if rule.market != "ALL" else None) if not reason else ""
        rows.append((user.pk, grant_id, phone or "", rendered, reason))
        reasons[reason or "PENDING"] += 1
        digest.update(f"{user.pk}:{grant_id}:{phone or ''}:{reason};".encode("utf-8"))
    return rows, dict(reasons), digest.hexdigest()


def preview_day_one_reissue(*, actor):
    _require_superadmin(actor)
    campaign, rule = _campaign_and_rule()
    now = timezone.now()
    rows, reasons, candidate_digest = _cohort(campaign, rule, now=now)
    old_keys = [f"JOURNEY:{grant_id}:1:SMS" for _, grant_id, _, _, _ in rows]
    originals = SMSAutomationDelivery.objects.filter(event="JOURNEY", event_key__in=old_keys)
    old_statuses = Counter(originals.values_list("status", flat=True))
    old_records = {user_id: (status, text) for user_id, status, text in
                   originals.values_list("user_id", "status", "text")}
    changed_count = sum(
        bool(rendered and old_records.get(user_id, (None, ""))[1]
             and old_records[user_id][1] != rendered)
        for user_id, _, _, rendered, _ in rows
    )
    duplicate_recipients = sum(
        bool(rendered and old_records.get(user_id, (None, ""))[0] == SMSAutomationDelivery.Status.SENT)
        for user_id, _, _, rendered, _ in rows
    )
    return {
        "operation": "DAY_ONE_SMS_REISSUE_20261029",
        "campaign_id": campaign.pk,
        "day_one_text": rule.text,
        "day_one_updated_at": rule.updated_at.isoformat(),
        "already_applied": SMSAutomationDelivery.objects.filter(
            event=REISSUE_EVENT, event_key__startswith=f"{REISSUE_PREFIX}:{campaign.pk}:1:",
        ).exists(),
        "cohort_size": len(rows),
        "new_pending_count": reasons.get("PENDING", 0),
        "new_skipped_by_reason": {key: value for key, value in reasons.items() if key != "PENDING"},
        "original_status_counts": dict(old_statuses),
        "original_pending_to_supersede": old_statuses.get(SMSAutomationDelivery.Status.PENDING, 0),
        "other_pending_messages_outside_this_campaign": SMSAutomationDelivery.objects.filter(
            status=SMSAutomationDelivery.Status.PENDING,
        ).exclude(event_key__in=old_keys).count(),
        "original_sent_will_receive_second_sms": duplicate_recipients,
        "rendered_text_changed_from_original_count": changed_count,
        "candidate_digest": candidate_digest,
        "template_digest": hashlib.sha256(rule.text.encode("utf-8")).hexdigest(),
    }


@transaction.atomic
def apply_day_one_reissue(*, actor, expected_pending_count, expected_candidate_digest, expected_template_digest):
    _require_superadmin(actor)
    campaign, rule = _campaign_and_rule()
    # Serializes competing applications without modifying the trial itself.
    TrialCampaign.objects.select_for_update().get(pk=campaign.pk)
    rule = TrialJourneyDay.objects.select_for_update().get(pk=rule.pk, is_active=True)
    if SMSAutomationDelivery.objects.filter(
        event=REISSUE_EVENT, event_key__startswith=f"{REISSUE_PREFIX}:{campaign.pk}:1:",
    ).exists():
        return {"already_applied": True, "campaign_id": campaign.pk}
    preview = preview_day_one_reissue(actor=actor)
    if (preview["candidate_digest"] != expected_candidate_digest
            or preview["template_digest"] != expected_template_digest
            or preview["original_pending_to_supersede"] != expected_pending_count):
        raise TrialCampaignConflict("Reissue audience, template, or original pending count changed; preview again.")
    if preview["original_status_counts"].get(SMSAutomationDelivery.Status.SENDING, 0):
        raise TrialCampaignConflict("An original SMS is SENDING; reconcile it before reissuing.")
    if preview["rendered_text_changed_from_original_count"] == 0:
        raise TrialCampaignConflict("The day-one SMS text has not changed from the original deliveries.")

    now = timezone.now()
    rows, _, fresh_digest = _cohort(campaign, rule, now=now)
    if fresh_digest != expected_candidate_digest:
        raise TrialCampaignConflict("Reissue audience changed during application; preview again.")
    old_keys = [f"JOURNEY:{grant_id}:1:SMS" for _, grant_id, _, _, _ in rows]
    old_deliveries = SMSAutomationDelivery.objects.select_for_update().filter(
        event="JOURNEY", event_key__in=old_keys,
    )
    if old_deliveries.filter(status=SMSAutomationDelivery.Status.SENDING).exists():
        raise TrialCampaignConflict("An original SMS is SENDING; reconcile it before reissuing.")
    superseded = old_deliveries.filter(status=SMSAutomationDelivery.Status.PENDING).update(
        status=SMSAutomationDelivery.Status.SKIPPED,
        failure_code=SUPERSEDED_CODE,
        updated_at=now,
    )
    if superseded != expected_pending_count:
        raise TrialCampaignConflict("Original pending count changed during application; preview again.")

    SMSAutomationDelivery.objects.bulk_create((
        SMSAutomationDelivery(
            user_id=user_id, event_key=_event_key(campaign.pk, grant_id),
            event=REISSUE_EVENT, phone=phone, text=rendered,
            status=(SMSAutomationDelivery.Status.SKIPPED if reason else SMSAutomationDelivery.Status.PENDING),
            failure_code=reason, scheduled_at=now,
        )
        for user_id, grant_id, phone, rendered, reason in rows
    ), batch_size=500)
    return {
        "already_applied": False, "campaign_id": campaign.pk,
        "old_pending_superseded": superseded,
        "new_pending": preview["new_pending_count"],
        "new_skipped": len(rows) - preview["new_pending_count"],
        "old_sent_preserved": preview["original_status_counts"].get(SMSAutomationDelivery.Status.SENT, 0),
    }


def reissue_sms_eligible(delivery, *, now):
    if not market_access_v2_enabled():
        return False
    parts = delivery.event_key.split(":")
    if len(parts) != 4 or parts[0] != REISSUE_PREFIX or parts[2] != "1":
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
        grant and TrialJourneyDay.objects.filter(day=1, is_active=True).exists()
        and journey_eligible(grant, 1, now=now)
    )
