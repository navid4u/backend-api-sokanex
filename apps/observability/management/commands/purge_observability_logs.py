from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.observability.models import LogEvent


class Command(BaseCommand):
    help = "Permanently delete observability log events only."

    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group()
        group.add_argument(
            "--days",
            type=int,
            default=5,
            help="Delete logs older than this many days (default: 5).",
        )
        group.add_argument(
            "--all",
            action="store_true",
            dest="purge_all",
            help="Delete every observability log event.",
        )

    def handle(self, *args, **options):
        if options["purge_all"]:
            queryset = LogEvent.objects.all()
        else:
            days = options["days"]
            if days < 1:
                raise CommandError("--days must be a positive integer.")
            cutoff = timezone.now() - timedelta(days=days)
            queryset = LogEvent.objects.filter(created_at__lt=cutoff)

        with transaction.atomic():
            log_count = queryset.count()
            queryset.delete()

        self.stdout.write(self.style.SUCCESS(f"Deleted observability logs: {log_count}"))
