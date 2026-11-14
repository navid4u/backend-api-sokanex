"""Additive community endpoints; all object lookups use the existing visibility policy."""

from datetime import timedelta
from urllib.parse import quote
from decouple import config

from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.html import strip_tags
from rest_framework import status
from rest_framework.exceptions import PermissionDenied, ValidationError, APIException
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.generics import ListAPIView

from apps.accounts.models import User
from common.pagination import DefaultPagination
from common.permissions import IsEmployee
from .community import (
    _redis, can_invite_to_room, heartbeat, poll_response,
    queue_social_notification, room_online_ids,
)
from .models import (
    ChatRoom, CommentReport, PollOption, PollVote, PostComment, PostHashtag,
    PostPoll, PostReport, PostUseful, RoomInvitation, RoomMembership,
    SocialAnalystProfile, SocialReportAudit, TraderPost,
)
from .serializers import ChatRoomSerializer, SocialUserSerializer
from .services import ChatService
from .throttles import SocialWriteThrottle, SocialReportThrottle, RoomInviteThrottle
from .views import can_moderate_social, social_posts_for, social_users_for


class Conflict(APIException):
    status_code = 409
    default_detail = "Conflicting action."


class PresenceUnavailable(APIException):
    status_code = 503
    default_detail = "Presence is temporarily unavailable."


class PostUsefulView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [SocialWriteThrottle]

    def _post(self, request, pk):
        return get_object_or_404(social_posts_for(request.user), pk=pk)

    def post(self, request, pk):
        post = self._post(request, pk)
        PostUseful.objects.get_or_create(post=post, user=request.user)
        return Response({"is_useful": True, "useful_count": PostUseful.objects.filter(post=post).count()})

    def delete(self, request, pk):
        post = self._post(request, pk)
        PostUseful.objects.filter(post=post, user=request.user).delete()
        return Response({"is_useful": False, "useful_count": PostUseful.objects.filter(post=post).count()})


class PollVoteView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [SocialWriteThrottle]

    def post(self, request, pk):
        post = get_object_or_404(social_posts_for(request.user), pk=pk, post_type=TraderPost.Type.POLL)
        try:
            option_id = int(request.data.get("option_id"))
        except (TypeError, ValueError):
            raise ValidationError({"option_id": "An option ID is required."}) from None
        with transaction.atomic():
            poll = get_object_or_404(PostPoll.objects.select_for_update(), post=post)
            option = get_object_or_404(PollOption, pk=option_id, poll=poll)
            existing = PollVote.objects.filter(poll=poll, user=request.user).first()
            if existing:
                if existing.option_id != option_id:
                    raise Conflict("You already voted for another option.")
            else:
                if poll.closes_at and poll.closes_at <= timezone.now():
                    raise Conflict("This poll is closed.")
                try:
                    with transaction.atomic():
                        PollVote.objects.create(poll=poll, option=option, user=request.user)
                except IntegrityError:
                    current = PollVote.objects.get(poll=poll, user=request.user)
                    if current.option_id != option_id:
                        raise Conflict("You already voted for another option.") from None
        return Response({"poll": poll_response(post, request.user)})


