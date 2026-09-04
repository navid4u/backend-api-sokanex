from django.conf import settings
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import User, UserProfile


@receiver(post_save, sender=User, dispatch_uid="queue_crm_contact_sync")
def queue_crm_contact_sync(sender, instance, **kwargs):
    if not settings.CRM_ENABLED:
        return
    from .crm import CrmContactSyncService

    transaction.on_commit(lambda: CrmContactSyncService.queue_user(instance.pk))


@receiver(post_save, sender=UserProfile, dispatch_uid="queue_crm_profile_sync")
def queue_crm_profile_sync(sender, instance, **kwargs):
    if not settings.CRM_ENABLED:
        return
    from .crm import CrmContactSyncService

    transaction.on_commit(lambda: CrmContactSyncService.queue_user(instance.user_id))
