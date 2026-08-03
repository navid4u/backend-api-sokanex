from django.urls import path

from apps.chat.consumers import SupportConsumer
from apps.content_channels.consumers import ContentChannelConsumer
from apps.livestream.consumers import LivestreamConsumer

websocket_urlpatterns = [
    path("ws/channels/<slug:slug>/", ContentChannelConsumer.as_asgi()),
    path("ws/support/<int:thread_id>/", SupportConsumer.as_asgi()),
    path("ws/livestream/<slug:slug>/", LivestreamConsumer.as_asgi()),
]
