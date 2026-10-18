"""Explicit production gate: no retrospective enrollment or provider calls."""

import json

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.market_access import market_access_v2_enabled
from apps.notifications.models import (
    SMSAutomationDelivery, SMSAutomationRule, TrialJourneyActivation, TrialJourneyDay,
)


class Command(BaseCommand):
    help = "Preview or explicitly activate the canonical seven-day journey for future grants."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--confirm", action="store_true")

    def handle(self, *args, **options):
        ready = TrialJourneyDay.objects.count() == 7
        existing = TrialJourneyActivation.objects.filter(pk=1).first()
        summary = {
            "mode": "apply" if options["apply"] else "dry_run",
            "already_active": existing is not None,
            "configured_days": TrialJourneyDay.objects.count(),
            "legacy_enabled_rules": SMSAutomationRule.objects.filter(
                event__in=("TRIAL", "WELCOME"), enabled=True,
            ).count(),
            "legacy_pending_deliveries": SMSAutomationDelivery.objects.filter(
                event__in=("TRIAL", "WELCOME"), status="PENDING",
            ).count(),
            "v2_enabled": market_access_v2_enabled(),
            "journey_kill_switch_enabled": settings.TRIAL_JOURNEY_ENABLED,
        }
        if options["apply"]:
            if not options["confirm"]:
                raise CommandError("--apply requires --confirm after backup and operator approval.")
            if not ready or not market_access_v2_enabled() or not settings.TRIAL_JOURNEY_ENABLED:
                raise CommandError("Seven days, Market Access V2 and TRIAL_JOURNEY_ENABLED are required.")
            with transaction.atomic():
                SMSAutomationRule.objects.filter(event__in=("TRIAL", "WELCOME")).update(enabled=False)
                SMSAutomationDelivery.objects.filter(
                    event__in=("TRIAL", "WELCOME"), status="PENDING",
                ).update(status="SKIPPED", failure_code="REPLACED_BY_TRIAL_JOURNEY")
                activation, _ = TrialJourneyActivation.objects.get_or_create(
                    pk=1, defaults={"activated_at": timezone.now()},
                )
                summary["activated_at"] = activation.activated_at.isoformat()
        self.stdout.write(json.dumps(summary, ensure_ascii=False, sort_keys=True))
