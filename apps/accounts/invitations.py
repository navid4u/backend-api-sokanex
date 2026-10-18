"""Attribution is recorded once, only for a newly created account."""

import secrets

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from .models import InvitationLink, InvitationRegistration


REGISTRATION_URL = "https://app.sokanex.com/register"


def active_invitation(token):
    if not isinstance(token, str) or not 1 <= len(token) <= 64:
        return None
    return InvitationLink.objects.filter(
        Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now()),
        token=token, is_active=True,
    ).first()


def create_invitation_link(*, name, actor):
    # 24 random bytes provide 192 bits of entropy. A DB constraint protects
    # against an astronomically unlikely collision across concurrent workers.
    for _ in range(3):
        try:
            with transaction.atomic():
                return InvitationLink.objects.create(
                    name=name, token=secrets.token_urlsafe(24), created_by=actor,
                )
        except IntegrityError:
            continue
    raise RuntimeError("Unable to allocate a unique invitation token.")


def attribute_new_user(*, user, token=None, fallback_link=None):
    """Call inside the account-creation transaction; never from login."""
    link = active_invitation(token) if token else None
    if link is None and fallback_link is not None:
        link = active_invitation(fallback_link.token)
    if link is not None:
        InvitationRegistration.objects.get_or_create(user=user, defaults={"link": link})
