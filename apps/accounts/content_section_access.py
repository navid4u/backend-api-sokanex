"""V2 content-section policy, independent of legacy per-item level flags."""

from django.db import transaction
from rest_framework.exceptions import PermissionDenied, ValidationError

from common.content_access import restrict_queryset_for_user, user_can_access_levels

from .market_access import market_access_v2_enabled, resolve_market_access, user_can_manage_market_access
from .models import (
    ContentSectionAccessAudit,
    ContentSectionAccessPolicy,
    User,
    default_content_access_tiers,
)


CONTENT_TIERS = tuple(default_content_access_tiers())
CONTENT_SECTIONS = tuple(ContentSectionAccessPolicy.Section.values)


def content_policy_rows():
    """Return all sections, including never-configured sections (open by default)."""
    configured = {
        row.section: row
        for row in ContentSectionAccessPolicy.objects.all()
    }
    return [
        {
            "section": section,
            "allowed_tiers": configured[section].allowed_tiers if section in configured else list(CONTENT_TIERS),
            "updated_at": configured[section].updated_at if section in configured else None,
        }
        for section in CONTENT_SECTIONS
    ]


def user_can_access_content_section(user, section, *, legacy_allowed_levels=None):
    if not getattr(user, "is_authenticated", False):
        return False
    if section not in CONTENT_SECTIONS:
        return False
    if not market_access_v2_enabled() or user.role == User.Role.SUPPORT:
        return True if legacy_allowed_levels is None else user_can_access_levels(user, legacy_allowed_levels)
    if user.is_superuser or user.role == User.Role.SUPER_ADMIN:
        return True
    if user.has_platform_permission(User.Permission.CONTENT_VIEW_ALL):
        return True
    state = resolve_market_access(user)
    tier = "GOLD" if state.trial_active else state.membership_tier
    if tier not in CONTENT_TIERS:
        return False
    allowed = ContentSectionAccessPolicy.objects.filter(section=section).values_list("allowed_tiers", flat=True).first()
    if allowed is None:
        allowed = CONTENT_TIERS
    return isinstance(allowed, (list, tuple)) and tier in allowed


def restrict_content_section_queryset(queryset, user, section):
    if not getattr(user, "is_authenticated", False):
        return queryset.none()
    if not market_access_v2_enabled() or user.role == User.Role.SUPPORT:
        return restrict_queryset_for_user(queryset, user)
    return queryset if user_can_access_content_section(user, section) else queryset.none()


@transaction.atomic
def update_content_section_policy(*, actor, section, allowed_tiers):
    """Replace one section's tier policy and audit real changes only."""
    if not market_access_v2_enabled() or not user_can_manage_market_access(actor):
        raise PermissionDenied("Content access management is unavailable.")
    if section not in CONTENT_SECTIONS or not isinstance(allowed_tiers, list) or (
        any(not isinstance(tier, str) or tier not in CONTENT_TIERS for tier in allowed_tiers)
        or len(allowed_tiers) != len(set(allowed_tiers))
    ):
        raise ValidationError("Invalid content section or allowed tiers.")
    policy, _ = ContentSectionAccessPolicy.objects.get_or_create(section=section)
    policy = ContentSectionAccessPolicy.objects.select_for_update().get(pk=policy.pk)
    before = list(policy.allowed_tiers)
    after = [tier for tier in CONTENT_TIERS if tier in allowed_tiers]
    if before != after:
        policy.allowed_tiers = after
        policy.updated_by = actor
        policy.save(update_fields=["allowed_tiers", "updated_by", "updated_at"])
        ContentSectionAccessAudit.objects.create(
            section=section, actor=actor, before=before, after=after,
        )
    return policy
