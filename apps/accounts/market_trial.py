"""Superadmin-triggered, once-per-account V2 market-access trial campaigns."""

import uuid
import hashlib
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import models, transaction
from django.db.models import Exists, OuterRef
from django.utils import timezone
from rest_framework.exceptions import APIException, PermissionDenied

from .market_access import market_access_v2_enabled
from .models import (
    TrialAutoStartSettings, TrialAutoStartSettingsAudit, TrialCampaign,
    TrialGrant, TrialAutoStartDecision, User, UserAccessAudit, UserAccessProfile,
    UserMarketGrant,
)


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
        datetime.combine(registered_from, time.min), ZoneInfo("Asia/Tehran")
    )


def eligible_trial_users(*, registered_from=None):
    """Level 1 means zero active V2 grants, never the legacy access_level.

    Legacy Gold/trial dates and explicitly invalidated pre-reset grants are
    ignored. The current TrialGrant is the lifetime-use marker for this era.
    Existing V2 market grants do not exclude someone: they are revoked when
    the trial starts, per the seven-day-only rollout policy.
    """
    prior_trial = TrialGrant.objects.filter(user_id=OuterRef("pk"), invalidated_at__isnull=True)
    users = (
        User.objects.filter(is_active=True, is_superuser=False)
        .exclude(role__in=(User.Role.SUPER_ADMIN, User.Role.SUPPORT))
        .annotate(_has_v2_trial=Exists(prior_trial))
        .filter(_has_v2_trial=False)
    )
    cutoff = _registration_cutoff(registered_from)
    if cutoff is not None:
        users = users.filter(date_joined__gte=cutoff)
    return users


def trial_candidate_digest(user_ids):
    """Opaque fingerprint of the exact, sorted preview cohort (no user PII)."""
    encoded = ",".join(str(user_id) for user_id in sorted(user_ids)).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def auto_start_settings_payload():
    setting = TrialAutoStartSettings.objects.filter(pk=1).first()
    return {"auto_start_new_users": bool(setting and setting.auto_start_new_users)}


@transaction.atomic
def update_auto_start_settings(*, actor, auto_start_new_users):
    _require_superadmin(actor)
    setting, _ = TrialAutoStartSettings.objects.select_for_update().get_or_create(pk=1)
    previous = setting.auto_start_new_users
    if previous != auto_start_new_users:
        if auto_start_new_users:
            now = timezone.now()
            setting.enabled_at = now
            setting.campaign = TrialCampaign.objects.create(
                created_by=actor, duration_days=7,
                status=TrialCampaign.Status.APPLIED, applied_at=now,
            )
        setting.auto_start_new_users = auto_start_new_users
        setting.updated_by = actor
        setting.save(update_fields=("auto_start_new_users", "enabled_at", "campaign", "updated_by", "updated_at"))
        TrialAutoStartSettingsAudit.objects.create(
            actor=actor, before=previous, after=auto_start_new_users,
        )
    return {"auto_start_new_users": setting.auto_start_new_users}


def _create_trial_grants(*, user_ids, campaign, started_at, actor, source):
    """One grant/audit writer shared by campaign and registration paths.

    The caller owns an atomic transaction and has locked the relevant users.
    """
    ends_at = started_at + timedelta(days=7)
    TrialGrant.objects.bulk_create(
        (TrialGrant(user_id=user_id, campaign=campaign, started_at=started_at, ends_at=ends_at, source=source)
         for user_id in user_ids),
        batch_size=500,
    )
    from apps.notifications.trial_journey import enroll_new_grants
    enroll_new_grants(
        user_ids=user_ids, campaign=campaign, started_at=started_at,
    )
    operation_id = uuid.uuid4()
    UserAccessAudit.objects.bulk_create(
        (UserAccessAudit(
            user_id=user_id, subject_user_id=user_id, actor=actor,
            action=UserAccessAudit.Action.TRIAL_STARTED,
            before={"trial_active": False, "trial_used": False},
            after={"trial_active": True, "trial_used": True,
                   "campaign_id": campaign.pk, "source": source},
            operation_id=operation_id,
        ) for user_id in user_ids),
        batch_size=500,
    )
    return ends_at


