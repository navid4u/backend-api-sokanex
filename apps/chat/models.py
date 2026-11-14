from django.conf import settings
from django.db import models
from django.utils.text import slugify
from .social_media import private_social_storage


class ChatRoom(models.Model):
    market = models.CharField(max_length=20, default="general", db_index=True)
    topic = models.CharField(max_length=200, blank=True)
    manager = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="managed_chat_rooms")

    name = models.CharField(
        max_length=150,
        unique=True,
    )

    slug = models.SlugField(
        max_length=180,
        unique=True,
        allow_unicode=True,
        blank=True,
    )

    description = models.TextField(
        blank=True,
    )

    image = models.ImageField(
        upload_to="chat/rooms/",
        storage=private_social_storage,
        null=True,
        blank=True,
    )

    is_public = models.BooleanField(
        default=True,
    )

    is_active = models.BooleanField(
        default=True,
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_chat_rooms",
    )

    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        through="RoomMembership",
        related_name="chat_rooms",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ["name"]

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(
                self.name,
                allow_unicode=True,
            ) or "chat-room"

            slug = base_slug
            counter = 2

            while ChatRoom.objects.filter(
                slug=slug
            ).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1

            self.slug = slug

        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class RoomMembership(models.Model):

    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Admin"
        MODERATOR = "MODERATOR", "Moderator"
        MEMBER = "MEMBER", "Member"

    room = models.ForeignKey(
        ChatRoom,
        on_delete=models.CASCADE,
        related_name="memberships",
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="room_memberships",
    )

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.MEMBER,
    )

    joined_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "room",
                    "user",
                ],
                name="unique_chat_room_membership",
            ),
        ]

    def __str__(self):
        return f"{self.user} - {self.room}"


class Message(models.Model):

    room = models.ForeignKey(
        ChatRoom,
        on_delete=models.CASCADE,
        related_name="messages",
    )

    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="chat_messages",
    )

    text = models.TextField(
        blank=True,
    )

    attachment = models.FileField(
        upload_to="chat/attachments/",
        storage=private_social_storage,
        null=True,
        blank=True,
    )

    reply_to = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="replies",
    )

    is_deleted = models.BooleanField(
        default=False,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ["-created_at"]

        indexes = [
            models.Index(
                fields=[
                    "room",
                    "-created_at",
                ]
            ),
            models.Index(
                fields=[
                    "sender",
                    "-created_at",
                ]
            ),
        ]

    def __str__(self):
        return (
            f"Message {self.pk} "
            f"in {self.room}"
        )


class TraderPost(models.Model):
    class Market(models.TextChoices):
        FOREX = "forex", "Forex"
        CRYPTO = "crypto", "Crypto"
        GOLD_DOLLAR = "gold_dollar", "Gold and dollar"
        STOCK = "stock", "Stock"
        REAL_ESTATE = "real_estate", "Real estate"
        GENERAL = "general", "General"

    class Type(models.TextChoices):
        POST = "POST", "Post"
        ANALYSIS = "ANALYSIS", "Analysis"
        QUESTION = "QUESTION", "Question"
        POLL = "POLL", "Poll"

    class Visibility(models.TextChoices):
        PUBLIC = "PUBLIC", "Public"
        FOLLOWERS = "FOLLOWERS", "Followers"
        PRIVATE = "PRIVATE", "Private"

    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="social_posts"
    )
    market = models.CharField(max_length=20, choices=Market.choices, default=Market.GENERAL, db_index=True)
    post_type = models.CharField(max_length=12, choices=Type.choices, default=Type.POST, db_index=True)
    text = models.TextField(blank=True)
    image = models.ImageField(upload_to="social/posts/images/%Y/%m/", storage=private_social_storage, null=True, blank=True)
    video = models.FileField(upload_to="social/posts/videos/%Y/%m/", storage=private_social_storage, null=True, blank=True)
    visibility = models.CharField(max_length=20, choices=Visibility.choices, default=Visibility.PUBLIC)
    is_edited = models.BooleanField(default=False)
    is_deleted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["visibility", "is_deleted", "-created_at"]),
            models.Index(fields=["author", "-created_at"]),
        ]


class PostComment(models.Model):
    post = models.ForeignKey(TraderPost, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="social_comments"
    )
    parent = models.ForeignKey(
        "self", on_delete=models.CASCADE, null=True, blank=True, related_name="replies"
    )
    text = models.TextField(max_length=2000)
    is_edited = models.BooleanField(default=False)
    is_deleted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at", "id"]


class PostReaction(models.Model):
    class Type(models.TextChoices):
        LIKE = "LIKE", "Like"
        INSIGHTFUL = "INSIGHTFUL", "Insightful"
        SUPPORT = "SUPPORT", "Support"

    post = models.ForeignKey(TraderPost, on_delete=models.CASCADE, related_name="reactions")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="post_reactions"
    )
    reaction_type = models.CharField(max_length=20, choices=Type.choices, default=Type.LIKE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["post", "user"], name="unique_user_post_reaction")
        ]


