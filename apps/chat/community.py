"""Small, server-authoritative helpers for the existing chat/social API."""

import re

from django.conf import settings
from django.db.models import Count
from django.utils import timezone

from .models import PollOption, PollVote, PostHashtag, PostPoll, RoomMembership, TraderPost


HASHTAG_RE = re.compile(r"(?<![\w\u200c])#([\w\u200c]{1,100})", re.UNICODE)


def normalize_tag(tag):
    return (tag or "").lstrip("#").strip("_\u200c").lower()


def sync_post_hashtags(post):
    tags = {normalize_tag(match) for match in HASHTAG_RE.findall(post.text or "")}
    tags.discard("")
    PostHashtag.objects.filter(post=post).exclude(tag__in=tags).delete()
    existing = set(PostHashtag.objects.filter(post=post).values_list("tag", flat=True))
    PostHashtag.objects.bulk_create(
        [PostHashtag(post=post, tag=tag) for tag in tags - existing], ignore_conflicts=True
    )


def prepare_poll_data(request, posts):
    poll_post_ids = [post.pk for post in posts if post.post_type == TraderPost.Type.POLL]
    if not poll_post_ids:
        return
    polls = list(PostPoll.objects.filter(post_id__in=poll_post_ids))
    poll_ids = [poll.pk for poll in polls]
    options = {poll_id: [] for poll_id in poll_ids}
    for option in PollOption.objects.filter(poll_id__in=poll_ids).annotate(votes_count=Count("votes")).order_by("position", "pk"):
        options[option.poll_id].append(option)
    selected = dict(PollVote.objects.filter(poll_id__in=poll_ids, user=request.user).values_list("poll_id", "option_id"))
    request._social_poll_lookup = {poll.post_id: (poll, options[poll.pk], selected.get(poll.pk)) for poll in polls}


def poll_response(post, user, request=None):
    cached = getattr(request, "_social_poll_lookup", {}) if request else {}
    if post.pk in cached:
        poll, options, selected = cached[post.pk]
    else:
        poll = PostPoll.objects.filter(post=post).first()
        if poll is None:
            return None
        options = list(poll.options.annotate(votes_count=Count("votes")).order_by("position", "pk"))
        selected = PollVote.objects.filter(poll=poll, user=user).values_list("option_id", flat=True).first()
    if poll is None:
        return None
    now = timezone.now()
    is_closed = bool(poll.closes_at and poll.closes_at <= now)
    show_results = bool(selected or is_closed)
    total = sum(option.votes_count for option in options)
    return {
        "question": poll.question,
        "total_votes": total if show_results else None,
        "has_voted": selected is not None,
        "is_closed": is_closed,
        "show_results": show_results,
        "selected_option_id": selected,
        "options": [
            {
                "id": option.pk,
                "text": option.text,
                "votes_count": option.votes_count if show_results else None,
                "percentage": round(option.votes_count * 100 / total, 1) if show_results and total else (0 if show_results else None),
            }
            for option in options
        ],
    }


def _redis():
    if not settings.REDIS_URL:
        return None
    try:
        import redis
        client = redis.Redis.from_url(settings.REDIS_URL, socket_connect_timeout=0.2, socket_timeout=0.2)
        client.ping()
        return client
    except Exception:
        return None


def presence_available():
    return _redis() is not None


def _presence_key(room_id):
    return f"sokanex:chat:presence:{room_id}"


def room_online_ids(room, client=None):
    if not room.is_active:
        return set()
    client = client or _redis()
    if client is None:
        return None
    try:
        key = _presence_key(room.pk)
        now = timezone.now().timestamp()
        client.zremrangebyscore(key, "-inf", now)
        return {int(value) for value in client.zrangebyscore(key, now, "+inf")}
    except Exception:
        return None


def room_online_count(room):
    users = room_online_ids(room)
    return len(users) if users is not None else None


def heartbeat(room, user):
    client = _redis()
    if client is None:
        return None
    try:
        key = _presence_key(room.pk)
        now = timezone.now().timestamp()
        client.zadd(key, {str(user.pk): now + 90})
        client.expire(key, 120)
        return len(room_online_ids(room, client))
    except Exception:
        return None


def clear_presence(room, user=None):
    client = _redis()
    if client is None:
        return
    try:
        if user is None:
            client.delete(_presence_key(room.pk))
        else:
            client.zrem(_presence_key(room.pk), str(user.pk))
    except Exception:
        pass


def can_invite_to_room(room, user):
    if not user or not user.is_authenticated or not room.is_active:
        return False
    return RoomMembership.objects.filter(
        room=room, user=user, role__in=[RoomMembership.Role.ADMIN, RoomMembership.Role.MODERATOR]
    ).exists()


def queue_social_notification(*, key, recipient_id, title, url):
    """Called from on_commit. Generic text only; never embed private content."""
    if not recipient_id:
        return
    from apps.notifications.models import Notification

    Notification.objects.get_or_create(
        source_key=f"SOCIAL:{key}"[:120],
        defaults={
            "recipient_id": recipient_id,
            "notification_type": Notification.Type.SOCIAL,
            "title": title,
            "message": title,
            "target_url": url,
            "send_sms": False,
            "show_in_app": True,
            "is_active": True,
        },
    )
