import logging

from django.db import transaction
from django.db.models.signals import post_delete, pre_save
from django.dispatch import receiver

from .models import ChannelPost


logger = logging.getLogger(__name__)

FILE_FIELDS = (
    "image", "video", "audio", "cover", "more_info_video", "usage_guide_video",
)
OWNED_PREFIXES = (
    "channels/uploads/",
    "internal_analysis/more_info/",
    "internal_analysis/usage_guides/",
)


def delete_after_commit(storage, name, field_name, excluded_pk=None):
    if not name or not name.startswith(OWNED_PREFIXES):
        return

    def delete_owned_file():
        try:
            references = ChannelPost.objects.filter(**{field_name: name})
            if excluded_pk is not None:
                references = references.exclude(pk=excluded_pk)
            if references.exists():
                return
            storage.delete(name)
        except Exception:
            logger.exception("Could not delete owned channel media", extra={"media_name": name})

    transaction.on_commit(delete_owned_file)


@receiver(pre_save, sender=ChannelPost)
def remove_replaced_channel_files(sender, instance, **kwargs):
    if not instance.pk:
        return
    try:
        previous = sender.objects.get(pk=instance.pk)
    except sender.DoesNotExist:
        return
    for field_name in FILE_FIELDS:
        old_file = getattr(previous, field_name)
        new_file = getattr(instance, field_name)
        if old_file and old_file.name != getattr(new_file, "name", None):
            delete_after_commit(old_file.storage, old_file.name, field_name, instance.pk)


@receiver(post_delete, sender=ChannelPost)
def remove_deleted_channel_files(sender, instance, **kwargs):
    for field_name in FILE_FIELDS:
        file_value = getattr(instance, field_name)
        if file_value:
            delete_after_commit(file_value.storage, file_value.name, field_name, instance.pk)
