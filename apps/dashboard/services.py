from apps.accounts.models import User
from apps.signals.models import Signal, SignalStatus
from apps.signals.services import SignalService
from apps.wallet.services import WalletService
from apps.articles.services import ArticleService
from apps.videos.services import VideoService
from apps.notifications.services import NotificationService
from apps.chat.services import ChatService
from apps.livestream.services import LiveEventService
from apps.accounts.models import BrokerConnection


class DashboardService:

    @staticmethod
    def get_dashboard(user):

        is_super_admin = (
            user.is_superuser
            or user.role == User.Role.SUPER_ADMIN
        )

        can_submit_signals = (
            user.has_platform_permission(
                User.Permission.SIGNAL_SUBMIT
            )
        )

        can_review_signals = (
            user.has_platform_permission(
                User.Permission.SIGNAL_REVIEW
            )
        )

        approved_signals = SignalService.list_signals(user)

        recent_signals = approved_signals.select_related(
            "created_by"
        )[:5]

        wallet = WalletService.get_wallet(user)
        broker = BrokerConnection.objects.filter(user=user).first()
        broker_connected = bool(broker and broker.status == BrokerConnection.Status.CONNECTED)

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

        return {
            "user": user,

            "stats": {
                "wallet_balance": str(wallet.balance),

                "wallet_currency": wallet.currency,

                "signals": approved_signals.count(),

                "my_signals": (
                    user.signals.count()
                    if can_submit_signals
                    else 0
                ),

                "pending_signals": (
                    Signal.objects.filter(
                        status=SignalStatus.PENDING
                    ).count()
                    if can_review_signals
                    else 0
                ),

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
