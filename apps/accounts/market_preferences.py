"""Self-service V2 market selection; preferences are never access grants."""

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from .market_access import MARKETS, market_access_v2_enabled, with_market_access_relations
from .models import User, UserAccessAudit, UserAccessProfile, UserMarketPreference


@transaction.atomic
def update_market_preferences(*, user, selected_markets):
    if not market_access_v2_enabled() or not getattr(user, "is_authenticated", False):
        raise PermissionDenied("Market selection is unavailable.")
    target = User.objects.select_for_update().get(pk=user.pk)
    if target.is_superuser or target.role in (User.Role.SUPER_ADMIN, User.Role.SUPPORT):
        raise PermissionDenied("Special roles do not use regular market selection.")

    try:
        requested = set(selected_markets)
    except (TypeError, ValueError) as exc:
        raise ValidationError({"selected_markets": "Choose distinct, known markets."}) from exc
    if len(requested) != len(selected_markets) or not requested.issubset(MARKETS):
        raise ValidationError({"selected_markets": "Choose distinct, known markets."})
    existing = list(UserMarketPreference.objects.select_for_update().filter(user=target))
    previous = {entry.market for entry in existing}
    profile = UserAccessProfile.objects.select_for_update().filter(user=target).first()
    was_confirmed = bool(profile and profile.market_selection_confirmed_at)
    if previous == requested and was_confirmed:
        return with_market_access_relations(User.objects.filter(pk=target.pk)).get()

    UserMarketPreference.objects.filter(user=target, market__in=previous - requested).delete()
    UserMarketPreference.objects.bulk_create(
        (UserMarketPreference(user=target, market=market) for market in sorted(requested - previous)),
        batch_size=3,
    )
    if profile is None:
        profile = UserAccessProfile(user=target)
    if profile.market_selection_confirmed_at is None:
        profile.market_selection_confirmed_at = timezone.now()
    profile.save()
    UserAccessAudit.objects.create(
        user=target,
        subject_user_id=target.pk,
        actor=target,
        action=UserAccessAudit.Action.PREFERENCES_CHANGED,
        before={"selected_markets": sorted(previous), "confirmed": was_confirmed},
        after={"selected_markets": sorted(requested), "confirmed": True},
    )
    return with_market_access_relations(User.objects.filter(pk=target.pk)).get()
