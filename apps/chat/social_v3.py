"""Visibility-preserving social filters and signed keyset pagination."""

import hashlib
import json

from django.core import signing
from django.db.models import Case, Count, IntegerField, Q, Value, When
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from .community import normalize_tag
from .models import TraderPost, UserFollow


FEEDS = {"for_you", "following", "analysis", "questions", "discussed"}
CURSOR_SALT = "sokanex-social-v3-cursor"


def filter_social_posts(queryset, request):
    params = request.query_params
    feed = params.get("feed", "for_you")
    market = params.get("market", "ALL")
    if feed not in FEEDS:
        raise ValidationError({"feed": "Unknown feed."})
    if market != "ALL" and market not in TraderPost.Market.values:
        raise ValidationError({"market": "Unknown market."})
    if market != "ALL":
        queryset = queryset.filter(market=market)
    if feed == "following" or params.get("following") == "true":
        followed = UserFollow.objects.filter(follower=request.user).values("following_id")
        queryset = queryset.filter(author_id__in=followed)
    elif feed == "analysis":
        queryset = queryset.filter(post_type=TraderPost.Type.ANALYSIS)
    elif feed == "questions":
        queryset = queryset.filter(post_type=TraderPost.Type.QUESTION)
    search = params.get("search", "").strip()
    if search:
        queryset = queryset.filter(text__icontains=search[:200])
    hashtag = params.get("hashtag", "").strip()
    if hashtag:
        tag = normalize_tag(hashtag)
        if not tag or len(tag) > 100:
            raise ValidationError({"hashtag": "Invalid hashtag."})
        queryset = queryset.filter(hashtags__tag=tag)
    return queryset


def _filter_fingerprint(request, extra_filter):
    params = {key: request.query_params.get(key, "") for key in ("feed", "market", "search", "hashtag", "following", "post_type")}
    params.update(extra_filter or {})
    return hashlib.sha256(json.dumps(params, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _cursor_url(request, *, snapshot, fingerprint, mode, boundary, backward, size):
    payload = {"v": 1, "s": snapshot.isoformat(), "f": fingerprint, "m": mode, "b": boundary, "r": backward}
    token = signing.dumps(payload, salt=CURSOR_SALT, compress=True)
    query = request.query_params.copy()
    query["cursor"] = token
    query["page_size"] = str(size)
    return request.build_absolute_uri(f"{request.path}?{query.urlencode()}")


def _boundary_q(fields, values, backward):
    result = Q(pk__in=[])
    equal = Q()
    for field, value in zip(fields, values):
        op = "gt" if backward else "lt"
        result |= equal & Q(**{f"{field}__{op}": value})
        equal &= Q(**{field: value})
    return result


def enrich_social_authors(request, objects):
    if not objects:
        return
    from apps.accounts.models import User
    from .views import social_posts_for, social_users_for
    author_ids = {obj.author_id for obj in objects}
    request._social_author_lookup = {
        user.pk: user for user in social_users_for(User.objects.filter(pk__in=author_ids), request.user).select_related("social_analyst_profile", "profile_details")
    }
    activity = {author_id: set() for author_id in author_ids}
    for author_id, market in social_posts_for(request.user).filter(author_id__in=author_ids).values_list("author_id", "market").distinct():
        activity[author_id].add(market)
    request._social_activity_markets = {key: sorted(values) for key, values in activity.items()}


def paginated_social_posts(queryset, request, serializer_factory, extra_filter=None):
    try:
        size = int(request.query_params.get("page_size", "20"))
    except ValueError:
        raise ValidationError({"page_size": "Must be an integer."}) from None
    if not 1 <= size <= 100:
        raise ValidationError({"page_size": "Must be between 1 and 100."})
    mode = request.query_params.get("feed", "for_you") if not extra_filter else "profile"
    fingerprint = _filter_fingerprint(request, extra_filter)
    token = request.query_params.get("cursor")
    backward = False
    boundary = None
    snapshot = timezone.now()
    if token:
        try:
            payload = signing.loads(token, salt=CURSOR_SALT, max_age=7 * 24 * 3600)
            if payload.get("v") != 1 or payload.get("f") != fingerprint or payload.get("m") != mode:
                raise ValueError("Cursor belongs to another filter.")
            snapshot = parse_datetime(payload["s"])
            if snapshot is None or timezone.is_naive(snapshot):
                raise ValueError("Invalid cursor date.")
            backward = bool(payload["r"])
            boundary = payload["b"]
        except (signing.BadSignature, KeyError, TypeError, ValueError):
            raise ValidationError({"cursor": "Invalid or incompatible cursor."}) from None
    queryset = queryset.filter(created_at__lte=snapshot)
    if mode == "discussed":
        queryset = queryset.annotate(discussion_rank=Count("comments", filter=Q(comments__is_deleted=False, comments__created_at__lte=snapshot), distinct=True))
        fields = ["discussion_rank", "created_at", "id"]
    elif mode == "for_you":
        followed = UserFollow.objects.filter(follower=request.user).values("following_id")
        selected = list(request.user.market_preferences_v2.values_list("market", flat=True))
        fields = ["feed_rank", "created_at", "id"]
        queryset = queryset.annotate(feed_rank=Case(
            When(author_id__in=followed, then=Value(2)),
            When(market__in=selected, then=Value(1)),
            default=Value(0), output_field=IntegerField(),
        ))
    else:
        fields = ["created_at", "id"]
    if boundary:
        if len(boundary) != len(fields):
            raise ValidationError({"cursor": "Invalid cursor boundary."})
        values = [parse_datetime(value) if field == "created_at" else int(value) for field, value in zip(fields, boundary)]
        queryset = queryset.filter(_boundary_q(fields, values, backward))
    order = [f"{'' if backward else '-'}{field}" for field in fields]
    page = list(queryset.order_by(*order)[:size + 1])
    has_more = len(page) > size
    page = page[:size]
    if backward:
        page.reverse()
    enrich_social_authors(request, page)
    from .community import prepare_poll_data
    prepare_poll_data(request, page)
    def marker(post):
        return [getattr(post, field).isoformat() if field == "created_at" else getattr(post, field) for field in fields]
    next_url = _cursor_url(request, snapshot=snapshot, fingerprint=fingerprint, mode=mode, boundary=marker(page[-1]), backward=False, size=size) if page and (has_more if not backward else True) else None
    previous_url = _cursor_url(request, snapshot=snapshot, fingerprint=fingerprint, mode=mode, boundary=marker(page[0]), backward=True, size=size) if page and (has_more if backward else bool(token)) else None
    return Response({"results": serializer_factory(page, many=True).data, "next": next_url, "previous": previous_url})
