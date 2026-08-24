from rest_framework import serializers

from common.content_access import AllowedLevelsSerializerMixin
from common.validators import validate_image_upload, validate_video_upload

from .models import (
    Course, CourseEnrollment, CourseSession, SessionProgress,
    Quiz, QuizAttempt, QuizOption, QuizQuestion,
)


class CourseListSerializer(
    AllowedLevelsSerializerMixin,
    serializers.ModelSerializer,
):
    instructor = serializers.CharField(
        source="instructor.username",
        read_only=True,
    )
    instructor_name = serializers.SerializerMethodField()
    sessions_count = serializers.IntegerField(
        source="sessions.count",
        read_only=True,
    )
    is_enrolled = serializers.SerializerMethodField()
    is_purchased = serializers.SerializerMethodField()
    can_access_content = serializers.SerializerMethodField()

    class Meta:
        model = Course
        fields = (
            "id",
            "title",
            "slug",
            "description",
            "short_description",
            "cover_image",
            "instructor",
            "instructor_name",
            "status",
            "difficulty",
            "trailer_url",
            "estimated_duration_minutes",
            "prerequisites",
            "learning_outcomes",
            "enrollment_open",
            "is_free",
            "price",
            "currency",
            "purchase_required",
            "weekly_session_limit",
            "monthly_session_limit",
            "starts_at",
            "ends_at",
            "allowed_levels",
            "sessions_count",
            "is_enrolled",
            "is_purchased",
            "can_access_content",
            "created_at",
            "updated_at",
        )

    def get_instructor_name(self, obj) -> str:
        return (
            obj.instructor.get_full_name().strip()
            or obj.instructor.username
        )

    def _access_state(self, obj):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False, False, False
        manages = (
            user.has_platform_permission("ACADEMY_MANAGE")
            or obj.instructor_id == user.id
        )
        enrolled = obj.enrollments.filter(user=user).exists()
        purchased = obj.purchases.filter(user=user).exists()
        can_access = manages or (enrolled and (obj.is_free or purchased))
        return enrolled, purchased, can_access

    def get_is_enrolled(self, obj) -> bool:
        return self._access_state(obj)[0]

    def get_is_purchased(self, obj) -> bool:
        return self._access_state(obj)[1]

    def get_can_access_content(self, obj) -> bool:
        return self._access_state(obj)[2]


class CourseWriteSerializer(
    AllowedLevelsSerializerMixin,
    serializers.ModelSerializer,
):
    instructor = serializers.CharField(
        source="instructor.username",
        read_only=True,
    )
    instructor_name = serializers.SerializerMethodField()

    class Meta:
        model = Course
        fields = (
            "id",
            "title",
            "slug",
            "description",
            "short_description",
            "cover_image",
            "instructor",
            "instructor_name",
            "status",
            "difficulty",
            "trailer_url",
            "estimated_duration_minutes",
            "prerequisites",
            "learning_outcomes",
            "enrollment_open",
            "is_free",
            "price",
            "currency",
            "purchase_required",
            "weekly_session_limit",
            "monthly_session_limit",
            "starts_at",
            "ends_at",
            "allowed_levels",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "slug",
            "instructor",
            "instructor_name",
            "created_at",
            "updated_at",
        )

    def get_instructor_name(self, obj) -> str:
        return (
            obj.instructor.get_full_name().strip()
            or obj.instructor.username
        )

    def validate_cover_image(self, value):
        return validate_image_upload(
            value,
            max_size_mb=8,
            file_label="Course cover image",
        )

    def validate(self, attrs):
        attrs = super().validate(attrs)
        is_free = attrs.get("is_free", getattr(self.instance, "is_free", True))
        price = attrs.get("price", getattr(self.instance, "price", 0))
        if is_free and price:
            raise serializers.ValidationError({"price": "A free course must have zero price."})
        if not is_free and price <= 0:
            raise serializers.ValidationError({"price": "A paid course needs a positive price."})
        attrs["purchase_required"] = not is_free
        attrs["currency"] = "IRT"
        return attrs


