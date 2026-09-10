from django.conf import settings
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import UpgradeRequest, User, UserProfile


@receiver(post_save, sender=UpgradeRequest, dispatch_uid="premium_upgrade_enforces_level_five")
def premium_upgrade_enforces_level_five(sender, instance, **kwargs):
    if (
        instance.request_type == UpgradeRequest.Type.PREMIUM
        and instance.status == UpgradeRequest.Status.APPROVED
    ):
        User.objects.filter(pk=instance.user_id).exclude(
            access_level=User.AccessLevel.LEVEL_5
        ).update(access_level=User.AccessLevel.LEVEL_5)


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
