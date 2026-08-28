import hashlib
import uuid
from datetime import UTC, datetime, timedelta

from django.utils import timezone
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken

from apps.activity.models import UserActivity
from apps.activity.services import ActivityService

from .models import SecuritySettings, UserDevice


def issue_login_tokens(user, request, refresh_value=None, record_login=True):
    refresh = RefreshToken(refresh_value) if refresh_value else RefreshToken.for_user(user)
    security = SecuritySettings.load()
    refresh.set_exp(lifetime=timedelta(days=security.session_lifetime_days))
    refresh_value = str(refresh)
    access_value = str(refresh.access_token)
    OutstandingToken.objects.filter(jti=str(refresh["jti"])).update(
        token=refresh_value,
        expires_at=datetime.fromtimestamp(refresh["exp"], tz=UTC),
    )

    supplied_id = request.headers.get("X-Device-ID", "").strip()
    if supplied_id:
        device_id = supplied_id[:64]
    else:
        seed = f"{uuid.uuid4()}:{request.META.get('HTTP_USER_AGENT', '')}"
        device_id = hashlib.sha256(seed.encode()).hexdigest()
    user_agent = request.META.get("HTTP_USER_AGENT", "")[:500]
    ip_address = ActivityService.client_ip(request)
    device, _ = UserDevice.objects.update_or_create(
        user=user,
        device_id=device_id,
        defaults={
            "name": request.headers.get("X-Device-Name", "")[:150],
            "user_agent": user_agent,
            "ip_address": ip_address,
            "refresh_jti": str(refresh["jti"]),
            "revoked_at": None,
        },
    )
    extra_ids = list(
        UserDevice.objects.filter(user=user, revoked_at__isnull=True)
        .exclude(pk=device.pk)
        .order_by("-last_seen_at")
        .values_list("pk", flat=True)[max(security.max_active_devices - 1, 0):]
    )
    if extra_ids:
        old_jtis = list(
            UserDevice.objects.filter(pk__in=extra_ids)
            .exclude(refresh_jti="")
            .values_list("refresh_jti", flat=True)
        )
        for outstanding in OutstandingToken.objects.filter(user=user, jti__in=old_jtis):
            BlacklistedToken.objects.get_or_create(token=outstanding)
        UserDevice.objects.filter(pk__in=extra_ids).update(revoked_at=timezone.now())

    if record_login:
        ActivityService.record(
            user,
            UserActivity.Type.LOGIN,
            "Account login",
            description=device.name or user_agent[:150],
            target_type="device",
            target_id=device.pk,
            ip_address=ip_address,
        )
    return {"access": access_value, "refresh": refresh_value, "device_id": device_id}