def _revoke_pretrial_access(*, user_ids, at, actor, reason, granted_before=None):
    """Remove normal-user grants before a trial or at its end, with audit."""
    operation_id = uuid.uuid4()
    grants = UserMarketGrant.objects.select_for_update().filter(
        user_id__in=user_ids, revoked_at__isnull=True,
    )
    if granted_before is not None:
        grants = grants.filter(granted_at__lt=granted_before)
    for grant in grants.order_by("user_id", "pk"):
        grant.revoked_at = max(at, grant.granted_at)
        grant.revoked_by = actor
        grant.save(update_fields=("revoked_at", "revoked_by"))
        UserAccessAudit.objects.create(
            user_id=grant.user_id, subject_user_id=grant.user_id, actor=actor,
            action=UserAccessAudit.Action.MARKET_REVOKED,
            before={"market": grant.market, "active": True, "grant_id": grant.pk},
            after={"market": grant.market, "active": False, "reason": reason},
            operation_id=operation_id,
        )
    profiles = UserAccessProfile.objects.select_for_update().filter(
        user_id__in=user_ids, is_elite=True,
    )
    if granted_before is not None:
        profiles = profiles.filter(
            models.Q(elite_updated_at__isnull=True) | models.Q(elite_updated_at__lt=granted_before)
        )
    for profile in profiles.order_by("user_id"):
        profile.is_elite = False
        profile.elite_updated_at = at
        profile.elite_updated_by = actor
        profile.save(update_fields=("is_elite", "elite_updated_at", "elite_updated_by"))
        UserAccessAudit.objects.create(
            user_id=profile.user_id, subject_user_id=profile.user_id, actor=actor,
            action=UserAccessAudit.Action.ELITE_CHANGED,
            before={"is_elite": True},
            after={"is_elite": False, "reason": reason},
            operation_id=operation_id,
        )


@transaction.atomic
def start_new_user_trial(user):
    """Decide once at the first successful new-account session, inside its transaction."""
    target = User.objects.select_for_update().get(pk=user.pk)
    decision = TrialAutoStartDecision.objects.filter(user=target).select_related("grant").first()
    if decision:
        return None
    setting = TrialAutoStartSettings.objects.select_for_update().filter(pk=1).first()
    if not market_access_v2_enabled():
        reason = "V2_DISABLED"
    elif not setting or not setting.auto_start_new_users or not setting.campaign_id:
        reason = "AUTO_START_DISABLED"
    elif not target.is_active:
        reason = "USER_INACTIVE"
    elif target.is_superuser or target.role in (User.Role.SUPER_ADMIN, User.Role.SUPPORT):
        reason = "PROTECTED_ROLE"
    elif setting.enabled_at and target.created_at < setting.enabled_at:
        reason = "EXISTING_ACCOUNT"
    elif TrialGrant.objects.filter(user=target, invalidated_at__isnull=True).exists():
        reason = "TRIAL_ALREADY_USED"
    elif UserMarketGrant.objects.filter(user=target, revoked_at__isnull=True).exists():
        reason = "EXISTING_GRANT"
    else:
        reason = None
    if reason:
        TrialAutoStartDecision.objects.create(user=target, reason=reason)
        UserAccessAudit.objects.create(
            user=target, subject_user_id=target.pk, actor=None,
            action=UserAccessAudit.Action.TRIAL_AUTO_START_SKIPPED,
            before={}, after={"reason": reason}, operation_id=uuid.uuid4(),
        )
        return None
    started_at = timezone.now()
    _create_trial_grants(
        user_ids=(target.pk,), campaign=setting.campaign,
        started_at=started_at, actor=None, source="AUTO_NEW_USER",
    )
    grant = TrialGrant.objects.get(user=target, invalidated_at__isnull=True)
    TrialAutoStartDecision.objects.create(user=target, grant=grant, reason="STARTED")
    return grant


