"""Academy market discovery is intentionally broader than VIP entitlements."""

from django.utils import timezone

from apps.accounts.market_access import resolve_market_access


def academy_markets(user):
    state = resolve_market_access(user)
    # Market selection is discovery-only after a trial has expired. A fresh
    # approval must be the source of access; old selections cannot reopen it.
    if state.trial_ends_at is not None and state.trial_ends_at <= timezone.now():
        return state.effective_markets
    return state.effective_markets | state.selected_markets


def can_access_academy_market(user, market):
    return bool(market and market in academy_markets(user))
