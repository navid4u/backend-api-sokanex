"""Privacy-limited, server-side admin analytics."""

from datetime import date, datetime, time, timedelta, timezone as utc_timezone
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.cache import cache
from django.db.models import Count, IntegerField, Min, OuterRef, Q, Subquery, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.accounts.market_access import MARKETS, market_access_v2_enabled
from apps.accounts.models import User, UserMarketGrant

from .models import PageViewDailyAggregate, UserActivity


TEHRAN = ZoneInfo("Asia/Tehran")
PERIODS = {"1m": 1, "3m": 3, "6m": 6, "12m": 12, "7d": 7, "30d": 30}
PERSIAN_MONTHS = (
    "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
    "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند",
)
MARKET_LABELS = {
    "internal": "بازار داخلی", "forex": "فارکس", "crypto": "کریپتو", "": "انتخاب نشده",
}
TIER_LABELS = {
    "LEVEL_1": "سطح اولیه", "BASIC": "پایه", "PRO": "حرفه‌ای", "GOLD": "طلایی",
    "ELITE": "الیت", "MANAGEMENT": "حساب مدیریتی",
}
EVENT_DISPLAY = {
    UserActivity.Type.REGISTER: ("REGISTER", "ثبت‌نام کاربر", "/admin/users"),
    UserActivity.Type.LOGIN: ("LOGIN", "ورود کاربر", "/admin/users"),
    UserActivity.Type.LOGOUT: ("LOGOUT", "خروج کاربر", "/admin/users"),
    UserActivity.Type.PROFILE_UPDATE: ("PROFILE_UPDATE", "ویرایش پروفایل", "/admin/users"),
    UserActivity.Type.ARTICLE_READ: ("ARTICLE_VIEW", "مشاهده مقاله", "/admin/articles"),
    UserActivity.Type.VIDEO_WATCH: ("VIDEO_VIEW", "مشاهده ویدئو", "/admin/videos"),
    UserActivity.Type.LIVE_JOIN: ("LIVE_JOIN", "ورود به لایو", "/admin/livestream"),
    UserActivity.Type.COURSE_VIEW: ("COURSE_ENROLL", "ثبت‌نام کاربر در دوره", "/admin/academy"),
    UserActivity.Type.COURSE_ENROLL: ("COURSE_ENROLL", "ثبت‌نام کاربر در دوره", "/admin/academy"),
    UserActivity.Type.MARKET_ACCESS_REQUEST: ("MARKET_ACCESS_REQUEST", "درخواست دسترسی بازار", "/admin/market-access"),
    UserActivity.Type.MARKET_PREFERENCES_UPDATE: ("MARKET_PREFERENCES_UPDATE", "ویرایش بازارهای منتخب", "/admin/market-access"),
    UserActivity.Type.ASSET_ADDED: ("ASSET_ADDED", "افزودن دارایی", "/admin/users"),
    UserActivity.Type.COURSE_SESSION_VIEW: ("SESSION_VIEW", "مشاهده جلسه دوره", "/admin/academy"),
    UserActivity.Type.PERSONALITY_TEST_COMPLETED: ("PERSONALITY_SUBMIT", "ثبت آزمون شخصیت", "/admin/users"),
}


