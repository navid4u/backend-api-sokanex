from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.conf import settings
from django.core import signing

from .models import Channel, ChannelPost


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
        self.channel_slug = slug
        self.user_id = payload.get("user_id")
        self.group_name = f"content_channel_{slug.replace('-', '_')}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def channel_event(self, event):
        if not await self.can_access(self.user_id, self.channel_slug):
            await self.close(code=4403)
            return
        payload = event["payload"]
        if (getattr(settings, "MARKET_ACCESS_V2_ENABLED", False)
                and self.channel_slug == "internal-analysis"
                and payload.get("type") != "post.deleted"):
            post_id = payload.get("data", {}).get("id")
            if not await self.can_view_internal_post(self.user_id, post_id):
                return
        await self.send_json(payload)

    @database_sync_to_async
    def can_view_internal_post(self, user_id, post_id):
        from django.utils import timezone
        from apps.accounts.models import User
        from apps.accounts.market_access import can_view_vip_market

        try:
            user = User.objects.get(pk=user_id, is_active=True)
            post = ChannelPost.objects.get(pk=post_id, channel__slug="internal-analysis")
        except (User.DoesNotExist, ChannelPost.DoesNotExist, TypeError, ValueError):
            return False
        if user.is_staff or user.role in (User.Role.SUPER_ADMIN, User.Role.SUPPORT,
                                         User.Role.ADMIN, User.Role.EMPLOYEE):
            return True
        return bool(
            post.status == ChannelPost.Status.PUBLISHED
            and post.published_at and post.published_at <= timezone.now()
            and can_view_vip_market(user, User.MarketType.INTERNAL)
            and (post.scope != ChannelPost.Scope.FOREX or can_view_vip_market(user, User.MarketType.FOREX))
        )

    @database_sync_to_async
    def can_access(self, user_id, slug):
        from apps.accounts.models import User
        from apps.accounts.market_access import can_access_gold_features, can_view_vip_market, market_access_v2_enabled
        try:
            user = User.objects.get(pk=user_id, is_active=True)
            channel = Channel.objects.get(slug=slug, is_active=True)
        except (User.DoesNotExist, Channel.DoesNotExist):
            return False
        if market_access_v2_enabled():
            if user.is_staff or user.role in (User.Role.SUPPORT, User.Role.EMPLOYEE, User.Role.ADMIN, User.Role.SUPER_ADMIN):
                return True
            if slug in {"vip-signals", "internal-analysis"}:
                return (can_view_vip_market(user, User.MarketType.INTERNAL)
                        if slug == "internal-analysis" else can_access_gold_features(user))
        return user.is_staff or user.effective_access_level >= channel.min_access_level
