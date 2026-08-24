from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.wallet.models import Payment


class Command(BaseCommand):
    help = "Report stale pending payments for provider-side reconciliation."

    def add_arguments(self, parser):
        parser.add_argument("--minutes", type=int, default=30)

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(minutes=max(options["minutes"], 1))
        queryset = Payment.objects.filter(status=Payment.Status.PENDING, updated_at__lt=cutoff)
        self.stdout.write(f"stale_pending={queryset.count()}")
        for payment in queryset.order_by("created_at").iterator():
            self.stdout.write(f"{payment.id} {payment.provider.code}")
