from rest_framework import serializers

from common.content_access import AllowedLevelsSerializerMixin
from common.validators import validate_image_upload

from .models import Course, CourseSession


class CourseListSerializer(
    AllowedLevelsSerializerMixin,
    serializers.ModelSerializer,
):
    instructor = serializers.CharField(
        source="instructor.username",
        read_only=True,
    )
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
            "cover_image",
            "instructor",
            "status",
            "allowed_levels",
            "sessions_count",
            "created_at",
            "updated_at",
        )


class CourseWriteSerializer(
    AllowedLevelsSerializerMixin,
    serializers.ModelSerializer,
):
    class Meta:
        model = Course
        fields = (
            "id",
            "title",
            "slug",
            "description",
            "cover_image",
            "status",
            "allowed_levels",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "slug",
            "created_at",
            "updated_at",
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
            "text",
            "image",
            "is_published",
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

    def validate(self, attrs):
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
