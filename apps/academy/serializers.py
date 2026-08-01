from rest_framework import serializers

from common.content_access import AllowedLevelsSerializerMixin
from common.validators import validate_image_upload, validate_video_upload

from .models import Course, CourseEnrollment, CourseSession, SessionProgress


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
            "starts_at",
            "ends_at",
            "allowed_levels",
            "sessions_count",
            "created_at",
            "updated_at",
        )

    def get_instructor_name(self, obj) -> str:
        return (
            obj.instructor.get_full_name().strip()
            or obj.instructor.username
        )


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


class CourseSessionSerializer(serializers.ModelSerializer):
    course = serializers.CharField(
        source="course.slug",
        read_only=True,
    )

    class Meta:
        model = CourseSession
        fields = (
            "id",
            "course",
            "title",
            "order",
            "video_url",
            "video_file",
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


class CourseEnrollmentSerializer(serializers.ModelSerializer):
    course = CourseListSerializer(read_only=True)

    class Meta:
        model = CourseEnrollment
        fields = ("id", "course", "enrolled_at", "completed_at")
        read_only_fields = fields


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
