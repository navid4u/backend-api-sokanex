from django.db import transaction
from django.db.models.signals import post_delete, pre_save
from django.dispatch import receiver

from .models import ChannelPost


FILE_FIELDS = ("image", "video", "audio", "cover")


def delete_after_commit(storage, name):
    transaction.on_commit(lambda: storage.delete(name))


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
            delete_after_commit(old_file.storage, old_file.name)


@receiver(post_delete, sender=ChannelPost)
def remove_deleted_channel_files(sender, instance, **kwargs):
    for field_name in FILE_FIELDS:
        file_value = getattr(instance, field_name)
        if file_value:
            delete_after_commit(file_value.storage, file_value.name)
