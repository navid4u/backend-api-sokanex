from rest_framework import serializers
from django.urls import reverse
import re
import json
from pathlib import Path
from django.db import transaction
from django.utils.html import strip_tags

from common.validators import (
    validate_attachment_upload,
    validate_image_upload,
    validate_video_upload,
)

from .models import (
    ChatRoom, Message, PostComment, PostReaction, PostReport, PostPoll, PollOption,
    SupportMessage, SupportThread, TraderPost, UserFollow,
)
from .services import ChatService


class ChatRoomSerializer(
    serializers.ModelSerializer
):

    member_count = serializers.IntegerField(
        read_only=True,
    )

    is_member = serializers.BooleanField(
        read_only=True,
    )
    online_count = serializers.SerializerMethodField()
    presence_enabled = serializers.SerializerMethodField()
    can_invite = serializers.SerializerMethodField()
    manager = serializers.SerializerMethodField()

    def get_online_count(self, obj):
        from .community import room_online_ids
        client = self._presence_client()
        if client is None:
            return None
        ids = room_online_ids(obj, client)
        return len(ids) if ids is not None else None

    def _presence_client(self):
        from .community import _redis
        request = self.context.get("request")
        if request is None:
            return None
        if not hasattr(request, "_chat_presence_client"):
            request._chat_presence_client = _redis()
        return request._chat_presence_client

    def get_presence_enabled(self, obj):
        return self._presence_client() is not None

    def get_can_invite(self, obj):
        from .community import can_invite_to_room
        request = self.context.get("request")
        annotated = getattr(obj, "can_invite_flag", None)
        if annotated is not None:
            return bool(obj.is_active and annotated)
        return bool(request and can_invite_to_room(obj, request.user))

    def get_manager(self, obj):
        if not obj.manager_id:
            return None
        serializer = SocialUserSerializer(context=self.context)
        return {"id": obj.manager_id, "display_name": serializer.get_display_name(obj.manager)}

    class Meta:
        model = ChatRoom

        fields = (
            "id",
            "name",
            "slug",
            "description",
            "image",
            "is_public",
            "is_active",
            "market",
            "topic",
            "manager",
            "member_count",
            "is_member",
            "online_count",
            "presence_enabled",
            "can_invite",
            "created_at",
        )


class ChatRoomWriteSerializer(
    serializers.ModelSerializer
):

    manager_id = serializers.IntegerField(required=False, write_only=True, allow_null=True)

    class Meta:
        model = ChatRoom

        fields = (
            "id",
            "name",
            "slug",
            "description",
            "image",
            "is_public",
            "is_active",
            "market",
            "topic",
            "manager_id",
            "created_at",
            "updated_at",
        )

        read_only_fields = (
            "id",
            "slug",
            "created_at",
            "updated_at",
        )

    def validate_image(self, value):
        return validate_image_upload(
            value,
            max_size_mb=5,
            file_label="Room image",
        )

    def validate_market(self, value):
        if value not in TraderPost.Market.values:
            raise serializers.ValidationError("Unknown market.")
        return value

    def validate_topic(self, value):
        return strip_tags(value).strip()

    def validate_manager_id(self, value):
        if value is None:
            return value
        from apps.accounts.models import User
        if not User.objects.filter(pk=value, is_active=True).exists():
            raise serializers.ValidationError("Active manager not found.")
        return value

    def create(self, validated_data):
        from apps.accounts.models import User
        from .models import RoomMembership
        manager_id = validated_data.pop("manager_id", None)
        with transaction.atomic():
            room = super().create(validated_data)
            if manager_id:
                room.manager_id = manager_id
                room.save(update_fields=["manager", "updated_at"])
                RoomMembership.objects.update_or_create(room=room, user_id=manager_id, defaults={"role": RoomMembership.Role.ADMIN})
        return room

    def update(self, instance, validated_data):
        from .models import RoomMembership
        manager_id = validated_data.pop("manager_id", serializers.empty)
        with transaction.atomic():
            room = super().update(instance, validated_data)
            if manager_id is not serializers.empty and manager_id is not None:
                room.manager_id = manager_id
                room.save(update_fields=["manager", "updated_at"])
                RoomMembership.objects.update_or_create(room=room, user_id=manager_id, defaults={"role": RoomMembership.Role.ADMIN})
        return room


