"""Preview or queue the corrected day-three SMS for cancelled recipients only."""

import json

from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import User
from apps.notifications.trial_day_three_reissue import (
    apply_day_three_reissue, preview_day_three_reissue,
)

from .reissue_trial_day_one_sms_20261029 import _require_stopped_worker


class Command(BaseCommand):
    help = "One-time reissue of corrected day-three SMS to cancelled unsent recipients."

    def add_arguments(self, parser):
        parser.add_argument("--actor", required=True)
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--confirm-send-to-cancelled-only", action="store_true")
        parser.add_argument("--confirm-worker-stopped", action="store_true")
        parser.add_argument("--expected-count", type=int)
        parser.add_argument("--expected-candidate-digest")
        parser.add_argument("--expected-template-digest")

    def handle(self, *args, **options):
        actor = User.objects.filter(username=options["actor"]).first()
        if actor is None or not actor.is_active or not (
            actor.is_superuser or actor.role == User.Role.SUPER_ADMIN
        ):
            raise CommandError("--actor must name an active super administrator.")
        try:
            if not options["apply"]:
                result = preview_day_three_reissue(actor=actor)
                result["mode"] = "dry_run"
            else:
                if not options["confirm_send_to_cancelled_only"]:
                    raise CommandError("Confirm the corrected SMS goes only to cancelled unsent recipients.")
                if not options["confirm_worker_stopped"]:
                    raise CommandError("Confirm the SMS worker is stopped explicitly.")
                if (options["expected_count"] is None
                        or not options["expected_candidate_digest"]
                        or not options["expected_template_digest"]):
                    raise CommandError("Use the count and both digests from a fresh dry run.")
                _require_stopped_worker()
                result = apply_day_three_reissue(
                    actor=actor, expected_count=options["expected_count"],
                    expected_candidate_digest=options["expected_candidate_digest"],
                    expected_template_digest=options["expected_template_digest"],
                )
                result["mode"] = "apply"
        except CommandError:
            raise
        except Exception as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(json.dumps(result, ensure_ascii=False, sort_keys=True, default=str))
