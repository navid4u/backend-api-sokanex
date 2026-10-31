"""Cancel only unsent day-three SMS for the fixed October 2026 trial campaign."""

import hashlib
from collections import Counter

from django.db import transaction
from django.utils import timezone

from apps.accounts.market_trial import (
    ONE_TIME_ALL_USERS_RESTART_KEY, TrialCampaignConflict, _require_superadmin,
)
from apps.accounts.models import TrialCampaign

from .models import SMSAutomationDelivery, TrialJourneyDispatch


CANCEL_CODE = "DAY3_TEXT_CHANGE_CANCELLED"


def _campaign():
    return TrialCampaign.objects.get(
        operation_key=ONE_TIME_ALL_USERS_RESTART_KEY,
        status=TrialCampaign.Status.APPLIED,
    )


def _deliveries(campaign):
    return SMSAutomationDelivery.objects.filter(
        trial_journey_dispatches__enrollment__grant__campaign=campaign,
        trial_journey_dispatches__day=3,
        trial_journey_dispatches__channel=TrialJourneyDispatch.Channel.SMS,
        event="JOURNEY",
    )


def _preview(campaign):
    statuses = Counter()
    digest = hashlib.sha256()
    for pk, event_key, status, sent_at, provider_id in _deliveries(campaign).order_by("pk").values_list(
        "pk", "event_key", "status", "sent_at", "provider_message_id",
    ).iterator(chunk_size=500):
        statuses[status] += 1
        if status == SMSAutomationDelivery.Status.PENDING:
            if sent_at is not None or provider_id:
                raise TrialCampaignConflict("A PENDING delivery has provider acceptance evidence; reconcile it.")
            digest.update(f"{pk}:{event_key}\n".encode("utf-8"))
    return {
        "campaign_id": campaign.pk,
        "day": 3,
        "pending_to_cancel": statuses[SMSAutomationDelivery.Status.PENDING],
        "sending_needs_review": statuses[SMSAutomationDelivery.Status.SENDING],
        "sent_preserved": statuses[SMSAutomationDelivery.Status.SENT],
        "failed_preserved": statuses[SMSAutomationDelivery.Status.FAILED],
        "day_three_dispatches_without_sms": TrialJourneyDispatch.objects.filter(
            enrollment__grant__campaign=campaign, day=3,
            channel=TrialJourneyDispatch.Channel.SMS, sms_delivery__isnull=True,
        ).count(),
        "already_cancelled": _deliveries(campaign).filter(
            status=SMSAutomationDelivery.Status.SKIPPED, failure_code=CANCEL_CODE,
        ).count(),
        "other_pending_untouched": SMSAutomationDelivery.objects.filter(
            status=SMSAutomationDelivery.Status.PENDING,
        ).exclude(pk__in=_deliveries(campaign).values("pk")).count(),
        "pending_digest": digest.hexdigest(),
    }


def preview_day_three_cancel(*, actor):
    _require_superadmin(actor)
    return _preview(_campaign())


@transaction.atomic
def apply_day_three_cancel(*, actor, expected_pending_count, expected_pending_digest):
    _require_superadmin(actor)
    campaign = _campaign()
    TrialCampaign.objects.select_for_update().get(pk=campaign.pk)
    preview = _preview(campaign)
    if preview["sending_needs_review"]:
        raise TrialCampaignConflict("A day-three SMS is SENDING; reconcile it before cancelling.")
    if (preview["pending_to_cancel"] != expected_pending_count
            or preview["pending_digest"] != expected_pending_digest):
        raise TrialCampaignConflict("Day-three pending audience changed; preview again.")
    if not preview["pending_to_cancel"]:
        return {**preview, "cancelled_now": 0}

    pending_ids = list(_deliveries(campaign).select_for_update().filter(
        status=SMSAutomationDelivery.Status.PENDING,
    ).order_by("pk").values_list("pk", flat=True))
    if len(pending_ids) != expected_pending_count:
        raise TrialCampaignConflict("Day-three pending count changed during cancellation.")
    now = timezone.now()
    cancelled = SMSAutomationDelivery.objects.filter(
        pk__in=pending_ids, status=SMSAutomationDelivery.Status.PENDING,
    ).update(status=SMSAutomationDelivery.Status.SKIPPED,
             failure_code=CANCEL_CODE, updated_at=now)
    if cancelled != expected_pending_count:
        raise TrialCampaignConflict("Day-three pending count changed during cancellation.")
    TrialJourneyDispatch.objects.filter(
        enrollment__grant__campaign=campaign, day=3,
        channel=TrialJourneyDispatch.Channel.SMS,
        sms_delivery_id__in=pending_ids,
    ).update(status="SKIPPED")
    return {**preview, "cancelled_now": cancelled}