class MessageSerializer(
    serializers.ModelSerializer
):

    sender = serializers.SerializerMethodField()

    reply_to_text = serializers.CharField(
        source="reply_to.text",
        read_only=True,
        allow_null=True,
    )

    can_delete = serializers.SerializerMethodField()
    is_mine = serializers.SerializerMethodField()
    sender_display_name = serializers.SerializerMethodField()

    class Meta:
        model = Message

        fields = (
            "id",
            "sender",
            "sender_display_name",
            "is_mine",
            "text",
            "attachment",
            "reply_to",
            "reply_to_text",
            "is_deleted",
            "can_delete",
            "created_at",
            "updated_at",
        )

        read_only_fields = (
            "id",
            "sender",
            "sender_display_name",
            "is_mine",
            "is_deleted",
            "can_delete",
            "created_at",
            "updated_at",
        )

    def get_can_delete(self, obj) -> bool:
        request = self.context.get("request")

        if (
            request is None
            or not request.user.is_authenticated
            or obj.is_deleted
        ):
            return False

        return ChatService.can_delete_message(
            obj,
            request.user,
        )

    def get_is_mine(self, obj) -> bool:
        request = self.context.get("request")
        return bool(
            request is not None
            and request.user.is_authenticated
            and obj.sender_id == request.user.pk
        )

    def get_sender_display_name(self, obj) -> str:
        if obj.sender_id is None:
            return "عضو اتاق"
        name = obj.sender.get_full_name().strip()
        digits = re.sub(r"\D", "", name)
        if not name or len(digits) >= 10:
            return "عضو اتاق"
        return name

    def get_sender(self, obj):
        if obj.sender_id is None:
            return None
        username = obj.sender.username or ""
        return self.get_sender_display_name(obj) if len(re.sub(r"\D", "", username)) >= 10 else username

    def validate(self, attrs):
        if (
            not attrs.get("text")
            and not attrs.get("attachment")
        ):
            raise serializers.ValidationError(
                "A message must contain "
                "text or an attachment."
            )

        return attrs

    def validate_attachment(self, value):
        return validate_attachment_upload(
            value,
            max_size_mb=20,
            file_label="Chat attachment",
        )


class SocialUserSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    display_name = serializers.SerializerMethodField()
    avatar = serializers.ImageField(read_only=True)
    posts_count = serializers.SerializerMethodField()
    first_name = serializers.SerializerMethodField()
    last_name = serializers.SerializerMethodField()
    bio = serializers.SerializerMethodField()
    specialty = serializers.SerializerMethodField()
    activity_markets = serializers.SerializerMethodField()
    followers_count = serializers.SerializerMethodField()
    following_count = serializers.SerializerMethodField()
    is_following = serializers.SerializerMethodField()
    is_active_analyst = serializers.SerializerMethodField()
    is_verified = serializers.SerializerMethodField()
    credibility_score = serializers.SerializerMethodField()

    def get_bio(self, obj):
        bio = getattr(getattr(obj, "profile_details", None), "bio", "")
        bio = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "", strip_tags(bio))
        return re.sub(r"(?:\+?98|0)?9\d{9}", "", bio).strip()

    def _safe_name(self, value):
        value = (value or "").strip()
        digits = re.sub(r"\D", "", value)
        return value[:100] if len(digits) < 10 else ""

    def get_first_name(self, obj):
        return self._safe_name(obj.first_name)

    def get_last_name(self, obj):
        return self._safe_name(obj.last_name)

    def _analyst(self, obj):
        return getattr(obj, "social_analyst_profile", None)

    def get_specialty(self, obj):
        return getattr(self._analyst(obj), "specialty", "")

    def get_activity_markets(self, obj):
        request = self.context.get("request")
        if not request:
            return []
        lookup = getattr(request, "_social_activity_markets", None)
        if lookup is not None and obj.pk in lookup:
            return lookup[obj.pk]
        from .views import social_posts_for
        return list(social_posts_for(request.user).filter(author=obj).values_list("market", flat=True).distinct())

    def get_posts_count(self, obj):
        annotated = getattr(obj, "visible_posts_count", None)
        if annotated is not None:
            return annotated
        request = self.context.get("request")
        if not request:
            return 0
        from .views import social_posts_for
        return social_posts_for(request.user).filter(author=obj).count()

    def get_followers_count(self, obj):
        return getattr(obj, "followers_count", None) if getattr(obj, "followers_count", None) is not None else obj.follower_relations.count()

    def get_following_count(self, obj):
        return getattr(obj, "following_count", None) if getattr(obj, "following_count", None) is not None else obj.following_relations.count()

    def get_is_following(self, obj):
        annotated = getattr(obj, "followed_by_viewer", None)
        if annotated is not None:
            return annotated
        request = self.context.get("request")
        return bool(request and request.user.is_authenticated and UserFollow.objects.filter(follower=request.user, following=obj).exists())

    def get_is_active_analyst(self, obj):
        return bool(getattr(self._analyst(obj), "is_active_analyst", False))

    def get_is_verified(self, obj):
        return bool(getattr(self._analyst(obj), "is_verified", False))

    def get_credibility_score(self, obj):
        return getattr(self._analyst(obj), "credibility_score", 0)

    def get_display_name(self, obj):
        name = " ".join(part for part in (self.get_first_name(obj), self.get_last_name(obj)) if part)
        digits = re.sub(r"\D", "", name)
        if name and not (len(digits) >= 10 and len(digits) >= len(name.strip()) - 3):
            return name[:100]
        return f"کاربر سوکانکس {obj.pk}"


class SupportUserSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    username = serializers.CharField(read_only=True)
    first_name = serializers.CharField(read_only=True)
    last_name = serializers.CharField(read_only=True)
    phone = serializers.CharField(read_only=True, allow_null=True)
    avatar = serializers.ImageField(read_only=True, allow_null=True)


class PostCommentSerializer(serializers.ModelSerializer):
    author = serializers.SerializerMethodField()
    reply_to = serializers.PrimaryKeyRelatedField(source="parent", queryset=PostComment.objects.filter(is_deleted=False), required=False, allow_null=True)
    reply_to_text = serializers.SerializerMethodField()

    def get_reply_to_text(self, obj):
        return strip_tags(obj.parent.text) if obj.parent_id and not obj.parent.is_deleted else None

    def get_author(self, obj):
        request = self.context.get("request")
        lookup = getattr(request, "_social_author_lookup", {}) if request else {}
        return SocialUserSerializer(lookup.get(obj.author_id, obj.author), context=self.context).data

    class Meta:
        model = PostComment
        fields = ("id", "post", "author", "parent", "reply_to", "reply_to_text", "text", "is_edited", "created_at", "updated_at")
        read_only_fields = ("id", "post", "author", "is_edited", "created_at", "updated_at")

    def validate_text(self, value):
        value = strip_tags(value).strip()
        if not value:
            raise serializers.ValidationError("Comment cannot be empty.")
        return value

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["text"] = strip_tags(instance.text)
        return data


