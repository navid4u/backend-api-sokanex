from django.db import transaction

from .models import UserActivity


class ActivityService:
    MAX_PER_USER = 25

    @classmethod
    def record(cls, user, activity_type, title, **kwargs):
        if not user or not user.is_authenticated:
            return None
        with transaction.atomic():
            activity = UserActivity.objects.create(
                user=user,
                activity_type=activity_type,
                title=title,
                description=kwargs.get("description", ""),
                target_type=kwargs.get("target_type", ""),
                target_id=str(kwargs.get("target_id", "") or ""),
                target_url=kwargs.get("target_url", ""),
                metadata=kwargs.get("metadata", {}),
                ip_address=kwargs.get("ip_address"),
            )
            stale_ids = list(
                UserActivity.objects.filter(user=user)
                .order_by("-created_at", "-id")
                .values_list("id", flat=True)[cls.MAX_PER_USER :]
            )
            if stale_ids:
                UserActivity.objects.filter(id__in=stale_ids).delete()
            return activity

    @staticmethod
    def client_ip(request):
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        return (forwarded.split(",")[0].strip() if forwarded else None) or request.META.get("REMOTE_ADDR")

