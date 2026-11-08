"""V2 applications and reviews; never use the paid legacy upgrade ledger."""

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError

from .market_access import MARKETS, market_access_v2_enabled, resolve_market_access, user_can_manage_market_access
from .market_access_admin import update_user_market_access
from .models import MarketAccessRequest, User, UserAccessProfile, UserMarketGrant, UserMarketPreference
from apps.activity.models import UserActivity
from apps.activity.services import ActivityService
from apps.notifications.models import Notification


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
    confirmed_at = UserAccessProfile.objects.filter(user=target).values_list(
        "market_selection_confirmed_at", flat=True
    ).first()
    if confirmed_at is None:
        raise ValidationError({"selected_markets": "Confirm your market preferences first."})
    selected = sorted(set(UserMarketPreference.objects.filter(user=target).values_list("market", flat=True)))
    if not selected or not set(selected).issubset(MARKETS):
        raise ValidationError({"selected_markets": "Select at least one market."})
    if requested_tier not in MarketAccessRequest.RequestedTier.values:
        raise ValidationError({"requested_tier": "Unknown requested tier."})

    pending = MarketAccessRequest.objects.select_for_update().filter(
        user=target, status=MarketAccessRequest.Status.PENDING
    ).first()
    if pending and pending.created_at < confirmed_at:
        # A cohort reset requires a fresh application after the new market
        # confirmation. Retain the old request as reviewed history.
        pending.status = MarketAccessRequest.Status.REJECTED
        pending.admin_note = "Superseded by a new market selection confirmation."
        pending.reviewed_at = timezone.now()
        pending.save(update_fields=("status", "admin_note", "reviewed_at", "updated_at"))
        pending = None
    if pending:
        if pending.requested_tier == requested_tier:
            if pending.requested_markets == selected:
                return pending, False
            if requested_tier == MarketAccessRequest.RequestedTier.GOLD:
                pending.requested_markets = selected
                pending.revision += 1
                pending.save(update_fields=("requested_markets", "revision", "updated_at"))
                return pending, False
        raise MarketAccessRequestConflict("A different request is already pending review.")

    state = resolve_market_access(target)
    if requested_tier == MarketAccessRequest.RequestedTier.ELITE:
        if not state.granted_markets:
            raise ValidationError({"requested_tier": "Elite requests require an existing approved market."})
        if state.is_elite:
            raise MarketAccessRequestConflict("Elite access is already active.")
    elif requested_tier != MarketAccessRequest.RequestedTier.GOLD:
        if state.granted_markets:
            raise MarketAccessRequestConflict("Members may request GOLD or ELITE.")
        raise ValidationError({"requested_tier": "Initial membership requests must be GOLD."})

    request = MarketAccessRequest.objects.create(
        user=target,
        requested_tier=requested_tier,
        requested_markets=selected,
        message=message.strip(),
    )
    ActivityService.record(target, UserActivity.Type.MARKET_ACCESS_REQUEST, "Market access requested")
    return request, True


@transaction.atomic
def review_market_access_request(*, actor, request_id, status, admin_note="",
                                 approved_markets=None, is_elite=None, expected_revision=None):
    if not market_access_v2_enabled() or not user_can_manage_market_access(actor):
        raise PermissionDenied("Market access request review is unavailable.")
    # Consistent lock order with submit and direct admin access changes: user, then request.
    request_user_id = get_object_or_404(MarketAccessRequest, pk=request_id).user_id
    target = User.objects.select_for_update().get(pk=request_user_id)
    application = MarketAccessRequest.objects.select_for_update().get(pk=request_id)
    if application.status != MarketAccessRequest.Status.PENDING:
        same_rejection = (
            status == MarketAccessRequest.Status.REJECTED
            and approved_markets is None and is_elite is None
        )
        same_approval = (
            status == MarketAccessRequest.Status.APPROVED
            and approved_markets is not None
            and sorted(set(approved_markets)) == application.approved_markets
            and (is_elite is None or is_elite == application.approved_elite)
        )
        if (application.status == status
                and (not admin_note or application.admin_note == admin_note.strip())
                and (same_rejection or same_approval)):
            return application
        raise MarketAccessRequestConflict("This request has already been reviewed.")
    if status not in (MarketAccessRequest.Status.APPROVED, MarketAccessRequest.Status.REJECTED):
        raise ValidationError({"status": "Choose APPROVED or REJECTED."})
    if status == MarketAccessRequest.Status.APPROVED:
        if application.revision > 1 and expected_revision is None:
            raise MarketAccessRequestConflict("Request markets changed. Refresh the pending list and retry with expected_revision.")
        if expected_revision is not None and expected_revision != application.revision:
            raise MarketAccessRequestConflict("Request markets changed. Refresh the pending list before approval.")
        confirmed_at = UserAccessProfile.objects.filter(user=target).values_list(
            "market_selection_confirmed_at", flat=True
        ).first()
        if confirmed_at is None or application.created_at < confirmed_at:
            raise MarketAccessRequestConflict(
                "The user must confirm markets and submit a fresh request after the baseline reset."
            )
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
        superadmin = actor.is_superuser or actor.role == User.Role.SUPER_ADMIN
        if not chosen or not chosen.issubset(MARKETS) or (not superadmin and not chosen.issubset(selected_now)):
            raise ValidationError({
                "approved_markets": (
                    "Approve at least one valid market."
                    if superadmin else "Approve at least one market from the user's selections."
                )
            })
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
    if status == MarketAccessRequest.Status.APPROVED:
        Notification.objects.get_or_create(
            source_key=f"MARKET_ACCESS_REQUEST_APPROVED:{application.pk}",
            defaults={
                "recipient": target,
                "created_by": actor,
                "title": "دسترسی شما فعال شد",
                "message": "درخواست اشتراک شما تأیید شد و دسترسی بازارهای تأییدشده فعال است.",
                "notification_type": Notification.Type.SYSTEM,
                "target_url": "/dashboard",
                "send_sms": False,
            },
        )
    return application
