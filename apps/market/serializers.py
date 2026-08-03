from rest_framework import serializers

from .models import EconomicEvent


class EconomicEventSerializer(serializers.ModelSerializer):
    impact_display = serializers.CharField(source="get_impact_display", read_only=True)

    class Meta:
        model = EconomicEvent
        fields = (
            "id", "datetime", "currency", "impact", "impact_display", "title",
            "actual", "forecast", "previous", "unit", "source_timestamp",
        )
