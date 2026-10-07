"""V2 applications and reviews; never use the paid legacy upgrade ledger."""

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError

from .market_access import MARKETS, market_access_v2_enabled, resolve_market_access, user_can_manage_market_access
from .market_access_admin import update_user_market_access
from .models import MarketAccessRequest, User, UserAccessProfile, UserMarketGrant, UserMarketPreference


class MarketAccessRequestConflict(APIException):
    status_code = 409
    default_detail = "این درخواست با وضعیت فعلی دسترسی یا انتخاب بازار سازگار نیست."
    default_code = "MARKET_ACCESS_REQUEST_CONFLICT"
    machine_code = "MARKET_ACCESS_REQUEST_CONFLICT"


@transaction.atomic
def submit_market_access_request(*, user, requested_tier, message=""):
    if not market_access_v2_enabled() or not getattr(user, "is_authenticated", False):
        raise PermissionDenied("Market access requests are unavailable.")
    target = User.objects.select_for_update().get(pk=user.pk)
    if target.is_superuser or target.role in (User.Role.SUPER_ADMIN, User.Role.SUPPORT):
        raise PermissionDenied("Special roles do not request regular market access.")
    if not UserAccessProfile.objects.filter(
        user=target, market_selection_confirmed_at__isnull=False
    ).exists():
        raise ValidationError({"selected_markets": "Confirm your market preferences first."})
    selected = sorted(UserMarketPreference.objects.filter(user=target).values_list("market", flat=True))
    if not selected:
        raise ValidationError({"selected_markets": "Select at least one market."})
    if requested_tier == MarketAccessRequest.RequestedTier.PRO and len(selected) < 2:
        raise ValidationError({"requested_tier": "Pro requires at least two selected markets."})
    if requested_tier == MarketAccessRequest.RequestedTier.GOLD and len(selected) != 3:
        raise ValidationError({"requested_tier": "Gold requires all three selected markets."})
    if requested_tier not in MarketAccessRequest.RequestedTier.values:
        raise ValidationError({"requested_tier": "Unknown requested tier."})

    pending = MarketAccessRequest.objects.filter(
        user=target, status=MarketAccessRequest.Status.PENDING
    ).first()
    if pending:
        if pending.requested_tier == requested_tier and pending.requested_markets == selected:
            return pending, False
        raise MarketAccessRequestConflict("A different request is already pending review.")

    state = resolve_market_access(target)
    if requested_tier == MarketAccessRequest.RequestedTier.ELITE and state.is_elite:
        raise MarketAccessRequestConflict("Elite access is already active.")
    if requested_tier == MarketAccessRequest.RequestedTier.GOLD and state.membership_tier == "GOLD":
        raise MarketAccessRequestConflict("Gold access is already active.")
    if requested_tier == MarketAccessRequest.RequestedTier.PRO and state.membership_tier in ("PRO", "GOLD"):
        raise MarketAccessRequestConflict("Pro access or higher is already active.")

    request = MarketAccessRequest.objects.create(
        user=target,
        requested_tier=requested_tier,
        requested_markets=selected,
        message=message.strip(),
    )
    return request, True


@transaction.atomic
def review_market_access_request(*, actor, request_id, status, admin_note="",
                                 approved_markets=None, is_elite=None):
    if not market_access_v2_enabled() or not user_can_manage_market_access(actor):
        raise PermissionDenied("Market access request review is unavailable.")
    # Consistent lock order with submit and direct admin access changes: user, then request.
    request_user_id = get_object_or_404(MarketAccessRequest, pk=request_id).user_id
    target = User.objects.select_for_update().get(pk=request_user_id)
    application = MarketAccessRequest.objects.select_for_update().get(pk=request_id)
    if application.status != MarketAccessRequest.Status.PENDING:
        raise MarketAccessRequestConflict("This request has already been reviewed.")
    if status not in (MarketAccessRequest.Status.APPROVED, MarketAccessRequest.Status.REJECTED):
        raise ValidationError({"status": "Choose APPROVED or REJECTED."})
    if status == MarketAccessRequest.Status.REJECTED:
        if approved_markets is not None or is_elite is not None:
            raise ValidationError({"approved_markets": "Rejection cannot change access."})
    else:
        if approved_markets is None:
            raise ValidationError({"approved_markets": "Specify the markets to approve."})
        selected_now = set(UserMarketPreference.objects.filter(user=target).values_list("market", flat=True))
        if selected_now != set(application.requested_markets):
            raise MarketAccessRequestConflict("Market preferences changed after this request was submitted.")
        chosen = set(approved_markets)
        if not chosen or not chosen.issubset(selected_now) or not chosen.issubset(MARKETS):
            raise ValidationError({"approved_markets": "Approve at least one market from the user's selections."})
        current_elite = UserAccessProfile.objects.filter(user=target, is_elite=True).exists()
        approved_elite = current_elite if is_elite is None else is_elite
        update_user_market_access(
            actor=actor,
            user_id=target.pk,
            approved_markets=sorted(chosen),
            is_elite=approved_elite,
            grant_source=UserMarketGrant.Source.APPROVED_REQUEST,
        )
        application.approved_markets = sorted(chosen)
        application.approved_elite = approved_elite
    application.status = status
    application.admin_note = admin_note.strip()
    application.reviewed_by = actor
    application.reviewed_at = timezone.now()
    application.save(update_fields=(
        "status", "approved_markets", "approved_elite", "admin_note",
        "reviewed_by", "reviewed_at", "updated_at",
    ))
    return application
