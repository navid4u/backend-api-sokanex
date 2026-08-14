from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.content_channels.models import ChannelPost


class Command(BaseCommand):
    help = "Idempotently publish due internal-analysis posts."

    def handle(self, *args, **options):
        with transaction.atomic():
            count = ChannelPost.objects.filter(
                channel__slug="internal-analysis",
                status=ChannelPost.Status.SCHEDULED,
                published_at__lte=timezone.now(),
            ).update(status=ChannelPost.Status.PUBLISHED)
        self.stdout.write(self.style.SUCCESS(f"Published {count} scheduled analysis post(s)."))
