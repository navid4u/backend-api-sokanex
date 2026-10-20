from django.core.management.base import BaseCommand
from apps.accounts.market_trial import audit_expired_trials

from apps.notifications.sms_automation import queue_due_trial_messages, send_pending
from apps.notifications.trial_journey import queue_due_trial_journey


class Command(BaseCommand):
    help = "Queue today's due trial SMS and send pending automation/broadcast SMS."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100)

    def handle(self, *args, **options):
        limit = options["limit"]
        if limit < 1 or limit > 1000:
            raise ValueError("--limit must be between 1 and 1000")
        journey_queued = queue_due_trial_journey()
        queued = queue_due_trial_messages()
        sent = send_pending(limit=limit)
        expired_audited = audit_expired_trials(limit=limit)
        self.stdout.write(f"SMS automation pass: queued={queued} journey_dispatched={journey_queued} sent={sent} expired_audited={expired_audited}")