class PostCommentDetailView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [SocialWriteThrottle]

    def _comment(self, request, pk):
        from .serializers import PostCommentSerializer
        comment = get_object_or_404(PostComment.objects.select_related("post", "author"), pk=pk, is_deleted=False)
        if not can_moderate_social(request.user):
            get_object_or_404(social_posts_for(request.user), pk=comment.post_id)
        if comment.author_id != request.user.pk and not can_moderate_social(request.user):
            raise PermissionDenied("Only the comment author or content manager can change this comment.")
        return comment

    def patch(self, request, pk):
        from .serializers import PostCommentSerializer
        comment = self._comment(request, pk)
        if "text" not in request.data:
            raise ValidationError({"text": "This field is required."})
        serializer = PostCommentSerializer(comment, data=request.data, partial=True, context={"request": request})
        serializer.is_valid(raise_exception=True)
        if set(serializer.validated_data) - {"text"}:
            raise ValidationError({"detail": "Only comment text can be edited."})
        serializer.save(is_edited=True)
        return Response(serializer.data)

    def delete(self, request, pk):
        comment = self._comment(request, pk)
        comment.is_deleted = True
        comment.text = ""
        comment.save(update_fields=["is_deleted", "text", "updated_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)


REPORT_REASONS = {"SPAM", "ABUSE", "MISLEADING", "OTHER"}


def _report_data(request):
    reason = str(request.data.get("reason", "")).upper()
    description = strip_tags(str(request.data.get("description", ""))).strip()
    if reason not in REPORT_REASONS:
        raise ValidationError({"reason": "Choose SPAM, ABUSE, MISLEADING or OTHER."})
    if len(description) > 1000:
        raise ValidationError({"description": "Maximum 1000 characters."})
    return reason, description


class CommentReportView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [SocialReportThrottle]

    def post(self, request, pk):
        comment = get_object_or_404(PostComment.objects.select_related("post"), pk=pk, is_deleted=False)
        get_object_or_404(social_posts_for(request.user), pk=comment.post_id)
        reason, description = _report_data(request)
        report, created = CommentReport.objects.get_or_create(
            comment=comment, reporter=request.user, defaults={"reason": reason, "description": description}
        )
        return Response({"id": report.pk, "status": report.status}, status=201 if created else 200)


class AnalystListView(ListAPIView):
    permission_classes = [IsAuthenticated]
    pagination_class = DefaultPagination
    serializer_class = SocialUserSerializer

    def get_queryset(self):
        return social_users_for(User.objects.filter(is_active=True, social_analyst_profile__is_active_analyst=True), self.request.user).select_related("social_analyst_profile", "profile_details").order_by("-social_analyst_profile__credibility_score", "pk")


class AnalystManageListView(ListAPIView):
    permission_classes = [IsAuthenticated, IsEmployee]
    pagination_class = DefaultPagination
    serializer_class = SocialUserSerializer

    def get_queryset(self):
        queryset = social_users_for(User.objects.filter(is_active=True), self.request.user).select_related("social_analyst_profile", "profile_details")
        search = self.request.query_params.get("search", "").strip()[:100]
        if search:
            queryset = queryset.filter(Q(first_name__icontains=search) | Q(last_name__icontains=search) | Q(username__icontains=search))
        return queryset.order_by("pk")


class AnalystManageDetailView(APIView):
    permission_classes = [IsAuthenticated, IsEmployee]

    def patch(self, request, user_id):
        user = get_object_or_404(User, pk=user_id, is_active=True)
        allowed = {"is_active_analyst", "is_verified", "specialty", "credibility_score"}
        unknown = set(request.data) - allowed
        if unknown:
            raise ValidationError({"detail": f"Unknown fields: {', '.join(sorted(unknown))}"})
        profile, _ = SocialAnalystProfile.objects.get_or_create(user=user)
        for name, value in request.data.items():
            if name in ("is_active_analyst", "is_verified"):
                if not isinstance(value, bool):
                    raise ValidationError({name: "Must be a boolean."})
            elif name == "credibility_score":
                if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 100:
                    raise ValidationError({name: "Must be an integer from 0 to 100."})
            elif name == "specialty":
                if not isinstance(value, str) or len(value) > 200:
                    raise ValidationError({name: "Maximum 200 characters."})
                value = strip_tags(value).strip()
            setattr(profile, name, value)
        profile.save()
        return Response(SocialUserSerializer(user, context={"request": request}).data)


class RoomPresenceView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, slug):
        room = get_object_or_404(ChatRoom, slug=slug, is_active=True)
        ChatService.ensure_member(room, request.user)
        count = heartbeat(room, request.user)
        if count is None:
            raise PresenceUnavailable()
        return Response({"online_count": count})


class RoomInvitationView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [RoomInviteThrottle]

    def post(self, request, slug):
        room = get_object_or_404(ChatRoom, slug=slug, is_active=True)
        if not can_invite_to_room(room, request.user):
            raise PermissionDenied("Only room managers and moderators can invite members.")
        try:
            user_id = int(request.data.get("user_id"))
        except (TypeError, ValueError):
            raise ValidationError({"user_id": "A user ID is required."}) from None
        invitee = get_object_or_404(User, pk=user_id, is_active=True)
        if RoomMembership.objects.filter(room=room, user=invitee).exists():
            raise Conflict("This user is already a member.")
        with transaction.atomic():
            ChatRoom.objects.select_for_update().get(pk=room.pk)
            existing = RoomInvitation.objects.filter(room=room, invitee=invitee, accepted_at__isnull=True, cancelled_at__isnull=True).first()
            if existing and existing.expires_at > timezone.now():
                invitation, created = existing, False
            else:
                if existing:
                    existing.cancelled_at = timezone.now()
                    existing.save(update_fields=["cancelled_at"])
                invitation = RoomInvitation.objects.create(room=room, invitee=invitee, inviter=request.user, expires_at=timezone.now() + timedelta(days=7))
                created = True
            if created:
                transaction.on_commit(lambda: queue_social_notification(
                    key=f"ROOM_INVITATION:{invitation.pk}", recipient_id=invitee.pk,
                    title="دعوت به اتاق گفتگو", url=f"/chat/rooms/{quote(room.slug, safe='')}?invite={invitation.pk}",
                ))
        return Response({"id": invitation.pk, "expires_at": invitation.expires_at}, status=201 if created else 200)


class RoomInvitationAcceptView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, invitation_id):
        with transaction.atomic():
            invitation = get_object_or_404(RoomInvitation.objects.select_for_update().select_related("room"), pk=invitation_id)
            if invitation.invitee_id != request.user.pk:
                raise PermissionDenied("This invitation is not yours.")
            if invitation.accepted_at:
                membership = get_object_or_404(RoomMembership, room=invitation.room, user=request.user)
                return Response({"room": invitation.room.slug, "membership_role": membership.role})
            if invitation.cancelled_at or invitation.expires_at <= timezone.now():
                raise Conflict("This invitation expired or was cancelled.")
            if not invitation.room.is_active:
                raise Conflict("This room is inactive.")
            membership, _ = RoomMembership.objects.get_or_create(room=invitation.room, user=request.user)
            if not invitation.accepted_at:
                invitation.accepted_at = timezone.now()
                invitation.save(update_fields=["accepted_at"])
        return Response({"room": invitation.room.slug, "membership_role": membership.role})


