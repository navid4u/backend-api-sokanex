from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.conf import settings
from django.core import signing

from .models import LiveEvent


class LivestreamConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        ticket = parse_qs(self.scope["query_string"].decode()).get("ticket", [""])[0]
        try:
            payload = signing.loads(ticket, salt="live-ws-ticket", max_age=settings.CHANNEL_TICKET_TTL_SECONDS)
        except signing.BadSignature:
            await self.close(code=4401)
            return
        slug = self.scope["url_route"]["kwargs"]["slug"]
        event_id = await self.event_id(slug, payload.get("event_id"), payload.get("user_id"))
        if not event_id:
            await self.close(code=4403)
            return
        self.group_name = f"livestream_{event_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def live_event(self, event):
        await self.send_json(event["payload"])

    @database_sync_to_async
    def event_id(self, slug, event_id, user_id):
        from apps.accounts.models import User
        try:
            user = User.objects.get(pk=user_id, is_active=True)
            event = LiveEvent.objects.get(pk=event_id, slug=slug, is_active=True)
        except (User.DoesNotExist, LiveEvent.DoesNotExist):
            return None
        if user.is_staff or user.access_level in event.allowed_levels:
            return event.pk
        return None