def gregorian_to_jalali(day):
    """Calendar conversion used only for Tehran month boundaries and labels."""
    gy, gm, gd = day.year, day.month, day.day
    offsets = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)
    if gy > 1600:
        jy, gy = 979, gy - 1600
    else:
        jy, gy = 0, gy - 621
    gy2 = gy + (1 if gm > 2 else 0)
    days = 365 * gy + (gy2 + 3) // 4 - (gy2 + 99) // 100 + (gy2 + 399) // 400 - 80 + gd + offsets[gm - 1]
    jy += 33 * (days // 12053)
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        return jy, 1 + days // 31, 1 + days % 31
    return jy, 7 + (days - 186) // 30, 1 + (days - 186) % 30


def _month_start(day):
    return day - timedelta(days=gregorian_to_jalali(day)[2] - 1)


def _bucket_starts(period, today):
    if period.endswith("d"):
        return [today - timedelta(days=offset) for offset in range(PERIODS[period] - 1, -1, -1)]
    starts = [_month_start(today)]
    for _ in range(PERIODS[period] - 1):
        starts.append(_month_start(starts[-1] - timedelta(days=1)))
    return list(reversed(starts))


def _start_utc(day):
    return datetime.combine(day, time.min, TEHRAN).astimezone(utc_timezone.utc)


def _tier_distribution(v2):
    management = Q(is_superuser=True) | Q(is_staff=True) | Q(role__in=(
        User.Role.SUPER_ADMIN, User.Role.SUPPORT, User.Role.ADMIN, User.Role.EMPLOYEE,
    ))
    management_count = User.objects.filter(management).count()
    normal = User.objects.exclude(management)
    if v2:
        active_grants = UserMarketGrant.objects.filter(
            user_id=OuterRef("pk"), revoked_at__isnull=True, market__in=MARKETS,
        ).values("user_id").annotate(n=Count("market", distinct=True)).values("n")
        rows = normal.annotate(
            grant_count=Coalesce(Subquery(active_grants, output_field=IntegerField()), 0),
        ).values("grant_count", "market_access_profile__is_elite").annotate(n=Count("pk"))
        counts = dict.fromkeys(TIER_LABELS, 0)
        for row in rows:
            key = "ELITE" if row["market_access_profile__is_elite"] else {
                0: "LEVEL_1", 1: "BASIC", 2: "PRO", 3: "GOLD",
            }.get(row["grant_count"], "GOLD")
            counts[key] += row["n"]
        counts["MANAGEMENT"] = management_count
        return [{"label": TIER_LABELS[key], "count": counts[key]} for key in TIER_LABELS], "market_access_v2"
    legacy = {row["access_level"]: row["n"] for row in normal.values("access_level").annotate(n=Count("pk"))}
    return [
        {"label": f"سطح {level}", "count": legacy.get(level, 0)} for level in range(1, 6)
    ] + [{"label": "حساب مدیریتی", "count": management_count}], "legacy_access_level"


def overview(period="6m", *, now=None):
    if period not in PERIODS:
        raise ValueError("Invalid period")
    injected_clock = now is not None
    v2 = market_access_v2_enabled()
    cache_key = f"admin:analytics:v1:{period}:{int(v2)}"
    if not injected_clock:
        cached = cache.get(cache_key)
        if cached is not None:
            return cached
    now = now or timezone.now()
    today = timezone.localtime(now, TEHRAN).date()
    starts = _bucket_starts(period, today)
    end_exclusive = min(_start_utc(today + timedelta(days=1)), now + timedelta(microseconds=1))
    bounds = [
        (_start_utc(start), min(_start_utc(starts[index + 1]) if index + 1 < len(starts) else end_exclusive, end_exclusive))
        for index, start in enumerate(starts)
    ]
    bucket_counts = User.objects.aggregate(**{
        f"bucket_{index}": Count("pk", filter=Q(created_at__gte=begin, created_at__lt=end))
        for index, (begin, end) in enumerate(bounds)
    })
    registrations = []
    for index, start in enumerate(starts):
        if period.endswith("d"):
            label = start.isoformat()
        else:
            jy, jm, _ = gregorian_to_jalali(start)
            label = f"{PERSIAN_MONTHS[jm - 1]} {str(jy).translate(str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹'))}"
        registrations.append({
            "date": _start_utc(start).astimezone(TEHRAN).isoformat(),
            "label": label,
            "count": bucket_counts[f"bucket_{index}"],
        })

    market_counts = {row["market_type"]: row["n"] for row in User.objects.values("market_type").annotate(n=Count("pk"))}
    market_results = [
        {"label": MARKET_LABELS[key], "count": market_counts.get(key, 0)} for key in MARKET_LABELS
    ]
    market_results[-1]["count"] += sum(n for key, n in market_counts.items() if key not in MARKET_LABELS)
    tiers, tier_source = _tier_distribution(v2)
    aggregates = PageViewDailyAggregate.objects.filter(day__gte=starts[0], day__lte=today)
    total_views = aggregates.aggregate(total=Sum("views"))["total"] or 0
    unique_users = aggregates.values("user_id").distinct().count()
    pages = aggregates.values("path").annotate(views=Sum("views"), unique_users=Count("user_id", distinct=True)).order_by("-views", "path")
    coverage = PageViewDailyAggregate.objects.aggregate(first=Min("day"))["first"]
    activity = UserActivity.objects.filter(created_at__gte=bounds[0][0], created_at__lt=end_exclusive,
                                           activity_type__in=EVENT_DISPLAY).exclude(
        Q(activity_type=UserActivity.Type.COURSE_VIEW) & ~Q(title="Course enrollment")
    ).select_related("user").order_by("-created_at", "-id")[:20]
    events = []
    for row in activity:
        if row.activity_type == UserActivity.Type.COURSE_VIEW:
            if row.title != "Course enrollment":
                continue
            kind, title, path = "COURSE_ENROLL", "ثبت‌نام کاربر در دوره", "/admin/academy"
        else:
            kind, title, path = EVENT_DISPLAY[row.activity_type]
        events.append({"id": row.pk, "activity_type": kind, "title": title, "created_at": row.created_at,
                       "user": {"id": row.user_id, "username": row.user.username}, "path": path})
    result = {
        "period": period,
        "timezone": "Asia/Tehran",
        "generated_at": now,
        "total_users": User.objects.count(),
        "registrations": registrations,
        "distributions": {"markets": market_results, "tiers": tiers},
        "page_views": {"total_views": total_views, "unique_users": unique_users, "results": list(pages)},
        "user_events": events,
        "metadata": {
            "total_users_denominator": "all_users_including_inactive_all_time",
            "period_counts": "registrations_page_views_and_user_events_within_selected_tehran_period",
            "tier_source": tier_source,
            "page_view_coverage_started_at": coverage,
            "page_view_history_backfilled": False,
            "raw_retention_days": 30,
            "daily_aggregate_retention_days": 400,
            "event_id_dedupe_retention_days": 400,
        },
    }
    if not injected_clock:
        cache.set(cache_key, result, timeout=60)
    return result
