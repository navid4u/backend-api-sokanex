"""Superadmin-triggered, once-per-account V2 market-access trial campaigns."""

import uuid
import hashlib
from datetime import datetime, time, timedelta

from django.db import transaction
from django.db.models import Exists, OuterRef
from django.utils import timezone
from rest_framework.exceptions import APIException, PermissionDenied

from .market_access import market_access_v2_enabled
from .models import TrialCampaign, TrialGrant, User, UserAccessAudit, UserMarketGrant


class TrialCampaignConflict(APIException):
    status_code = 409
    default_detail = "Eligible users changed. Preview the campaign again."
    default_code = "TRIAL_CAMPAIGN_CONFLICT"
    machine_code = "TRIAL_CAMPAIGN_CONFLICT"


def _require_superadmin(actor):
    if not market_access_v2_enabled() or not getattr(actor, "is_authenticated", False):
        raise PermissionDenied("Trial campaigns are unavailable.")
    if not (actor.is_superuser or actor.role == User.Role.SUPER_ADMIN):
        raise PermissionDenied("Only a super administrator can start a trial campaign.")


def _registration_cutoff(registered_from):
    if registered_from is None:
        return None
    return timezone.make_aware(
        datetime.combine(registered_from, time.min), timezone.get_current_timezone()
    )


def eligible_trial_users(*, registered_from=None):
    """Level 1 means zero active V2 grants, never the legacy access_level.

    Legacy Gold/trial dates are intentionally ignored. The O2O TrialGrant is
    the lifetime-use marker. Disabled and privileged accounts are excluded.
    """
    grants = UserMarketGrant.objects.filter(user_id=OuterRef("pk"), revoked_at__isnull=True)
    prior_trial = TrialGrant.objects.filter(user_id=OuterRef("pk"))
    users = (
        User.objects.filter(is_active=True, is_superuser=False)
        .exclude(role__in=(User.Role.SUPER_ADMIN, User.Role.SUPPORT))
        .annotate(_has_active_market_grant=Exists(grants), _has_v2_trial=Exists(prior_trial))
        .filter(_has_active_market_grant=False, _has_v2_trial=False)
    )
    cutoff = _registration_cutoff(registered_from)
    if cutoff is not None:
        users = users.filter(date_joined__gte=cutoff)
    return users


def trial_candidate_digest(user_ids):
    """Opaque fingerprint of the exact, sorted preview cohort (no user PII)."""
    encoded = ",".join(str(user_id) for user_id in sorted(user_ids)).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def preview_trial_campaign(*, actor, registered_from=None):
    _require_superadmin(actor)
    user_ids = list(
        eligible_trial_users(registered_from=registered_from)
        .order_by("pk")
        .values_list("pk", flat=True)
    )
    return {
        "registered_from": registered_from,
        "duration_days": 7,
        "eligible_count": len(user_ids),
        "candidate_digest": trial_candidate_digest(user_ids),
    }


@transaction.atomic
def start_trial_campaign(*, actor, registered_from=None, expected_eligible_count, expected_candidate_digest):
    """Create one atomic campaign; a failed or stale run writes nothing.

    A fixed User row serializes concurrent campaigns. Candidate rows are then
    locked so individual access edits cannot interleave with eligibility.
    Bulk inserts are bounded by batch_size but share one transaction, keeping
    grants and audit entries all-or-nothing.
    """
    _require_superadmin(actor)
    # The actor exists, so at least one user row exists. Lock the lowest PK as
    # a shared mutex across different superadmin accounts and API workers.
    User.objects.order_by("pk").select_for_update().values_list("pk", flat=True).first()
    candidates = eligible_trial_users(registered_from=registered_from)
    proposed_ids = list(candidates.order_by("pk").values_list("pk", flat=True))
    # Lock the selected user rows before a fresh eligibility query. A manager
    # may have approved a market while this operation was waiting for a lock.
    list(
        User.objects.filter(pk__in=proposed_ids)
        .order_by("pk")
        .select_for_update()
        .values_list("pk", flat=True)
    )
    user_ids = list(
        eligible_trial_users(registered_from=registered_from)
        .filter(pk__in=proposed_ids)
        .order_by("pk")
        .values_list("pk", flat=True)
    )
    if (
        not user_ids
        or len(user_ids) != expected_eligible_count
        or trial_candidate_digest(user_ids) != expected_candidate_digest
    ):
        raise TrialCampaignConflict()

    now = timezone.now()
    duration_days = 7
    ends_at = now + timedelta(days=duration_days)
    campaign = TrialCampaign.objects.create(
        created_by=actor,
        created_from=_registration_cutoff(registered_from),
        duration_days=duration_days,
        status=TrialCampaign.Status.PENDING,
    )
    TrialGrant.objects.bulk_create(
        (
            TrialGrant(user_id=user_id, campaign=campaign, started_at=now, ends_at=ends_at)
            for user_id in user_ids
        ),
        batch_size=500,
    )
    operation_id = uuid.uuid4()
    UserAccessAudit.objects.bulk_create(
        (
            UserAccessAudit(
                user_id=user_id,
                subject_user_id=user_id,
                actor=actor,
                action=UserAccessAudit.Action.TRIAL_STARTED,
                before={"trial_active": False, "trial_used": False},
                after={"trial_active": True, "trial_used": True, "campaign_id": campaign.pk},
                operation_id=operation_id,
            )
            for user_id in user_ids
        ),
        batch_size=500,
    )
    campaign.status = TrialCampaign.Status.APPLIED
    campaign.applied_at = now
    campaign.save(update_fields=("status", "applied_at"))
    return {
        "id": campaign.pk,
        "status": campaign.status,
        "registered_from": registered_from,
        "duration_days": duration_days,
        "started_at": now,
        "ends_at": ends_at,
        "granted_count": len(user_ids),
    }
