from django.db import models
from django.db.models import Q
from rest_framework import serializers

from apps.accounts.models import User


LEVELS = (1, 2, 3, 4, 5)
class LevelRestrictedContent(models.Model):
    allowed_level_1 = models.BooleanField(default=True)
    allowed_level_2 = models.BooleanField(default=True)
    allowed_level_3 = models.BooleanField(default=True)
    allowed_level_4 = models.BooleanField(default=True)
    allowed_level_5 = models.BooleanField(default=True)

    class Meta:
        abstract = True

    @property
    def allowed_levels(self):
        return [
            level
            for level in LEVELS
            if getattr(self, f"allowed_level_{level}")
        ]


class AllowedLevelsSerializerMixin(serializers.Serializer):
    allowed_levels = serializers.ListField(
        child=serializers.IntegerField(min_value=1, max_value=5),
        allow_empty=False,
        required=False,
    )

    def validate_allowed_levels(self, value):
        if len(value) != len(set(value)):
            raise serializers.ValidationError(
                "Each access level may only be selected once."
            )
        return sorted(value)

    def _with_level_flags(self, validated_data):
        levels = validated_data.pop("allowed_levels", None)
        if levels is not None:
            for level in LEVELS:
                validated_data[f"allowed_level_{level}"] = level in levels
        return validated_data

    def create(self, validated_data):
        return super().create(self._with_level_flags(validated_data))

    def update(self, instance, validated_data):
        return super().update(
            instance,
            self._with_level_flags(validated_data),
        )

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["allowed_levels"] = instance.allowed_levels
        return data


def restrict_queryset_for_user(queryset, user):
    if (
        user.is_superuser
        or user.has_platform_permission(
            User.Permission.CONTENT_VIEW_ALL
        )
    ):
        return queryset

    level = user.access_level
    if level not in LEVELS:
        return queryset.none()

    return queryset.filter(
        Q(**{f"allowed_level_{level}": True})
    )
