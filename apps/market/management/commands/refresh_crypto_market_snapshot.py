from django.core.management.base import BaseCommand, CommandError

from apps.market.services import CryptoSnapshotService, MarketProviderUnavailable


class Command(BaseCommand):
    help = "Refresh the persisted crypto market snapshot outside web workers."

    def handle(self, *args, **options):
        try:
            payload = CryptoSnapshotService.refresh_snapshot()
        except MarketProviderUnavailable as exc:
            raise CommandError("Crypto market snapshot refresh failed.") from exc
        self.stdout.write(self.style.SUCCESS(f"Crypto market snapshot refreshed at {payload['updated_at']}."))
