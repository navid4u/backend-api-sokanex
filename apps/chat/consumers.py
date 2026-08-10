from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.conf import settings
from django.core import signing

from .models import SupportThread


class SupportConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        ticket = parse_qs(self.scope["query_string"].decode()).get("ticket", [""])[0]
        try:
            payload = signing.loads(ticket, salt="support-ws-ticket", max_age=settings.CHANNEL_TICKET_TTL_SECONDS)
        except signing.BadSignature:
            await self.close(code=4401)
            return
        thread_id = self.scope["url_route"]["kwargs"]["thread_id"]
        if payload.get("thread_id") != thread_id or not await self.can_access(payload.get("user_id"), thread_id):
            await self.close(code=4403)
            return
        self.group_name = f"support_{thread_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def support_event(self, event):
        await self.send_json(event["payload"])

    @database_sync_to_async
    def can_access(self, user_id, thread_id):
        from apps.accounts.models import User
        try:
            user = User.objects.get(pk=user_id, is_active=True)
            thread = SupportThread.objects.get(pk=thread_id)
        except (User.DoesNotExist, SupportThread.DoesNotExist):
            return False
        return thread.user_id == user.id or user.username == "support"
