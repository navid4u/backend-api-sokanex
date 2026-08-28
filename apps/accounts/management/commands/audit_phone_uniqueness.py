from collections import defaultdict

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand

from apps.accounts.models import User
from common.phone import normalize_iran_phone


class Command(BaseCommand):
    help = "Read-only audit of canonical Iranian phone conflicts; never merges users."

    def handle(self, *args, **options):
        canonical_users = defaultdict(list)
        invalid = []
        for user in User.objects.exclude(phone__isnull=True).exclude(phone="").iterator():
            try:
                canonical = normalize_iran_phone(user.phone)
            except ValidationError:
                invalid.append((user.pk, user.phone))
                continue
            canonical_users[canonical].append((user.pk, user.username, user.phone))

        conflicts = {
            phone: users for phone, users in canonical_users.items() if len(users) > 1
        }
        for phone, users in sorted(conflicts.items()):
            self.stdout.write(f"CONFLICT {phone}: {users}")
        for user_id, phone in invalid:
            self.stdout.write(f"INVALID user_id={user_id} phone={phone!r}")
        self.stdout.write(
            self.style.SUCCESS(
                f"Audit complete: conflicts={len(conflicts)} invalid={len(invalid)}; no data changed."
            )
        )