class CommunityView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        visible = social_posts_for(request.user)
        recent = visible.filter(created_at__gte=timezone.now() - timedelta(days=7))
        trends = list(PostHashtag.objects.filter(post_id__in=recent.values("pk")).values("tag").annotate(posts_count=Count("post_id", distinct=True)).order_by("-posts_count", "tag")[:10])
        rooms_qs = ChatService.visible_rooms(request.user).select_related("manager")
        rooms = list(rooms_qs[:10])
        all_room_ids = list(rooms_qs.values_list("pk", flat=True))
        online = set()
        occupied_rooms = 0
        client = _redis()
        request._chat_presence_client = client
        availability = client is not None
        if availability:
            for room in ChatRoom.objects.filter(pk__in=all_room_ids):
                ids = room_online_ids(room, client)
                if ids is None:
                    availability = False
                    break
                if ids:
                    occupied_rooms += 1
                online.update(ids)
        analysts = social_users_for(User.objects.filter(is_active=True, social_analyst_profile__is_active_analyst=True, social_analyst_profile__is_verified=True), request.user).select_related("social_analyst_profile", "profile_details").order_by("-social_analyst_profile__credibility_score", "pk")[:6]
        return Response({
            "features": {"community_v3": config("SOCIAL_COMMUNITY_V3_ENABLED", default=False, cast=bool)},
            "active_rooms_count": occupied_rooms if availability else None,
            "online_count": len(online) if availability else None,
            "trends": trends,
            "analysts": SocialUserSerializer(analysts, many=True, context={"request": request}).data,
            "rooms": ChatRoomSerializer(rooms, many=True, context={"request": request}).data,
        })


