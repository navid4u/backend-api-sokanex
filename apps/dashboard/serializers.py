from rest_framework import serializers

from apps.accounts.serializers import UserSerializer
from apps.signals.serializers import SignalListSerializer
from apps.articles.serializers import ArticleListSerializer
from apps.videos.serializers import VideoListSerializer
from apps.notifications.serializers import NotificationSerializer
from apps.chat.serializers import ChatRoomSerializer
from apps.livestream.serializers import LiveEventListSerializer


class DashboardSerializer(serializers.Serializer):

    user = UserSerializer()

    stats = serializers.DictField()

    capabilities = serializers.DictField()

    recent_signals = SignalListSerializer(
        many=True,
    )

    recent_articles = ArticleListSerializer(
        many=True,
    )

    recent_videos = VideoListSerializer(
        many=True,
    )

    recent_notifications = NotificationSerializer(
        many=True,
    )

    chat_rooms = ChatRoomSerializer(
        many=True,
    )

    live_events = LiveEventListSerializer(
        many=True,
    )

    upcoming_live_events = LiveEventListSerializer(
        many=True,
    )