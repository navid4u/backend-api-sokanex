"""Preview/apply the explicitly approved one-time seven-day trial restart."""

import json

from django.core.management.base import BaseCommand, CommandError

from apps.accounts.market_trial import (
    preview_all_users_trial_restart, restart_all_users_trial_once,
)
from apps.accounts.models import User


class Command(BaseCommand):
    help = "Preview or apply the fixed one-time seven-day trial restart for ordinary users."

    def add_arguments(self, parser):
        parser.add_argument("--actor", required=True, help="Existing superadmin username")
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--confirm-restart-all-users", action="store_true")
        parser.add_argument("--expected-eligible-count", type=int)
        parser.add_argument("--expected-candidate-digest")

    def handle(self, *args, **options):
        actor = User.objects.filter(username=options["actor"]).first()
        if actor is None or not actor.is_active or not (
            actor.is_superuser or actor.role == User.Role.SUPER_ADMIN
        ):
            raise CommandError("--actor must name an active super administrator.")
        try:
            if not options["apply"]:
                result = preview_all_users_trial_restart(actor=actor)
                result["mode"] = "dry_run"
            else:
                if not options["confirm_restart_all_users"]:
                    raise CommandError("--apply requires --confirm-restart-all-users.")
                if options["expected_eligible_count"] is None or not options["expected_candidate_digest"]:
                    raise CommandError("--apply requires the eligible count and digest from the current dry run.")
                result = restart_all_users_trial_once(
                    actor=actor,
                    expected_eligible_count=options["expected_eligible_count"],
                    expected_candidate_digest=options["expected_candidate_digest"],
                )
                result["mode"] = "apply"
        except CommandError:
            raise
        except Exception as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(json.dumps(result, ensure_ascii=False, sort_keys=True, default=str))
