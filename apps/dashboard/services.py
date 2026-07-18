from apps.accounts.models import User
from apps.signals.models import Signal, SignalStatus
from apps.wallet.services import WalletService
from apps.articles.services import ArticleService
from apps.videos.services import VideoService
from apps.notifications.services import NotificationService
from apps.chat.services import ChatService
from apps.livestream.services import LiveEventService


class DashboardService:

    @staticmethod
    def get_dashboard(user):

        is_super_admin = (
            user.is_superuser
            or user.role == User.Role.SUPER_ADMIN
        )

        can_submit_signals = (
            is_super_admin
            or user.role == User.Role.TRADER
        )

        can_review_signals = (
            is_super_admin
            or user.role in [
                User.Role.EMPLOYEE,
                User.Role.ADMIN,
            ]
        )

        approved_signals = Signal.objects.filter(
            status=SignalStatus.APPROVED
        )

        recent_signals = approved_signals.select_related(
            "created_by"
        )[:5]

        wallet = WalletService.get_wallet(user)

        published_articles = (
            ArticleService.published_articles()
        )

        published_videos = (
            VideoService.published_videos()
        )

        visible_notifications = (
            NotificationService.visible_notifications(user)
        )

        visible_chat_rooms = (
            ChatService.visible_rooms(user)
        )

        live_events = LiveEventService.live_now()

        upcoming_live_events = (
            LiveEventService.upcoming()
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
                    can_review_signals
                ),

                "can_manage_users": (
                    is_super_admin
                ),
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