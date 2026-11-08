from django.core.management.base import BaseCommand

from apps.notifications.services import NotificationService


class Command(BaseCommand):
    help = "Retry pending or failed notification SMS deliveries up to the configured limit."

    def add_arguments(self, parser):
        parser.add_argument("--source-prefix", default=None)

    def handle(self, *args, **options):
        NotificationService.send_pending_sms(source_prefix=options["source_prefix"])
        self.stdout.write(self.style.SUCCESS("Notification SMS retry pass completed."))
