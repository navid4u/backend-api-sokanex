from rest_framework import serializers

from common.validators import validate_image_upload

from .models import Article, Category


class CategorySerializer(
    serializers.ModelSerializer
):

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


class ArticleListSerializer(
    serializers.ModelSerializer
):

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

    category = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.all(),
        required=False,
        allow_null=True,
    )

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

        extra_kwargs = {
            "cover_image": {
                "required": False,
                "allow_null": True,
            },
        }

    
    def validate_cover_image(self, value):
        if value is None:
            return value

        return validate_image_upload(
            value,
            max_size_mb=8,
            file_label="Article cover image",
        )
    def to_internal_value(self, data):
        if "category_id" in data:
            raise serializers.ValidationError(
                {
                    "category_id": (
                        "This field is not accepted. "
                        "Use 'category' instead."
                    ),
                }
            )

        return super().to_internal_value(data)