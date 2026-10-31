"""One-off, guarded cancellation of queued day-three campaign SMS."""

import json

from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import User
from apps.notifications.trial_day_three_cancel import (
    apply_day_three_cancel, preview_day_three_cancel,
)

from .reissue_trial_day_one_sms_20261029 import _require_stopped_worker


class Command(BaseCommand):
    help = "Cancel unsent day-three SMS for the fixed October 2026 trial campaign."

    def add_arguments(self, parser):
        parser.add_argument("--actor", required=True)
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--confirm-worker-stopped", action="store_true")
        parser.add_argument("--expected-pending-count", type=int)
        parser.add_argument("--expected-pending-digest")

    def handle(self, *args, **options):
        actor = User.objects.filter(username=options["actor"]).first()
        if actor is None or not actor.is_active or not (
            actor.is_superuser or actor.role == User.Role.SUPER_ADMIN
        ):
            raise CommandError("--actor must name an active super administrator.")
        try:
            if not options["apply"]:
                result = preview_day_three_cancel(actor=actor)
                result["mode"] = "dry_run"
            else:
                if not options["confirm_worker_stopped"]:
                    raise CommandError("Confirm the SMS worker is stopped explicitly.")
                if (options["expected_pending_count"] is None
                        or not options["expected_pending_digest"]):
                    raise CommandError("Use the count and digest from a fresh dry run.")
                _require_stopped_worker()
                result = apply_day_three_cancel(
                    actor=actor,
                    expected_pending_count=options["expected_pending_count"],
                    expected_pending_digest=options["expected_pending_digest"],
                )
                result["mode"] = "apply"
        except CommandError:
            raise
        except Exception as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(json.dumps(result, ensure_ascii=False, sort_keys=True, default=str))
