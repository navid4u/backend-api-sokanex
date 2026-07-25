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


class DashboardSerializer(
    serializers.Serializer
):

    user = UserSerializer()

    stats = DashboardStatsSerializer()

    capabilities = (
        DashboardCapabilitiesSerializer()
    )

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
