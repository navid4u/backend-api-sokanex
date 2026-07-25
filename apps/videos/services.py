from django.utils import timezone

from .models import Video
from common.content_access import restrict_queryset_for_user


class VideoService:

    @staticmethod
    def published_videos(user=None):
        queryset = Video.objects.filter(
            status=Video.Status.PUBLISHED,
            published_at__lte=timezone.now(),
        ).select_related(
            "author",
            "category",
        )
        if user is not None:
            queryset = restrict_queryset_for_user(queryset, user)
        return queryset

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