class UserFollow(models.Model):
    follower = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="following_relations"
    )
    following = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="follower_relations"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["follower", "following"], name="unique_user_follow"),
            models.CheckConstraint(condition=~models.Q(follower=models.F("following")), name="cannot_follow_self"),
        ]


class SavedPost(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="saved_posts")
    post = models.ForeignKey(TraderPost, on_delete=models.CASCADE, related_name="saves")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "post"], name="unique_saved_post")]


class PostReport(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        REVIEWED = "REVIEWED", "Reviewed"
        RESOLVED = "RESOLVED", "Resolved"
        DISMISSED = "DISMISSED", "Dismissed"

    post = models.ForeignKey(TraderPost, on_delete=models.CASCADE, related_name="reports")
    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="post_reports"
    )
    reason = models.CharField(max_length=500)
    description = models.CharField(max_length=1000, blank=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="reviewed_social_post_reports")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    admin_note = models.CharField(max_length=1000, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["post", "reporter"], name="unique_user_post_report")
        ]


class PostUseful(models.Model):
    post = models.ForeignKey(TraderPost, on_delete=models.CASCADE, related_name="useful_votes")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="useful_posts")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["post", "user"], name="unique_social_post_useful")]


class PostHashtag(models.Model):
    post = models.ForeignKey(TraderPost, on_delete=models.CASCADE, related_name="hashtags")
    tag = models.CharField(max_length=100, db_index=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["post", "tag"], name="unique_social_post_tag")]


class PostPoll(models.Model):
    post = models.OneToOneField(TraderPost, on_delete=models.CASCADE, related_name="poll")
    question = models.CharField(max_length=250)
    closes_at = models.DateTimeField(null=True, blank=True)


class PollOption(models.Model):
    poll = models.ForeignKey(PostPoll, on_delete=models.CASCADE, related_name="options")
    text = models.CharField(max_length=120)
    position = models.PositiveSmallIntegerField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=["poll", "position"], name="unique_social_poll_position")]
        ordering = ["position", "pk"]


class PollVote(models.Model):
    poll = models.ForeignKey(PostPoll, on_delete=models.CASCADE, related_name="votes")
    option = models.ForeignKey(PollOption, on_delete=models.CASCADE, related_name="votes")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="social_poll_votes")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["poll", "user"], name="unique_social_poll_vote")]


class SocialAnalystProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="social_analyst_profile")
    is_active_analyst = models.BooleanField(default=False)
    is_verified = models.BooleanField(default=False)
    specialty = models.CharField(max_length=200, blank=True)
    credibility_score = models.PositiveSmallIntegerField(default=0)


class CommentReport(models.Model):
    comment = models.ForeignKey(PostComment, on_delete=models.CASCADE, related_name="reports")
    reporter = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="social_comment_reports")
    reason = models.CharField(max_length=20)
    description = models.CharField(max_length=1000, blank=True)
    status = models.CharField(max_length=20, choices=PostReport.Status.choices, default=PostReport.Status.PENDING)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="reviewed_social_comment_reports")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    admin_note = models.CharField(max_length=1000, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["comment", "reporter"], name="unique_user_comment_report")]


class RoomInvitation(models.Model):
    room = models.ForeignKey(ChatRoom, on_delete=models.CASCADE, related_name="invitations")
    invitee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="chat_invitations")
    inviter = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="sent_chat_invitations")
    accepted_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["room", "invitee"], condition=models.Q(accepted_at__isnull=True, cancelled_at__isnull=True), name="unique_pending_room_invitation")]


class SocialReportAudit(models.Model):
    target_type = models.CharField(max_length=10)
    report_id = models.PositiveIntegerField()
    action = models.CharField(max_length=20)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    admin_note = models.CharField(max_length=1000, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class SupportThread(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "در حال پیگیری"
        PENDING = "pending", "در انتظار پاسخ"
        CLOSED = "closed", "بسته شده"

    class Priority(models.TextChoices):
        LOW = "low", "کم"
        NORMAL = "normal", "عادی"
        HIGH = "high", "زیاد"
        URGENT = "urgent", "فوری"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="support_thread"
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="assigned_support_threads",
    )
    is_closed = models.BooleanField(default=False)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.OPEN)
    priority = models.CharField(max_length=12, choices=Priority.choices, default=Priority.NORMAL)
    subject = models.CharField(max_length=255, blank=True)
    last_message_at = models.DateTimeField(null=True, blank=True, db_index=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def slug(self):
        return "support"

    class Meta:
        ordering = ["-last_message_at", "-updated_at"]
        indexes = [models.Index(fields=["status", "last_message_at"])]


class SupportMessage(models.Model):
    thread = models.ForeignKey(SupportThread, on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name="support_messages",
    )
    text = models.TextField(blank=True)
    attachment = models.FileField(upload_to="chat/support/%Y/%m/", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    is_read = models.BooleanField(default=False, db_index=True)
    read_at = models.DateTimeField(null=True, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    idempotency_key = models.CharField(max_length=120, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["thread", "is_read"])]
        constraints = [models.UniqueConstraint(
            fields=["thread", "sender", "idempotency_key"],
            condition=~models.Q(idempotency_key=""),
            name="unique_support_message_idempotency",
        )]
