from rest_framework import serializers

from .models import UserActivity


class UserActivitySerializer(serializers.ModelSerializer):
    class Meta:
        model = UserActivity
        fields = (
            "id", "activity_type", "title", "description", "target_type",
            "target_id", "target_url", "metadata", "ip_address", "created_at",
        )
        read_only_fields = fields

