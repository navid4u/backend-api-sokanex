from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.conf import settings
from django.core import signing

from .models import Channel


class ContentChannelConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        ticket = parse_qs(self.scope["query_string"].decode()).get("ticket", [""])[0]
        try:
            payload = signing.loads(ticket, salt="channel-ws-ticket", max_age=settings.CHANNEL_TICKET_TTL_SECONDS)
        except signing.BadSignature:
            await self.close(code=4401)
            return
        slug = self.scope["url_route"]["kwargs"]["slug"]
        if payload.get("channel") != slug or not await self.can_access(payload.get("user_id"), slug):
            await self.close(code=4403)
            return
        self.group_name = f"content_channel_{slug.replace('-', '_')}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def channel_event(self, event):
        await self.send_json(event["payload"])

    @database_sync_to_async
    def can_access(self, user_id, slug):
        from apps.accounts.models import User
        try:
            user = User.objects.get(pk=user_id, is_active=True)
            channel = Channel.objects.get(slug=slug, is_active=True)
        except (User.DoesNotExist, Channel.DoesNotExist):
            return False
        return user.is_staff or user.access_level >= channel.min_access_level
