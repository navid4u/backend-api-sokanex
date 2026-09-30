from django.core.management.base import BaseCommand

from apps.accounts.services import PremiumAccessService


class Command(BaseCommand):
    help = "Downgrade expired seven-day Gold trials to access level 2."

    def handle(self, *args, **options):
        count = PremiumAccessService.expire_trials()
        self.stdout.write(self.style.SUCCESS(f"Expired Gold trials updated: {count}."))
