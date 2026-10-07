"""Audited, atomic administrator changes to V2 market grants and Elite."""

import uuid

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from .market_access import (
    market_access_v2_enabled,
    user_can_manage_market_access,
    with_market_access_relations,
)
from .models import User, UserAccessAudit, UserAccessProfile, UserMarketGrant


def _is_special(user):
    return user.is_superuser or user.role in (User.Role.SUPER_ADMIN, User.Role.SUPPORT)


@transaction.atomic
def update_user_market_access(*, actor, user_id, approved_markets=None, is_elite=None,
                              grant_source=UserMarketGrant.Source.ADMIN):
    """Replace active grants and/or Elite; never touch legacy access fields.

    The user row is locked first so concurrent updates for one user serialize.
    All grant and audit writes share the same transaction. Replaying the same
    request has no effect and produces no duplicate audit entries.
    """
    if not market_access_v2_enabled() or not user_can_manage_market_access(actor):
        raise PermissionDenied("Market access management is unavailable.")
    target = get_object_or_404(User.objects.select_for_update(), pk=user_id)
    if _is_special(target):
        raise PermissionDenied("Special-role access cannot be edited here.")
    if actor.pk == target.pk:
        raise PermissionDenied("You cannot edit your own market access.")
    if grant_source not in UserMarketGrant.Source.values:
        raise ValueError("Unknown grant source.")

    active_grants = list(
        UserMarketGrant.objects.select_for_update()
        .filter(user=target, revoked_at__isnull=True)
        .order_by("pk")
    )
    before_markets = {grant.market for grant in active_grants}
    requested_markets = before_markets if approved_markets is None else set(approved_markets)
    profile = UserAccessProfile.objects.select_for_update().filter(user=target).first()
    before_elite = bool(profile and profile.is_elite)
    requested_elite = before_elite if is_elite is None else is_elite
    if requested_markets == before_markets and requested_elite == before_elite:
        return with_market_access_relations(User.objects.filter(pk=target.pk)).get()

    operation_id = uuid.uuid4()
    now = timezone.now()
    for grant in active_grants:
        if grant.market not in requested_markets:
            grant.revoked_at = now
            grant.revoked_by = actor
            grant.save(update_fields=("revoked_at", "revoked_by"))
            UserAccessAudit.objects.create(
                user=target,
                subject_user_id=target.pk,
                actor=actor,
                action=UserAccessAudit.Action.MARKET_REVOKED,
                before={"market": grant.market, "active": True},
                after={"market": grant.market, "active": False},
                operation_id=operation_id,
            )
    for market in sorted(requested_markets - before_markets):
        UserMarketGrant.objects.create(
            user=target,
            market=market,
            source=grant_source,
            granted_by=actor,
            granted_at=now,
        )
        UserAccessAudit.objects.create(
            user=target,
            subject_user_id=target.pk,
            actor=actor,
            action=UserAccessAudit.Action.MARKET_GRANTED,
            before={"market": market, "active": False},
            after={"market": market, "active": True},
            operation_id=operation_id,
        )
    if requested_elite != before_elite:
        if profile is None:
            profile = UserAccessProfile(user=target)
        profile.is_elite = requested_elite
        profile.elite_updated_at = now
        profile.elite_updated_by = actor
        profile.save()
        UserAccessAudit.objects.create(
            user=target,
            subject_user_id=target.pk,
            actor=actor,
            action=UserAccessAudit.Action.ELITE_CHANGED,
            before={"is_elite": before_elite},
            after={"is_elite": requested_elite},
            operation_id=operation_id,
        )
    return with_market_access_relations(User.objects.filter(pk=target.pk)).get()
