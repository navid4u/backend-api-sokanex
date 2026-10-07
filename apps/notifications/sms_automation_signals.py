"""Small event adapters; callbacks only enqueue after the business transaction commits."""

import logging

from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.accounts.models import User, UserAccessAudit

from .sms_automation import queue_event

logger = logging.getLogger(__name__)


@receiver(post_save, sender=User, dispatch_uid="sms_automation_welcome_v1")
def queue_registration_welcome(sender, instance, created, **kwargs):
    if created and instance.phone and instance.is_active:
        transaction.on_commit(lambda: queue_event(instance.pk, "WELCOME", "WELCOME:REGISTRATION"))


@receiver(post_save, sender=UserAccessAudit, dispatch_uid="sms_automation_access_v1")
def queue_market_access_change(sender, instance, created, **kwargs):
    if not created or instance.action not in (
        UserAccessAudit.Action.MARKET_GRANTED,
        UserAccessAudit.Action.MARKET_REVOKED,
        UserAccessAudit.Action.ELITE_CHANGED,
    ):
        return
    user_id = instance.subject_user_id
    key = f"ACCESS:{instance.operation_id}"
    transaction.on_commit(lambda: queue_event(user_id, "ACCESS_CHANGE", key))