@transaction.atomic
def start_existing_user_trial(user):
    """Start one unused trial on a returning user's successful app entry.

    The rollout flag is deliberately separate from the registration switch.
    Previously approved market grants are revoked *before* the trial starts,
    so expiration never has to undo a later administrator approval.
    """
    if not market_access_v2_enabled() or not settings.TRIAL_EXISTING_LOGIN_ENABLED:
        return None
    target = User.objects.select_for_update().get(pk=user.pk)
    if not target.is_active or target.is_superuser or target.role in (
        User.Role.SUPER_ADMIN, User.Role.SUPPORT,
    ):
        return None
    if TrialGrant.objects.filter(user=target, invalidated_at__isnull=True).exists():
        return None
    setting = TrialAutoStartSettings.objects.select_for_update().filter(pk=1).first()
    if not setting or not setting.auto_start_new_users or not setting.campaign_id:
        return None

    now = timezone.now()
    _revoke_pretrial_access(
        user_ids=(target.pk,), at=now, actor=None,
        reason="AUTO_EXISTING_USER_TRIAL",
    )
    _create_trial_grants(
        user_ids=(target.pk,), campaign=setting.campaign,
        started_at=now, actor=None, source="AUTO_EXISTING_USER",
    )
    grant = TrialGrant.objects.get(user=target, invalidated_at__isnull=True)
    TrialAutoStartDecision.objects.update_or_create(
        user=target, defaults={"grant": grant, "reason": "STARTED"},
    )
    return grant


def audit_expired_trials(*, limit=200, now=None):
    """Record real expiry once; V2 access itself is resolved from server time."""
    if not market_access_v2_enabled():
        return 0
    now = now or timezone.now()
    grant_ids = list(TrialGrant.objects.filter(
        invalidated_at__isnull=True, revoked_at__isnull=True,
        expiry_audited_at__isnull=True, ends_at__lte=now,
    ).order_by("ends_at", "pk").values_list("pk", flat=True)[:limit])
    count = 0
    for grant_id in grant_ids:
        with transaction.atomic():
            grant = TrialGrant.objects.select_for_update().filter(
                pk=grant_id, invalidated_at__isnull=True, revoked_at__isnull=True,
                expiry_audited_at__isnull=True, ends_at__lte=now,
            ).first()
            if grant is None:
                continue
            # An access grant approved during a running trial must not survive
            # its end. A fresh approval *after* ends_at remains untouched.
            _revoke_pretrial_access(
                user_ids=(grant.user_id,), at=now, actor=None,
                reason="TRIAL_EXPIRED",
                granted_before=grant.ends_at,
            )
            UserAccessAudit.objects.create(
                user_id=grant.user_id, subject_user_id=grant.user_id, actor=None,
                action=UserAccessAudit.Action.TRIAL_EXPIRED,
                before={"trial_active": True, "grant_id": grant.pk},
                after={"trial_active": False, "grant_id": grant.pk},
                operation_id=uuid.uuid4(),
            )
            grant.expiry_audited_at = now
            grant.save(update_fields=("expiry_audited_at",))
            count += 1
    return count


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
    _revoke_pretrial_access(
        user_ids=user_ids, at=now, actor=actor, reason="ADMIN_TRIAL_CAMPAIGN",
    )
    campaign = TrialCampaign.objects.create(
        created_by=actor,
        created_from=_registration_cutoff(registered_from),
        duration_days=duration_days,
        status=TrialCampaign.Status.PENDING,
    )
    ends_at = _create_trial_grants(
        user_ids=user_ids, campaign=campaign, started_at=now,
        actor=actor, source="ADMIN_CAMPAIGN",
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
