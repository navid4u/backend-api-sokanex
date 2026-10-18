"""Bounded VIP channel retention; callers hold the per-channel database lock."""

import logging

from django.apps import apps
from django.db import transaction
from django.db import models
from django.utils.html import strip_tags

from .models import VIPSignalPost

logger = logging.getLogger(__name__)
LIMIT = 100


def retention_candidates(channel):
    posts = VIPSignalPost.objects.filter(channel=channel).order_by(
        "-published_at", "-created_at", "-id",
    )
    return list(posts.values_list("id", flat=True)[LIMIT:])


def _safe_snapshot(parent):
    return {
        "text": strip_tags(parent.text).replace("\x00", "").strip()[:500],
        "media_type": (
            "image" if parent.image else "video" if parent.video
            else "audio" if parent.audio else None
        ),
    }


def _delete_orphan_files(channel, names):
    prefix = f"signals/vip/{channel.lower()}/"
    for storage, name in names:
        if not name.startswith(prefix) or ".." in name.split("/"):
            continue
        try:
            # A library or another app may reference the same storage object.
            # Never delete merely because no VIP row uses the path.
            referenced = any(
                model._default_manager.filter(**{field.name: name}).exists()
                for model in apps.get_models()
                for field in model._meta.concrete_fields
                if isinstance(field, models.FileField)
            )
            if referenced:
                continue
        except Exception:
            logger.exception("vip_retention_reference_check_failed channel=%s", channel)
            continue
        try:
            storage.delete(name)
        except Exception:
            logger.exception("vip_retention_file_cleanup_failed channel=%s", channel)


def prune_vip_channel(channel):
    """Prune oldest rows, including inactive rows, inside the caller transaction."""
    ids = retention_candidates(channel)
    if not ids:
        return 0
    victims = list(VIPSignalPost.objects.filter(channel=channel, pk__in=ids))
    by_id = {post.pk: post for post in victims}
    children = VIPSignalPost.objects.filter(parent_id__in=ids).exclude(pk__in=ids)
    for child in children.iterator(chunk_size=200):
        parent = by_id[child.parent_id]
        snapshot = child.reply_snapshot or {}
        fallback = _safe_snapshot(parent)
        for key in ("text", "media_type"):
            if not snapshot.get(key):
                snapshot[key] = fallback[key]
        if child.reply_to_external_id is None and parent.external_id:
            child.reply_to_external_id = parent.external_id
        child.reply_snapshot = snapshot
        child.save(update_fields=("reply_snapshot", "reply_to_external_id", "updated_at"))
    files = []
    for post in victims:
        for field in (post.image, post.video, post.audio):
            if field and field.name:
                files.append((field.storage, field.name))
    VIPSignalPost.objects.filter(channel=channel, pk__in=ids).delete()
    transaction.on_commit(lambda: _delete_orphan_files(channel, files))
    return len(ids)
