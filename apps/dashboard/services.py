from apps.accounts.models import FinancialPersonalityAssessment, User
from apps.signals.models import VIPSignalPost
from apps.wallet.services import WalletService
from apps.articles.services import ArticleService
from apps.videos.services import VideoService
from apps.notifications.services import NotificationService
from apps.chat.services import ChatService
from apps.livestream.services import LiveEventService
from apps.accounts.models import BrokerConnection
from django.conf import settings
from apps.accounts.market_access import can_view_vip_market, market_access_payload, market_access_v2_enabled, user_can_manage_market_access
from apps.content_channels.models import ChannelPost
from django.utils import timezone
from django.utils.html import strip_tags
from html import unescape
import re


def _public_excerpt(value):
    return re.sub(r"\s+", " ", strip_tags(unescape(value or ""))).strip()[:160]


def _vip_previews(user):
    # Reserve room for each channel so a busy CRYPTO feed cannot hide FOREX.
    posts = []
    for channel in (VIPSignalPost.Channel.CRYPTO, VIPSignalPost.Channel.FOREX):
        posts.extend(VIPSignalPost.objects.filter(
            channel=channel, is_active=True,
        ).order_by("-published_at", "-created_at", "-id")[:2])
    if len(posts) < 4:
        selected_ids = {post.pk for post in posts}
        posts.extend(VIPSignalPost.objects.filter(is_active=True).exclude(
            pk__in=selected_ids,
        ).order_by("-published_at", "-created_at", "-id")[:4 - len(posts)])
    posts.sort(key=lambda post: (post.published_at, post.created_at, post.pk), reverse=True)
    result = []
    for post in posts:
        can_view = can_view_vip_market(user, post.channel.lower())
        result.append({
            "id": post.pk,
            "channel": post.channel,
            "excerpt": _public_excerpt(post.text) if can_view else "پست جدید کانال ویژه سوکانکس",
            # The model stores the original private image, not a public thumbnail.
            "image": None,
            "published_at": post.published_at,
            "can_view": can_view,
        })
    return result


def _internal_previews(user):
    # Mirror the market-scoped internal-analysis read permission.
    can_view = can_view_vip_market(user, "internal")
    posts = ChannelPost.objects.filter(
        channel__slug="internal-analysis", channel__is_active=True,
        status=ChannelPost.Status.PUBLISHED,
        scope__in=(ChannelPost.Scope.DOLLAR, ChannelPost.Scope.GOLD,
                   ChannelPost.Scope.STOCK, ChannelPost.Scope.HOUSING,
                   ChannelPost.Scope.CAR),
        published_at__lte=timezone.now(),
    ).order_by("-published_at", "-id")[:3]
    return [{
        "id": post.pk,
        "title": _public_excerpt(post.title) if can_view else "تحلیل جدید بازار داخلی",
        "excerpt": _public_excerpt(post.body) if can_view else "تحلیل جدید بازار داخلی سوکانکس",
        "image": None,
        "scope": post.scope,
        "published_at": post.published_at,
        "can_view": can_view,
    } for post in posts]


