from django.db.models import (
    Count,
    Exists,
    OuterRef,
    Q,
)

from rest_framework.exceptions import (
    PermissionDenied,
    ValidationError,
)

from apps.accounts.models import User

from .models import (
    ChatRoom,
    Message,
    RoomMembership,
)


class ChatService:

    @staticmethod
    def visible_rooms(user):
        membership = (
            RoomMembership.objects.filter(
                room_id=OuterRef("pk"),
                user=user,
            )
        )

        return (
            ChatRoom.objects.filter(
                Q(is_public=True)
                | Q(members=user),
                is_active=True,
            )
            .annotate(
                member_count=Count(
                    "members",
                    distinct=True,
                ),
                is_member=Exists(membership),
            )
            .distinct()
        )

    @staticmethod
    def create_room(serializer, creator):
        room = serializer.save(
            created_by=creator
        )

        RoomMembership.objects.create(
            room=room,
            user=creator,
            role=RoomMembership.Role.ADMIN,
        )

        return room

    @staticmethod
    def join_room(room, user):
        if not room.is_public:
            raise PermissionDenied(
                "This room is private."
            )

        membership, _ = (
            RoomMembership.objects.get_or_create(
                room=room,
                user=user,
            )
        )

        return membership

    @staticmethod
    def leave_room(room, user):
        membership = (
            RoomMembership.objects.filter(
                room=room,
                user=user,
            ).first()
        )

        if not membership:
            raise ValidationError(
                {
                    "room": (
                        "You are not a member "
                        "of this room."
                    )
                }
            )

        if (
            membership.role
            == RoomMembership.Role.ADMIN
        ):
            raise ValidationError(
                {
                    "room": (
                        "Room admin cannot leave "
                        "before assigning another admin."
                    )
                }
            )

        membership.delete()

    @staticmethod
    def ensure_member(room, user):
        exists = (
            RoomMembership.objects.filter(
                room=room,
                user=user,
            ).exists()
        )

        if not exists:
            raise PermissionDenied(
                "You must join this room first."
            )

    @staticmethod
    def room_messages(room):
        return (
            Message.objects.filter(room=room)
            .select_related(
                "sender",
                "reply_to",
                "reply_to__sender",
            )
        )

    @staticmethod
    def create_message(
        serializer,
        room,
        sender,
    ):
        reply_to = (
            serializer.validated_data.get(
                "reply_to"
            )
        )

        if (
            reply_to
            and reply_to.room_id != room.id
        ):
            raise ValidationError(
                {
                    "reply_to": (
                        "Reply message must belong "
                        "to the same room."
                    )
                }
            )

        return serializer.save(
            room=room,
            sender=sender,
        )

    @staticmethod
    def delete_message(message, user):
        can_moderate = (
            RoomMembership.objects.filter(
                room=message.room,
                user=user,
                role__in=[
                    RoomMembership.Role.ADMIN,
                    RoomMembership.Role.MODERATOR,
                ],
            ).exists()
        )

        is_staff_role = (
            user.is_superuser
            or user.role in [
                User.Role.EMPLOYEE,
                User.Role.ADMIN,
                User.Role.SUPER_ADMIN,
            ]
        )

        if (
            message.sender_id != user.id
            and not can_moderate
            and not is_staff_role
        ):
            raise PermissionDenied(
                "You cannot delete this message."
            )

        message.is_deleted = True
        message.text = ""

        if message.attachment:
            message.attachment.delete(
                save=False
            )
            message.attachment = None

        message.save(
            update_fields=[
                "is_deleted",
                "text",
                "attachment",
                "updated_at",
            ]
        )