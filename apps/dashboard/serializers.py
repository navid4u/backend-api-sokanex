from rest_framework import serializers

from apps.accounts.serializers import (
    UserSerializer,
)
from apps.articles.serializers import (
    ArticleListSerializer,
)
from apps.chat.serializers import (
    ChatRoomSerializer,
)
from apps.livestream.serializers import (
    LiveEventListSerializer,
)
from apps.notifications.serializers import (
    NotificationSerializer,
)
from apps.signals.serializers import (
    SignalListSerializer,
)
from apps.videos.serializers import (
    VideoListSerializer,
)


class DashboardStatsSerializer(
    serializers.Serializer
):

    wallet_balance = serializers.DecimalField(
        max_digits=20,
        decimal_places=8,
    )

    wallet_balance_usd = serializers.DecimalField(max_digits=18, decimal_places=2)

    wallet_currency = serializers.CharField(
        max_length=10,
    )

    signals = serializers.IntegerField(
        min_value=0,
    )

    my_signals = serializers.IntegerField(
        min_value=0,
    )

    pending_signals = serializers.IntegerField(
        min_value=0,
    )

    articles = serializers.IntegerField(
        min_value=0,
    )

    videos = serializers.IntegerField(
        min_value=0,
    )

    notifications = serializers.IntegerField(
        min_value=0,
    )

    unread_notifications = (
        serializers.IntegerField(
            min_value=0,
        )
    )

    chat_rooms = serializers.IntegerField(
        min_value=0,
    )

    live_events = serializers.IntegerField(
        min_value=0,
    )

    upcoming_live_events = (
        serializers.IntegerField(
            min_value=0,
        )
    )


class DashboardCapabilitiesSerializer(
    serializers.Serializer
):

    can_submit_signals = (
        serializers.BooleanField()
    )

    can_review_signals = (
        serializers.BooleanField()
    )

    can_manage_content = (
        serializers.BooleanField()
    )

    can_manage_users = (
        serializers.BooleanField()
    )

    can_teach_academy = serializers.BooleanField()

    can_manage_academy = serializers.BooleanField()

    can_manage_roles = serializers.BooleanField()

    can_manage_platform = serializers.BooleanField()

    can_manage_landing = serializers.BooleanField()

    can_manage_internal_analysis = serializers.BooleanField()

    can_manage_ai_assistant = serializers.BooleanField()


class DashboardFinanceSerializer(serializers.Serializer):
    connected = serializers.BooleanField()
    broker_connected = serializers.BooleanField()
    balance = serializers.DecimalField(max_digits=20, decimal_places=2)
    equity = serializers.DecimalField(max_digits=20, decimal_places=2)
    currency = serializers.CharField()
    chart = serializers.ListField(child=serializers.DecimalField(max_digits=20, decimal_places=2))
    updated_at = serializers.DateTimeField(allow_null=True)


class DashboardSerializer(
    serializers.Serializer
):

    user = UserSerializer()

    stats = DashboardStatsSerializer()

    premium_subscription = serializers.DictField()

    capabilities = (
        DashboardCapabilitiesSerializer()
    )

    finance = DashboardFinanceSerializer()

    recent_signals = SignalListSerializer(
        many=True,
    )

    recent_articles = ArticleListSerializer(
        many=True,
    )

    recent_videos = VideoListSerializer(
        many=True,
    )

    recent_notifications = (
        NotificationSerializer(
            many=True,
        )
    )

    chat_rooms = ChatRoomSerializer(
        many=True,
    )

    live_events = LiveEventListSerializer(
        many=True,
    )

    upcoming_live_events = (
        LiveEventListSerializer(
            many=True,
        )
    )