class CourseSessionSerializer(serializers.ModelSerializer):
    course = serializers.CharField(
        source="course.slug",
        read_only=True,
    )
    is_locked = serializers.SerializerMethodField()
    lock_reason = serializers.SerializerMethodField()

    class Meta:
        model = CourseSession
        fields = (
            "id",
            "course",
            "title",
            "order",
            "video_url",
            "video_file",
            "media_type",
            "audio_file",
            "cover",
            "duration_seconds",
            "playback_speeds",
            "is_locked",
            "lock_reason",
            "unlock_at",
            "duration_minutes",
            "text",
            "image",
            "is_published",
            "is_preview",
            "available_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "course",
            "created_at",
            "updated_at",
        )

    def validate_image(self, value):
        return validate_image_upload(
            value,
            max_size_mb=8,
            file_label="Course session image",
        )

    def validate_video_file(self, value):
        return validate_video_upload(value, max_size_mb=500, file_label="Session video")

    def validate(self, attrs):
        video_url = attrs.get("video_url", getattr(self.instance, "video_url", ""))
        video_file = attrs.get("video_file", getattr(self.instance, "video_file", None))
        if video_url and video_file:
            raise serializers.ValidationError("Use either video_url or video_file, not both.")
        course = (
            self.instance.course
            if self.instance
            else self.context["view"].get_course()
        )
        order = attrs.get(
            "order",
            getattr(self.instance, "order", None),
        )
        queryset = CourseSession.objects.filter(
            course=course,
            order=order,
        )
        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise serializers.ValidationError(
                {"order": "This order is already used in this course."}
            )
        return attrs

    def get_lock_reason(self, obj) -> str:
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return "Authentication required"
        from .views import session_lock_reason
        return session_lock_reason(obj, request.user)

    def get_is_locked(self, obj) -> bool:
        return bool(self.get_lock_reason(obj))

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if self.get_is_locked(instance):
            data.update({
                "video_url": "",
                "video_file": None,
                "audio_file": None,
                "text": "",
                "image": None,
            })
        return data

    def validate_audio_file(self, value):
        allowed = {"audio/mpeg", "audio/mp4", "audio/wav", "audio/ogg", "audio/webm"}
        if getattr(value, "content_type", "").split(";", 1)[0].lower() not in allowed:
            raise serializers.ValidationError("Unsupported audio content type.")
        if value.size > 50 * 1024 * 1024:
            raise serializers.ValidationError("Audio cannot exceed 50 MB.")
        return value


class QuizOptionPublicSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuizOption
        fields = ("id", "text", "order")


class QuizQuestionPublicSerializer(serializers.ModelSerializer):
    options = QuizOptionPublicSerializer(many=True, read_only=True)

    class Meta:
        model = QuizQuestion
        fields = ("id", "text", "order", "options")


class QuizPublicSerializer(serializers.ModelSerializer):
    questions = QuizQuestionPublicSerializer(many=True, read_only=True)

    class Meta:
        model = Quiz
        fields = ("id", "session", "title", "required_score", "max_attempts", "retry_delay_minutes", "questions")


class QuizAttemptSerializer(serializers.ModelSerializer):
    required_score = serializers.IntegerField(source="quiz.required_score", read_only=True)

    class Meta:
        model = QuizAttempt
        fields = ("id", "score", "passed", "required_score", "attempt_number", "next_attempt_at", "created_at")
        read_only_fields = fields


class QuizOptionWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuizOption
        fields = ("id", "text", "is_correct", "order")


class QuizQuestionWriteSerializer(serializers.ModelSerializer):
    options = QuizOptionWriteSerializer(many=True)

    class Meta:
        model = QuizQuestion
        fields = ("id", "text", "order", "options")


