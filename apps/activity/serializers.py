from rest_framework import serializers

from .models import UserActivity


CANONICAL_PAGE_PATHS = frozenset({
    "/dashboard", "/signals", "/internal-analysis", "/academy", "/videos",
    "/articles", "/brokers", "/live", "/assets", "/personality", "/portfolio",
    "/assistant", "/profile", "/chat", "/settings", "/upgrade",
    "/notifications", "/economic-calendar", "/broker-connection",
    "/academy/:item", "/videos/:item", "/articles/:item", "/brokers/:item",
    "/live/:item",
})


class PageViewIngestSerializer(serializers.Serializer):
    event_id = serializers.UUIDField()
    session_id = serializers.UUIDField()
    path = serializers.ChoiceField(choices=sorted(CANONICAL_PAGE_PATHS))

    def to_internal_value(self, data):
        unknown = set(data) - set(self.fields)
        if unknown:
            raise serializers.ValidationError({key: "Unknown field." for key in sorted(unknown)})
        return super().to_internal_value(data)


class UserActivitySerializer(serializers.ModelSerializer):
    class Meta:
        model = UserActivity
        fields = (
            "id", "activity_type", "title", "description", "target_type",
            "target_id", "target_url", "metadata", "ip_address", "created_at",
        )
        read_only_fields = fields

