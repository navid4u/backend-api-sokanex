from django.core.management.base import BaseCommand

from apps.accounts.crm import CrmContactSyncService


class Command(BaseCommand):
    help = "Retry due CRM contact synchronizations."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100)

    def handle(self, *args, **options):
        processed = CrmContactSyncService.process_pending(limit=max(1, options["limit"]))
        self.stdout.write(self.style.SUCCESS(f"Processed CRM syncs: {processed}"))
