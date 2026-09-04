from django.core.management.base import BaseCommand

from apps.accounts.crm import CrmContactSyncService
from apps.accounts.models import CrmContactSync
from django.utils import timezone


class Command(BaseCommand):
    help = "Retry due CRM contact synchronizations."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100)
        parser.add_argument("--reset-all", action="store_true")

    def handle(self, *args, **options):
        if options["reset_all"]:
            CrmContactSyncService.close_circuit()
            CrmContactSync.objects.filter(
                status__in=(
                    CrmContactSync.Status.FAILED,
                    CrmContactSync.Status.DEAD_LETTER,
                )
            ).update(
                status=CrmContactSync.Status.PENDING,
                attempts=0,
                last_error="",
                next_retry_at=timezone.now(),
            )
        processed = CrmContactSyncService.process_pending(limit=max(1, options["limit"]))
        self.stdout.write(self.style.SUCCESS(f"Processed CRM syncs: {processed}"))
