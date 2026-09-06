from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.observability.models import LogEvent


class Command(BaseCommand):
    help = "Delete observability events older than the configured retention period."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=None)

    def handle(self, *args, **options):
        days = options["days"] or settings.OBSERVABILITY_RETENTION_DAYS
        if days < 1:
            raise ValueError("Retention days must be positive.")
        deleted, _ = LogEvent.objects.filter(created_at__lt=timezone.now() - timedelta(days=days)).delete()
        self.stdout.write(self.style.SUCCESS(f"Deleted observability records: {deleted}"))
