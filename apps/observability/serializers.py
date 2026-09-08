from rest_framework import serializers

from .models import LogEvent
from .services import sanitize


class LogUserSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    username = serializers.CharField()
    first_name = serializers.CharField()
    last_name = serializers.CharField()


class LogEventSerializer(serializers.ModelSerializer):
    user = LogUserSerializer(read_only=True)
    resolved_by = LogUserSerializer(read_only=True)

    class Meta:
        model = LogEvent
        fields = (
            "id", "source", "level", "category", "message", "error_type",
            "stack_trace", "request_id", "client_event_id", "method", "path",
            "status_code", "duration_ms", "user", "ip_address", "user_agent",
            "frontend_url", "release", "context", "is_resolved", "resolved_by",
            "resolved_at", "created_at",
        )


class NullableBlankCharField(serializers.CharField):
    """Represent legacy blank model values as JSON null in detail responses."""

    def to_representation(self, value):
        if value in (None, ""):
            return None
        return super().to_representation(value)


class LogEventDetailSerializer(serializers.ModelSerializer):
    username = serializers.SerializerMethodField()
    user = LogUserSerializer(read_only=True)
    error_type = NullableBlankCharField(read_only=True, allow_null=True)
    stack_trace = NullableBlankCharField(read_only=True, allow_null=True)
    request_id = NullableBlankCharField(read_only=True, allow_null=True)
    frontend_url = NullableBlankCharField(read_only=True, allow_null=True)
    release = NullableBlankCharField(read_only=True, allow_null=True)
    user_agent = NullableBlankCharField(read_only=True, allow_null=True)
    method = NullableBlankCharField(read_only=True, allow_null=True)
    path = NullableBlankCharField(read_only=True, allow_null=True)

    class Meta:
        model = LogEvent
        fields = (
            "id", "source", "level", "category", "message", "error_type",
            "stack_trace", "context", "request_id", "frontend_url", "release",
            "user_agent", "ip_address", "username", "user", "method", "path",
            "status_code", "duration_ms", "is_resolved", "created_at",
        )

    def get_username(self, obj) -> str | None:
        return obj.user.username if obj.user_id else None


class FrontendLogSerializer(serializers.Serializer):
    client_event_id = serializers.CharField(max_length=80, required=False, allow_blank=True)
    level = serializers.ChoiceField(choices=("warning", "error", "critical"), default="error")
    category = serializers.ChoiceField(choices=(
        "javascript_error", "unhandled_rejection", "api_error", "network_error",
        "react_error_boundary", "resource_error", "other",
    ))
    message = serializers.CharField(max_length=1000)
    error_type = serializers.CharField(max_length=180, required=False, allow_blank=True)
    stack_trace = serializers.CharField(max_length=16000, required=False, allow_blank=True)
    frontend_url = serializers.URLField(max_length=1000, required=False, allow_blank=True)
    release = serializers.CharField(max_length=100, required=False, allow_blank=True)
    context = serializers.JSONField(required=False)

    def validate_context(self, value):
        cleaned = sanitize(value)
        if len(str(cleaned).encode("utf-8")) > 12000:
            raise serializers.ValidationError("Context is too large.")
        return cleaned


class ResolveLogSerializer(serializers.Serializer):
    is_resolved = serializers.BooleanField()


class PurgeLogSerializer(serializers.Serializer):
    confirm = serializers.BooleanField()

    def validate_confirm(self, value):
        if value is not True:
            raise serializers.ValidationError("Set confirm to true to purge all logs.")
        return value


class LogSummarySerializer(serializers.Serializer):
    last_24_hours = serializers.IntegerField()
    unresolved = serializers.IntegerField()
    by_level = serializers.DictField(child=serializers.IntegerField())
    by_source = serializers.DictField(child=serializers.IntegerField())