class QuizWriteSerializer(serializers.ModelSerializer):
    questions = QuizQuestionWriteSerializer(many=True)

    class Meta:
        model = Quiz
        fields = ("id", "session", "title", "required_score", "max_attempts", "retry_delay_minutes", "is_active", "questions")

    def validate_questions(self, questions):
        if not questions:
            raise serializers.ValidationError("At least one question is required.")
        for question in questions:
            if len(question.get("options", [])) < 2 or sum(bool(item.get("is_correct")) for item in question.get("options", [])) != 1:
                raise serializers.ValidationError("Each question needs at least two options and exactly one correct option.")
        return questions

    def create(self, validated_data):
        questions = validated_data.pop("questions")
        quiz = Quiz.objects.create(**validated_data)
        self._save_questions(quiz, questions)
        return quiz

    def update(self, instance, validated_data):
        questions = validated_data.pop("questions", None)
        instance = super().update(instance, validated_data)
        if questions is not None:
            instance.questions.all().delete()
            self._save_questions(instance, questions)
        return instance

    @staticmethod
    def _save_questions(quiz, questions):
        for question_data in questions:
            options = question_data.pop("options")
            question = QuizQuestion.objects.create(quiz=quiz, **question_data)
            QuizOption.objects.bulk_create([QuizOption(question=question, **item) for item in options])


class CourseEnrollmentSerializer(serializers.ModelSerializer):
    course = CourseListSerializer(read_only=True)
    completed_sessions = serializers.SerializerMethodField()
    total_sessions = serializers.IntegerField(source="course.sessions.count", read_only=True)
    weekly_used = serializers.SerializerMethodField()
    weekly_limit = serializers.IntegerField(source="course.weekly_session_limit", read_only=True, allow_null=True)
    monthly_used = serializers.SerializerMethodField()
    monthly_limit = serializers.IntegerField(source="course.monthly_session_limit", read_only=True, allow_null=True)
    next_session = serializers.SerializerMethodField()
    locked_reason = serializers.SerializerMethodField()

    class Meta:
        model = CourseEnrollment
        fields = (
            "id", "course", "enrolled_at", "completed_at", "completed_sessions", "total_sessions",
            "weekly_used", "weekly_limit", "monthly_used", "monthly_limit", "next_session", "locked_reason",
        )

        read_only_fields = fields

    def get_completed_sessions(self, obj) -> int:
        return obj.session_progress.filter(completed_at__isnull=False).count()

    def get_weekly_used(self, obj) -> int:
        from django.utils import timezone
        from datetime import timedelta
        return obj.session_progress.filter(updated_at__gte=timezone.now() - timedelta(days=7)).count()

    def get_monthly_used(self, obj) -> int:
        from django.utils import timezone
        from datetime import timedelta
        return obj.session_progress.filter(updated_at__gte=timezone.now() - timedelta(days=30)).count()

    def get_next_session(self, obj) -> int | None:
        completed = obj.session_progress.filter(completed_at__isnull=False).values_list("session_id", flat=True)
        session = obj.course.sessions.filter(is_published=True).exclude(pk__in=completed).order_by("order").first()
        return session.pk if session else None

    def get_locked_reason(self, obj) -> str:
        session_id = self.get_next_session(obj)
        if not session_id:
            return ""
        from .views import session_lock_reason
        return session_lock_reason(obj.course.sessions.get(pk=session_id), obj.user)


class CoursePurchaseSerializer(serializers.Serializer):
    payment_method = serializers.ChoiceField(choices=("WALLET", "GATEWAY"))
    provider = serializers.CharField(required=False)
    idempotency_key = serializers.CharField(max_length=120, required=False)


class SessionProgressSerializer(serializers.ModelSerializer):
    class Meta:
        model = SessionProgress
        fields = (
            "id", "session", "progress_percent", "last_position_seconds",
            "completed_at", "updated_at",
        )
        read_only_fields = ("id", "completed_at", "updated_at")

    def validate_progress_percent(self, value):
        if value > 100:
            raise serializers.ValidationError("Must be between 0 and 100.")
        return value
