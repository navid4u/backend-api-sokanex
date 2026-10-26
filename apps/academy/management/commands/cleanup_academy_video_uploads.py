from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.academy.chunk_uploads import remove_staging_file
from apps.academy.models import AcademyVideoUpload


class Command(BaseCommand):
    help = "Expire stale academy video uploads and remove their private staging files."

    def handle(self, *args, **options):
        now = timezone.now()
        stale = Q(status=AcademyVideoUpload.Status.PENDING, expires_at__lte=now) | Q(
            status__in=(AcademyVideoUpload.Status.COMPLETED, AcademyVideoUpload.Status.CANCELLED),
            updated_at__lte=now - timedelta(hours=1),
        )
        cleaned = 0
        for upload_id in AcademyVideoUpload.objects.filter(stale).values_list("pk", flat=True).iterator():
            with transaction.atomic():
                upload = AcademyVideoUpload.objects.select_for_update().get(pk=upload_id)
                if upload.status == AcademyVideoUpload.Status.PENDING:
                    if upload.expires_at > timezone.now():
                        continue
                    upload.status = AcademyVideoUpload.Status.EXPIRED
                    upload.save(update_fields=["status", "updated_at"])
                elif upload.status not in (AcademyVideoUpload.Status.COMPLETED, AcademyVideoUpload.Status.CANCELLED):
                    continue
                remove_staging_file(upload)
                cleaned += 1
        self.stdout.write(f"Academy video staging files cleaned: {cleaned}")
