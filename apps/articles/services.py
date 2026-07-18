from django.utils import timezone

from .models import Article


class ArticleService:

    @staticmethod
    def published_articles():
        return Article.objects.filter(
            status=Article.Status.PUBLISHED,
            published_at__lte=timezone.now(),
        ).select_related(
            "author",
            "category",
        )

    @staticmethod
    def all_articles():
        return Article.objects.select_related(
            "author",
            "category",
        )

    @staticmethod
    def create_article(
        serializer,
        author,
    ):
        published_at = None

        if (
            serializer.validated_data.get("status")
            == Article.Status.PUBLISHED
        ):
            published_at = timezone.now()

        return serializer.save(
            author=author,
            published_at=published_at,
        )

    @staticmethod
    def update_article(serializer):
        status = serializer.validated_data.get(
            "status",
            serializer.instance.status,
        )

        if (
            status == Article.Status.PUBLISHED
            and not serializer.instance.published_at
        ):
            return serializer.save(
                published_at=timezone.now()
            )

        if status == Article.Status.DRAFT:
            return serializer.save(
                published_at=None
            )

        return serializer.save()