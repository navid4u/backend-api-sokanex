"""Academy market discovery is intentionally broader than VIP entitlements."""

from apps.accounts.market_access import resolve_market_access


def academy_markets(user):
    state = resolve_market_access(user)
    return state.effective_markets | state.selected_markets


def can_access_academy_market(user, market):
    return bool(market and market in academy_markets(user))
