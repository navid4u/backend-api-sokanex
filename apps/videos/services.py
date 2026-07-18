from django.utils import timezone

from .models import Video


class VideoService:

    @staticmethod
    def published_videos():
        return Video.objects.filter(
            status=Video.Status.PUBLISHED,
            published_at__lte=timezone.now(),
        ).select_related(
            "author",
            "category",
        )

    @staticmethod
    def all_videos():
        return Video.objects.select_related(
            "author",
            "category",
        )

    @staticmethod
    def create_video(serializer, author):
        published_at = None

        if (
            serializer.validated_data.get("status")
            == Video.Status.PUBLISHED
        ):
            published_at = timezone.now()

        return serializer.save(
            author=author,
            published_at=published_at,
        )

    @staticmethod
    def update_video(serializer):
        status = serializer.validated_data.get(
            "status",
            serializer.instance.status,
        )

        if (
            status == Video.Status.PUBLISHED
            and not serializer.instance.published_at
        ):
            return serializer.save(
                published_at=timezone.now()
            )

        if status == Video.Status.DRAFT:
            return serializer.save(
                published_at=None
            )

        return serializer.save()