def _report_row(report, target_type):
    target = report.post if target_type == "POST" else report.comment
    return {
        "id": report.pk * 2 if target_type == "POST" else report.pk * 2 + 1,
        "status": report.status,
        "target_type": target_type,
        "target_id": target.pk,
        "reason": report.reason,
        "description": report.description,
        "content_excerpt": strip_tags(target.text or "")[:160] if not target.is_deleted else "",
        "created_at": report.created_at,
        "reviewed_at": report.reviewed_at,
    }


class ReportManageListView(APIView):
    permission_classes = [IsAuthenticated, IsEmployee]

    def get(self, request):
        report_status = request.query_params.get("status", "")
        if report_status and report_status not in ("PENDING", "RESOLVED", "DISMISSED"):
            raise ValidationError({"status": "Unknown report status."})
        search = request.query_params.get("search", "").strip()[:100]
        try:
            page = int(request.query_params.get("page", "1"))
            size = int(request.query_params.get("page_size", "20"))
        except ValueError:
            raise ValidationError({"page": "Page and page_size must be integers."}) from None
        if page < 1 or not 1 <= size <= 100:
            raise ValidationError({"page": "Invalid pagination."})
        posts = PostReport.objects.select_related("post")
        comments = CommentReport.objects.select_related("comment")
        if report_status:
            posts = posts.filter(status=report_status)
            comments = comments.filter(status=report_status)
        if search:
            posts = posts.filter(Q(reason__icontains=search) | Q(post__text__icontains=search))
            comments = comments.filter(Q(reason__icontains=search) | Q(comment__text__icontains=search))
        total = posts.count() + comments.count()
        limit = page * size
        rows = [_report_row(row, "POST") for row in posts.order_by("-created_at", "-pk")[:limit]]
        rows += [_report_row(row, "COMMENT") for row in comments.order_by("-created_at", "-pk")[:limit]]
        rows.sort(key=lambda row: (row["created_at"], row["id"]), reverse=True)
        start = (page - 1) * size
        def url(number):
            query = request.query_params.copy()
            query["page"] = str(number)
            query["page_size"] = str(size)
            return request.build_absolute_uri(f"{request.path}?{query.urlencode()}")
        return Response({"count": total, "next": url(page + 1) if start + size < total else None, "previous": url(page - 1) if page > 1 else None, "results": rows[start:start + size]})


class ReportManageDetailView(APIView):
    permission_classes = [IsAuthenticated, IsEmployee]

    def patch(self, request, report_id):
        action = request.data.get("action")
        note = request.data.get("admin_note", "")
        if action not in ("DISMISS", "REMOVE_CONTENT"):
            raise ValidationError({"action": "Choose DISMISS or REMOVE_CONTENT."})
        if not isinstance(note, str) or len(note) > 1000:
            raise ValidationError({"admin_note": "Maximum 1000 characters."})
        target_type = "COMMENT" if report_id % 2 else "POST"
        raw_id = report_id // 2
        model = CommentReport if target_type == "COMMENT" else PostReport
        with transaction.atomic():
            report = get_object_or_404(model.objects.select_for_update(), pk=raw_id)
            if report.status in (PostReport.Status.RESOLVED, PostReport.Status.DISMISSED):
                expected = PostReport.Status.RESOLVED if action == "REMOVE_CONTENT" else PostReport.Status.DISMISSED
                if report.status != expected:
                    raise Conflict("This report was already reviewed with another action.")
                return Response(_report_row(report, target_type))
            if action == "REMOVE_CONTENT":
                target = report.comment if target_type == "COMMENT" else report.post
                if not target.is_deleted:
                    target.is_deleted = True
                    target.text = ""
                    target.save(update_fields=["is_deleted", "text", "updated_at"])
                report.status = PostReport.Status.RESOLVED
            else:
                report.status = PostReport.Status.DISMISSED
            report.admin_note = note
            report.reviewed_at = timezone.now()
            report.reviewed_by = request.user
            report.save(update_fields=["status", "admin_note", "reviewed_at", "reviewed_by"])
            SocialReportAudit.objects.create(target_type=target_type, report_id=raw_id, action=action, actor=request.user, admin_note=note)
        return Response(_report_row(report, target_type))
