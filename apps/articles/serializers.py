from rest_framework import serializers

from .models import Article, Category
from common.validators import (
    validate_image_upload,
)

class CategorySerializer(serializers.ModelSerializer):

    class Meta:
        model = Category

        fields = (
            "id",
            "name",
            "slug",
        )

        read_only_fields = (
            "id",
            "slug",
        )


class ArticleListSerializer(serializers.ModelSerializer):

    author = serializers.CharField(
        source="author.username",
        read_only=True,
    )

    category = CategorySerializer(
        read_only=True,
    )

    class Meta:
        model = Article

        fields = (
            "id",
            "title",
            "slug",
            "summary",
            "cover_image",
            "category",
            "author",
            "status",
            "published_at",
            "created_at",
        )


class ArticleDetailSerializer(
    ArticleListSerializer
):

    class Meta(ArticleListSerializer.Meta):

        fields = (
            ArticleListSerializer.Meta.fields
            + (
                "content",
                "updated_at",
            )
        )


class ArticleWriteSerializer(
    serializers.ModelSerializer
):

    class Meta:
        model = Article

        fields = (
            "id",
            "title",
            "slug",
            "summary",
            "content",
            "cover_image",
            "category",
            "status",
            "published_at",
            "created_at",
            "updated_at",
        )

        read_only_fields = (
            "id",
            "slug",
            "published_at",
            "created_at",
            "updated_at",
        )

    def validate_cover_image(self, value):
        return validate_image_upload(
            value,
            max_size_mb=8,
            file_label="Cover image",
        )