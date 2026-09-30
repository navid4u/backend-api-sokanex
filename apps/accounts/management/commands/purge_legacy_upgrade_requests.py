from django.core.management.base import BaseCommand
from django.db import transaction

from apps.accounts.models import UpgradeRequest


class Command(BaseCommand):
    help = "Delete upgrade-request history after an explicit, backed-up rollout."

    def add_arguments(self, parser):
        parser.add_argument(
            "--confirm",
            action="store_true",
            help="Confirm deletion of all UpgradeRequest rows.",
        )

    def handle(self, *args, **options):
        if not options["confirm"]:
            self.stdout.write(
                self.style.WARNING(
                    "No changes made. Rerun with --confirm after verifying a database backup."
                )
            )
            return

        with transaction.atomic():
            queryset = UpgradeRequest.objects.all()
            count = queryset.count()
            queryset.delete()

        self.stdout.write(self.style.SUCCESS(f"UpgradeRequest rows deleted: {count}"))
