from django.core.management.base import BaseCommand

from apps.notifications.services import NotificationService


class Command(BaseCommand):
    help = "Send queued notification Web Push deliveries."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100)

    def handle(self, *args, **options):
        sent = NotificationService.send_pending_push(limit=max(options["limit"], 1))
        self.stdout.write(self.style.SUCCESS(f"Web Push pass completed; sent={sent}."))
