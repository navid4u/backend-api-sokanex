from django.core.management.base import BaseCommand

from apps.notifications.services import NotificationService


class Command(BaseCommand):
    help = "Retry pending or failed notification SMS deliveries up to the configured limit."

    def handle(self, *args, **options):
        NotificationService.send_pending_sms()
        self.stdout.write(self.style.SUCCESS("Notification SMS retry pass completed."))
