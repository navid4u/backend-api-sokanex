"""Preview/apply one corrected day-one SMS to the fixed October trial cohort."""

import json
import subprocess
import sys

from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import User
from apps.notifications.trial_day_one_reissue import (
    apply_day_one_reissue, preview_day_one_reissue,
)


def _require_stopped_worker():
    if not sys.platform.startswith("linux"):
        return
    for unit, expected in (
        ("sokanex-sms-automation.timer", "inactive"),
        ("sokanex-sms-automation.service", "inactive"),
    ):
        try:
            state = subprocess.run(
                ("systemctl", "is-active", unit), capture_output=True,
                text=True, timeout=5, check=False,
            ).stdout.strip()
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise CommandError(f"Cannot verify {unit} is stopped.") from exc
        if state != expected:
            raise CommandError(f"Stop {unit} before applying; current state is {state or 'unknown'}.")
    try:
        enabled = subprocess.run(
            ("systemctl", "is-enabled", "sokanex-sms-automation.timer"),
            capture_output=True, text=True, timeout=5, check=False,
        ).stdout.strip()
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CommandError("Cannot verify the SMS automation timer is disabled.") from exc
    if enabled != "disabled":
        raise CommandError("Disable the SMS automation timer before applying so a reboot cannot restart it.")


class Command(BaseCommand):
    help = "One-time replacement of campaign day-one SMS, including a second SMS for prior recipients."

    def add_arguments(self, parser):
        parser.add_argument("--actor", required=True)
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--confirm-resend-to-previous-recipients", action="store_true")
        parser.add_argument("--confirm-worker-stopped", action="store_true")
        parser.add_argument("--expected-old-pending", type=int)
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
                result = preview_day_one_reissue(actor=actor)
                result["mode"] = "dry_run"
            else:
                if not options["confirm_resend_to_previous_recipients"]:
                    raise CommandError("Confirm the second SMS to previously contacted users explicitly.")
                if not options["confirm_worker_stopped"]:
                    raise CommandError("Confirm the SMS worker is stopped explicitly.")
                if (options["expected_old_pending"] is None
                        or not options["expected_candidate_digest"]
                        or not options["expected_template_digest"]):
                    raise CommandError("Use the pending count and both digests from a fresh dry run.")
                _require_stopped_worker()
                result = apply_day_one_reissue(
                    actor=actor,
                    expected_pending_count=options["expected_old_pending"],
                    expected_candidate_digest=options["expected_candidate_digest"],
                    expected_template_digest=options["expected_template_digest"],
                )
                result["mode"] = "apply"
        except CommandError:
            raise
        except Exception as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(json.dumps(result, ensure_ascii=False, sort_keys=True, default=str))
