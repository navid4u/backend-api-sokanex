from rest_framework import serializers

from .models import EconomicEvent, NewsArticle


class EconomicEventSerializer(serializers.ModelSerializer):
    impact_display = serializers.CharField(source="get_impact_display", read_only=True)

    class Meta:
        model = EconomicEvent
        fields = (
            "id", "datetime", "currency", "impact", "impact_display", "title",
            "actual", "forecast", "previous", "unit", "source_timestamp",
        )


class NewsArticleSerializer(serializers.ModelSerializer):
    id = serializers.CharField(source="stable_id", read_only=True)
    source_name = serializers.CharField(source="source.name", read_only=True)
    language = serializers.CharField(source="source.language", read_only=True)

    class Meta:
        model = NewsArticle
        fields = (
            "id", "title", "summary", "url", "source_name", "language", "published_at",
        )
