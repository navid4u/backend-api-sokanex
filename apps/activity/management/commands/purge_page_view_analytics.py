"""Delete only already-aggregated raw page views and expired daily rollups."""

from datetime import timedelta
from zoneinfo import ZoneInfo

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.activity.models import PageViewDailyAggregate, PageViewEvent, PageViewReceipt


class Command(BaseCommand):
    help = "Purge aggregated page-view events after 30 days and daily rollups after 400 days."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Perform deletion; default is a dry run")

    def handle(self, *args, **options):
        now = timezone.now()
        raw = PageViewEvent.objects.filter(
            created_at__lt=now - timedelta(days=30), aggregated_at__isnull=False,
        )
        daily = PageViewDailyAggregate.objects.filter(
            day__lt=timezone.localtime(now, ZoneInfo("Asia/Tehran")).date() - timedelta(days=400),
        )
        receipts = PageViewReceipt.objects.filter(created_at__lt=now - timedelta(days=400))
        raw_count, daily_count, receipt_count = raw.count(), daily.count(), receipts.count()
        if options["apply"]:
            # Small indexed batches avoid an unbounded ORM Collector allocation.
            for queryset in (raw, daily, receipts):
                while True:
                    ids = list(queryset.order_by("pk").values_list("pk", flat=True)[:5000])
                    if not ids:
                        break
                    queryset.model.objects.filter(pk__in=ids).delete()
        self.stdout.write(
            f"mode={'apply' if options['apply'] else 'dry_run'} raw_deleted={raw_count if options['apply'] else 0} "
            f"daily_deleted={daily_count if options['apply'] else 0} receipts_deleted={receipt_count if options['apply'] else 0} "
            f"raw_eligible={raw_count} daily_eligible={daily_count} receipts_eligible={receipt_count}"
        )