class TraderPostSerializer(serializers.ModelSerializer):
    author = serializers.SerializerMethodField()
    image = serializers.ImageField(required=False, allow_null=True, use_url=False)
    video = serializers.FileField(required=False, allow_null=True, use_url=False)
    reactions_count = serializers.IntegerField(read_only=True)
    comments_count = serializers.IntegerField(read_only=True)
    is_reacted = serializers.BooleanField(read_only=True)
    is_saved = serializers.BooleanField(read_only=True)
    useful_count = serializers.IntegerField(read_only=True, default=0)
    is_useful = serializers.BooleanField(read_only=True, default=False)
    poll = serializers.JSONField(required=False, allow_null=True, write_only=True)

    class Meta:
        model = TraderPost
        fields = (
            "id", "author", "text", "image", "video", "visibility", "market", "post_type", "poll", "useful_count", "is_useful",
            "is_edited", "reactions_count", "comments_count", "is_reacted",
            "is_saved", "created_at", "updated_at",
        )
        read_only_fields = (
            "id", "author", "is_edited", "reactions_count", "comments_count",
            "is_reacted", "is_saved", "useful_count", "is_useful", "created_at", "updated_at",
        )

    def validate_text(self, value):
        value = strip_tags(value).strip()
        if len(value) > 10000:
            raise serializers.ValidationError("Text may contain at most 10000 characters.")
        return value

    def get_author(self, obj):
        request = self.context.get("request")
        lookup = getattr(request, "_social_author_lookup", {}) if request else {}
        author = lookup.get(obj.author_id, obj.author)
        return SocialUserSerializer(author, context=self.context).data

    def validate_poll(self, value):
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except (TypeError, ValueError):
                raise serializers.ValidationError("Poll must be valid JSON.") from None
        if value is None:
            return value
        if not isinstance(value, dict):
            raise serializers.ValidationError("Poll must be an object.")
        question = strip_tags(str(value.get("question", ""))).strip()
        options = value.get("options")
        if not question or len(question) > 250 or not isinstance(options, list) or not 2 <= len(options) <= 6:
            raise serializers.ValidationError("A poll needs a question and 2 to 6 options.")
        texts = []
        for option in options:
            if not isinstance(option, dict):
                raise serializers.ValidationError("Each option must contain text.")
            text = strip_tags(str(option.get("text", ""))).strip()
            if not text or len(text) > 120 or text.casefold() in {item.casefold() for item in texts}:
                raise serializers.ValidationError("Options must be distinct and at most 120 characters.")
            texts.append(text)
        return {"question": question, "options": texts}

    def validate_image(self, value):
        value = validate_image_upload(value, max_size_mb=10, file_label="Post image")
        from PIL import Image, UnidentifiedImageError
        try:
            value.seek(0)
            with Image.open(value) as image:
                image.verify()
        except (OSError, ValueError, UnidentifiedImageError):
            raise serializers.ValidationError("Image content is invalid.") from None
        finally:
            value.seek(0)
        return value

    def validate_video(self, value):
        value = validate_video_upload(value, max_size_mb=200, file_label="Post video")
        value.seek(0)
        header = value.read(16)
        value.seek(0)
        suffix = Path(value.name).suffix.lower()
        if (suffix in (".mp4", ".mov") and header[4:8] != b"ftyp") or (suffix in (".webm", ".mkv") and not header.startswith(b"\x1a\x45\xdf\xa3")):
            raise serializers.ValidationError("Video content does not match its format.")
        return value

    def validate(self, attrs):
        if self.instance is None and not self.initial_data.get("market"):
            raise serializers.ValidationError({"market": "This field is required."})
        if self.instance is None and attrs.get("post_type") == TraderPost.Type.POLL and not attrs.get("poll"):
            raise serializers.ValidationError({"poll": "A poll question and options are required."})
        if self.instance is None and attrs.get("post_type") != TraderPost.Type.POLL and attrs.get("poll"):
            raise serializers.ValidationError({"poll": "Only POLL posts can have poll data."})
        if self.instance is not None and "poll" in attrs:
            raise serializers.ValidationError({"poll": "Poll options cannot be changed."})
        if self.instance is not None and "post_type" in attrs and attrs["post_type"] != self.instance.post_type:
            raise serializers.ValidationError({"post_type": "Post type cannot be changed after publication."})
        text = attrs.get("text", getattr(self.instance, "text", ""))
        image = attrs.get("image", getattr(self.instance, "image", None))
        video = attrs.get("video", getattr(self.instance, "video", None))
        if not text and not image and not video and attrs.get("post_type", getattr(self.instance, "post_type", "")) != TraderPost.Type.POLL:
            raise serializers.ValidationError("A post must contain text, image, or video.")
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        from .community import sync_post_hashtags
        poll_data = validated_data.pop("poll", None)
        post = super().create(validated_data)
        if poll_data:
            poll = PostPoll.objects.create(post=post, question=poll_data["question"])
            PollOption.objects.bulk_create([PollOption(poll=poll, text=text, position=index) for index, text in enumerate(poll_data["options"])])
        sync_post_hashtags(post)
        return post

    @transaction.atomic
    def update(self, instance, validated_data):
        from .community import sync_post_hashtags
        post = super().update(instance, validated_data)
        if "text" in validated_data:
            sync_post_hashtags(post)
        return post

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["text"] = strip_tags(instance.text)
        from .community import poll_response
        request = self.context.get("request")
        data["poll"] = poll_response(instance, request.user, request) if request and instance.post_type == TraderPost.Type.POLL else None
        for kind in ("image", "video"):
            path = reverse("social-post-media", args=[instance.pk, kind]) if getattr(instance, kind) else None
            if path and request and request.get_host().split(":", 1)[0] == "api.sokanex.com":
                data[kind] = f"https://api.sokanex.com{path}"
            else:
                data[kind] = request.build_absolute_uri(path) if path and request else path
        return data


class PostReactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = PostReaction
        fields = ("reaction_type",)


class PostReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = PostReport
        fields = ("id", "post", "reason", "status", "created_at")
        read_only_fields = ("id", "post", "status", "created_at")


class FollowSerializer(serializers.ModelSerializer):
    following = SocialUserSerializer(read_only=True)

    class Meta:
        model = UserFollow
        fields = ("id", "following", "created_at")
        read_only_fields = fields


class SupportThreadSerializer(serializers.ModelSerializer):
    slug = serializers.CharField(read_only=True)
    user = SupportUserSerializer(read_only=True)
    assigned_to = SupportUserSerializer(read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    unread_count = serializers.SerializerMethodField()
    last_message = serializers.SerializerMethodField()

    class Meta:
        model = SupportThread
        fields = ("id", "slug", "user", "assigned_to", "status", "status_display", "priority", "subject", "unread_count", "last_message", "last_message_at", "created_at", "updated_at", "closed_at")
        read_only_fields = fields

    def get_unread_count(self, obj) -> int:
        request = self.context.get("request")
        if not request:
            return 0
        annotated = getattr(obj, "unread_count_value", None)
        if annotated is not None:
            return annotated
        return obj.messages.filter(is_read=False).exclude(sender=request.user).count()

    def get_last_message(self, obj) -> dict | None:
        messages = getattr(obj, "prefetched_latest_messages", None)
        message = messages[0] if messages else obj.messages.order_by("-created_at", "-id").first()
        if not message:
            return None
        return {"id": message.id, "text": message.text, "created_at": message.created_at}


class SupportThreadUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = SupportThread
        fields = ("status", "priority", "subject")


class SupportMessageSerializer(serializers.ModelSerializer):
    sender = SupportUserSerializer(read_only=True)
    sender_username = serializers.CharField(source="sender.username", read_only=True)
    is_mine = serializers.SerializerMethodField()

    class Meta:
        model = SupportMessage
        fields = ("id", "sender", "sender_username", "text", "attachment", "is_mine", "is_read", "created_at", "updated_at", "delivered_at", "read_at")
        read_only_fields = ("id", "sender", "sender_username", "is_mine", "is_read", "created_at", "updated_at", "delivered_at", "read_at")

    def get_is_mine(self, obj) -> bool:
        request = self.context.get("request")
        return bool(request and obj.sender_id == request.user.id)

    def validate_attachment(self, value):
        return validate_attachment_upload(value, max_size_mb=20, file_label="Support attachment")

    def validate_text(self, value):
        from django.utils.html import strip_tags
        return strip_tags(value).strip()

    def validate(self, attrs):
        if not attrs.get("text") and not attrs.get("attachment"):
            raise serializers.ValidationError("A support message needs text or an attachment.")
        return attrs
