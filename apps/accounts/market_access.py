"""Read-only market-access V2 resolution; not wired into legacy endpoints yet."""

from dataclasses import dataclass
from datetime import datetime

from django.conf import settings
from django.db.models import Exists, OuterRef, Q
from django.utils import timezone

from .models import PlatformRole, TrialGrant, User, UserMarketGrant


MARKETS = frozenset(User.MarketType.values)
TIER_BY_MARKET_COUNT = {
    0: "LEVEL_1",
    1: "BASIC",
    2: "PRO",
    3: "GOLD",
}


@dataclass(frozen=True)
class MarketAccessState:
    membership_tier: str | None
    selected_markets: frozenset[str]
    granted_markets: frozenset[str]
    effective_markets: frozenset[str]
    market_selection_confirmed: bool
    trial_active: bool
    trial_ends_at: datetime | None
    is_elite: bool
    has_gold_features: bool
    special_role: str | None


def market_access_v2_enabled() -> bool:
    """Deployment gate; false until the coordinated data/frontend cutover."""
    return bool(getattr(settings, "MARKET_ACCESS_V2_ENABLED", False))


def user_can_manage_market_access(user) -> bool:
    """Dedicated V2 capability; legacy user-management permission is unchanged."""
    if not getattr(user, "is_authenticated", False):
        return False
    if user.is_superuser or user.role == User.Role.SUPER_ADMIN:
        return True
    if user.role == User.Role.SUPPORT:
        return user.has_platform_permission(User.Permission.SUPPORT_MANAGE)
    return user.has_platform_permission(User.Permission.USER_MANAGE)


def with_market_access_relations(queryset):
    """Prefetch once for paginated user lists instead of N+1 access queries."""
    return queryset.select_related(
        "market_access_profile", "trial_grant_v2"
    ).prefetch_related("market_preferences_v2", "market_grants_v2")


def resolve_market_access(user, *, at=None) -> MarketAccessState:
    """Resolve access without mutating users or reading legacy Gold fields.

    The selected checkboxes are preferences only. The separate grant rows are
    the sole normal-user source of market access; an active trial temporarily
    overlays all markets without changing the underlying membership tier.
    """
    if at is None:
        at = timezone.now()
    empty = frozenset()
    if not getattr(user, "is_authenticated", False) or user.pk is None:
        return MarketAccessState(None, empty, empty, empty, False, False, None, False, False, None)

    if user.is_superuser or user.role == User.Role.SUPER_ADMIN:
        return MarketAccessState(None, empty, empty, MARKETS, False, False, None, False, True, "SUPER_ADMIN")
    if user.role == User.Role.SUPPORT:
        return MarketAccessState(None, empty, empty, empty, False, False, None, False, False, "SUPPORT")

    profile = getattr(user, "market_access_profile", None)
    trial = getattr(user, "trial_grant_v2", None)
    selected = frozenset(
        preference.market
        for preference in user.market_preferences_v2.all()
        if preference.market in MARKETS
    )
    granted = frozenset(
        grant.market
        for grant in user.market_grants_v2.all()
        if grant.revoked_at is None and grant.market in MARKETS
    )
    trial_active = bool(trial and trial.started_at <= at < trial.ends_at)
    tier = TIER_BY_MARKET_COUNT[len(granted)]
    return MarketAccessState(
        membership_tier=tier,
        selected_markets=selected,
        granted_markets=granted,
        effective_markets=MARKETS if trial_active else granted,
        market_selection_confirmed=bool(profile and profile.market_selection_confirmed_at),
        trial_active=trial_active,
        trial_ends_at=trial.ends_at if trial else None,
        is_elite=bool(profile and profile.is_elite),
        has_gold_features=trial_active or tier == "GOLD",
        special_role=None,
    )


def can_access_market(user, market: str, *, at=None) -> bool:
    if not isinstance(market, str):
        return False
    market = market.strip().lower()
    if market not in MARKETS:
        return False
    return market in resolve_market_access(user, at=at).effective_markets


def can_access_gold_features(user, *, at=None) -> bool:
    return resolve_market_access(user, at=at).has_gold_features


def has_basic_access(user, *, at=None) -> bool:
    """V2 general-section access; legacy role privileges remain intact."""
    if not getattr(user, "is_authenticated", False):
        return False
    if user.is_staff or user.has_platform_permission(User.Permission.CONTENT_VIEW_ALL):
        return True
    state = resolve_market_access(user, at=at)
    return bool(state.special_role or state.granted_markets or state.trial_active)


def users_with_basic_access(queryset, *, at=None):
    """Filter a User queryset in SQL for broadcast delivery without N+1 reads."""
    if at is None:
        at = timezone.now()
    privileged_role_ids = [
        role_id
        for role_id, permissions in PlatformRole.objects.filter(is_active=True)
        .values_list("id", "permissions")
        if User.Permission.CONTENT_VIEW_ALL in (permissions or [])
    ]
    grants = UserMarketGrant.objects.filter(user_id=OuterRef("pk"), revoked_at__isnull=True)
    trials = TrialGrant.objects.filter(
        user_id=OuterRef("pk"), started_at__lte=at, ends_at__gt=at
    )
    return queryset.alias(
        _v2_basic_grant=Exists(grants), _v2_basic_trial=Exists(trials)
    ).filter(
        Q(is_superuser=True)
        | Q(is_staff=True)
        | Q(role__in=(User.Role.SUPER_ADMIN, User.Role.SUPPORT, User.Role.ADMIN, User.Role.EMPLOYEE))
        | Q(custom_role_id__in=privileged_role_ids)
        | Q(_v2_basic_grant=True)
        | Q(_v2_basic_trial=True)
    )


def market_access_payload(user, *, at=None) -> dict:
    """Additive client-facing state; never claim V2 is live while gated off."""
    if not market_access_v2_enabled():
        return {"enabled": False}
    state = resolve_market_access(user, at=at)
    trial = getattr(user, "trial_grant_v2", None)
    return {
        "enabled": True,
        "membership_tier": state.membership_tier,
        "selected_markets": sorted(state.selected_markets),
        "approved_markets": sorted(state.granted_markets),
        "effective_markets": sorted(state.effective_markets),
        "market_selection_confirmed": state.market_selection_confirmed,
        "trial_used": trial is not None,
        "trial_active": state.trial_active,
        "trial_started_at": trial.started_at if trial else None,
        "trial_ends_at": state.trial_ends_at,
        "is_elite": state.is_elite,
        "has_gold_features": state.has_gold_features,
        "special_role": state.special_role,
    }