class DashboardService:

    @staticmethod
    def get_dashboard(user):

        is_super_admin = (
            user.is_superuser
            or user.role == User.Role.SUPER_ADMIN
        )

        # VIP channel posts are created only through the server-to-server
        # ingestion API. Interactive trading-signal submission is legacy.
        can_submit_signals = False

        can_review_signals = (
            user.has_platform_permission(
                User.Permission.SIGNAL_REVIEW
            )
        )

        visible_signals = VIPSignalPost.objects.filter(is_active=True)
        allowed_channels = [market.upper() for market in ("crypto", "forex") if can_view_vip_market(user, market)]
        visible_signals = visible_signals.filter(channel__in=allowed_channels)
        recent_signals = []
        for channel in allowed_channels:
            recent_signals.extend(visible_signals.filter(channel=channel).order_by(
                "-published_at", "-created_at", "-id",
            )[:3])
        recent_signals.sort(key=lambda post: (post.published_at, post.created_at, post.pk), reverse=True)

        wallet = WalletService.get_wallet(user)
        broker = BrokerConnection.objects.filter(user=user).first()
        broker_connected = bool(broker and broker.status == BrokerConnection.Status.CONNECTED)
        personality_result = FinancialPersonalityAssessment.objects.filter(
            user=user, is_current=True
        ).first()

        published_articles = (
            ArticleService.published_articles(user)
        )

        published_videos = (
            VideoService.published_videos(user)
        )

        visible_notifications = (
            NotificationService.visible_notifications(user)
        )

        visible_chat_rooms = (
            ChatService.visible_rooms(user)
        )

        live_events = LiveEventService.live_now(user)

        upcoming_live_events = (
            LiveEventService.upcoming(user)
        )

        access_state = market_access_payload(user)

        return {
            "user": user,

            "access_level": user.access_level,

            "stats": {
                "wallet_balance": str(WalletService.balance_irt(wallet)),

                "wallet_balance_usd": str(wallet.balance_usd),

                "wallet_currency": wallet.currency,

                "signals": visible_signals.count(),

                "my_signals": 0,

                "pending_signals": 0,

                "articles": published_articles.count(),

                "videos": published_videos.count(),

                "notifications": (
                    visible_notifications.count()
                ),

                "unread_notifications": (
                    NotificationService.unread_count(user)
                ),

                "chat_rooms": (
                    visible_chat_rooms.count()
                ),

                "live_events": live_events.count(),

                "upcoming_live_events": (
                    upcoming_live_events.count()
                ),
            },

            "premium_subscription": WalletService.premium_subscription(user),

            "market_access_v2": access_state,

            "analytics_tracking": {"enabled": bool(settings.ANALYTICS_PAGE_VIEW_TRACKING_ENABLED)},

            "special_role": access_state.get("special_role"),

            "personality_result": personality_result,

            "capabilities": {
                "can_submit_signals": (
                    can_submit_signals
                ),

                "can_review_signals": (
                    can_review_signals
                ),

                "can_manage_content": (
                    user.has_platform_permission(
                        User.Permission.CONTENT_MANAGE
                    )
                ),

                "can_manage_users": (
                    user.has_platform_permission(
                        User.Permission.USER_MANAGE
                    )
                ),

                "can_manage_market_access": (
                    market_access_v2_enabled() and user_can_manage_market_access(user)
                ),

                "can_manage_sms_automation": bool(
                    user.is_superuser or user.role == User.Role.SUPER_ADMIN
                ),

                "can_teach_academy": (
                    user.has_platform_permission(
                        User.Permission.ACADEMY_TEACH
                    )
                    or user.has_platform_permission(
                        User.Permission.ACADEMY_MANAGE
                    )
                ),

                "can_manage_academy": (
                    user.has_platform_permission(
                        User.Permission.ACADEMY_MANAGE
                    )
                ),

                "can_manage_roles": (
                    user.has_platform_permission(
                        User.Permission.ROLE_MANAGE
                    )
                ),

                "can_manage_landing": (
                    user.has_platform_permission(
                        User.Permission.LANDING_MANAGE
                    )
                ),

                "can_manage_platform": (
                    user.has_platform_permission(
                        User.Permission.PLATFORM_SETTINGS_MANAGE
                    )
                ),

                "can_manage_ai_assistant": (
                    user.has_platform_permission(User.Permission.AI_ASSISTANT_MANAGE)
                    or user.has_platform_permission(User.Permission.PLATFORM_SETTINGS_MANAGE)
                ),

                "can_manage_internal_analysis": (
                    user.is_superuser
                    or user.role == User.Role.SUPER_ADMIN
                    or user.has_platform_permission(User.Permission.INTERNAL_ANALYSIS_MANAGE)
                    or (
                        user.role in (User.Role.ADMIN, User.Role.EMPLOYEE)
                        and user.has_platform_permission(User.Permission.CONTENT_MANAGE)
                    )
                ),
            },

            "finance": {
                "connected": broker_connected,
                "broker_connected": broker_connected,
                "balance": broker.balance if broker_connected else 0,
                "equity": broker.equity if broker_connected else 0,
                "currency": broker.currency if broker_connected else "USD",
                "chart": broker.chart if broker_connected else [0, 0, 0, 0, 0, 0, 0],
                "updated_at": broker.updated_at if broker else None,
            },

            "recent_signals": recent_signals,

            "vip_signal_previews": _vip_previews(user),

            "recent_internal_analysis": _internal_previews(user),

            "recent_articles": (
                published_articles[:5]
            ),

            "recent_videos": (
                published_videos[:5]
            ),

            "recent_notifications": (
                visible_notifications[:5]
            ),

            "chat_rooms": (
                visible_chat_rooms[:5]
            ),

            "live_events": live_events[:5],

            "upcoming_live_events": (
                upcoming_live_events[:5]
            ),
        }
