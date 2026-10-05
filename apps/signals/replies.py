from django.db import transaction
from django.utils.html import strip_tags
from rest_framework.exceptions import APIException, ValidationError

from .models import VIPSignalPost


class VIPReplyConflict(APIException):
    status_code = 409
    default_detail = "این شناسه پیام قبلاً با مرجع Reply متفاوت ثبت شده است."
    default_code = "reply_conflict"


def _snapshot_from_post(post):
    return {
        "text": strip_tags(post.text).replace("\x00", "").strip()[:500],
        "media_type": (
            "image" if post.image else "video" if post.video
            else "audio" if post.audio else None
        ),
    }


def _resolve_parent(channel, own_external_id, reply_to_external_id):
    if not reply_to_external_id:
        return None
    cursor = reply_to_external_id
    direct_parent = None
    seen = set()
    for _ in range(100):
        if cursor == own_external_id or cursor in seen:
            raise ValidationError({"reply_to_external_id": "چرخه Reply مجاز نیست."})
        seen.add(cursor)
        candidate = VIPSignalPost.objects.filter(
            channel=channel, external_id=cursor
        ).first()
        if candidate is None:
            if VIPSignalPost.objects.filter(external_id=cursor).exclude(channel=channel).exists():
                raise ValidationError({"reply_to_external_id": "پیام مرجع در بازار دیگری است."})
            return direct_parent
        if direct_parent is None:
            direct_parent = candidate
        if not candidate.reply_to_external_id:
            return direct_parent
        cursor = candidate.reply_to_external_id
    raise ValidationError({"reply_to_external_id": "زنجیره Reply بیش از حد طولانی است."})


def _connect_waiting_replies(parent):
    if not parent.external_id:
        return
    waiting = VIPSignalPost.objects.filter(
        channel=parent.channel,
        reply_to_external_id=parent.external_id,
        parent__isnull=True,
    ).exclude(pk=parent.pk)
    for child in waiting:
        child.parent = parent
        if not child.reply_snapshot:
            child.reply_snapshot = _snapshot_from_post(parent)
        child.save(update_fields=("parent", "reply_snapshot", "updated_at"))


@transaction.atomic
def ingest_vip_post(channel, values):
    values = dict(values)
    external_id = values.pop("external_id", None)
    incoming_reply_id = values.pop("reply_to_external_id", None)
    incoming_snapshot = values.pop("reply_snapshot", {})

    if external_id:
        existing = VIPSignalPost.objects.select_for_update().filter(
            channel=channel, external_id=external_id
        ).first()
        if existing:
            if incoming_reply_id and existing.reply_to_external_id not in (None, incoming_reply_id):
                raise VIPReplyConflict()
            reply_id = incoming_reply_id or existing.reply_to_external_id
            if reply_id and not existing.parent_id:
                parent = _resolve_parent(channel, external_id, reply_id)
                existing.reply_to_external_id = reply_id
                existing.parent = parent
                if not existing.reply_snapshot:
                    existing.reply_snapshot = (
                        _snapshot_from_post(parent) if parent else incoming_snapshot
                    )
                existing.save(update_fields=(
                    "reply_to_external_id", "parent", "reply_snapshot", "updated_at"
                ))
            _connect_waiting_replies(existing)
            return existing, False

    parent = _resolve_parent(channel, external_id, incoming_reply_id)
    snapshot = _snapshot_from_post(parent) if parent else incoming_snapshot
    defaults = {
        **values,
        "channel": channel,
        "external_id": external_id,
        "parent": parent,
        "reply_to_external_id": incoming_reply_id,
        "reply_snapshot": snapshot,
        "source": VIPSignalPost.Source.TELEGRAM_API,
        "is_active": True,
    }
    if external_id:
        post, created = VIPSignalPost.objects.get_or_create(
            channel=channel, external_id=external_id, defaults=defaults
        )
        if not created:
            # A concurrent retry won the unique-key race; keep its original data.
            if incoming_reply_id and post.reply_to_external_id not in (None, incoming_reply_id):
                raise VIPReplyConflict()
            if incoming_reply_id and not post.parent_id:
                post.reply_to_external_id = incoming_reply_id
                post.parent = parent
                if not post.reply_snapshot:
                    post.reply_snapshot = snapshot
                post.save(update_fields=(
                    "reply_to_external_id", "parent", "reply_snapshot", "updated_at"
                ))
    else:
        post, created = VIPSignalPost.objects.create(**defaults), True
    _connect_waiting_replies(post)
    return post, created
