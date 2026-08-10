from django.core.management.base import BaseCommand

from apps.accounts.models import User


class Command(BaseCommand):
    help = "Idempotently create or secure the system support account."

    def handle(self, *args, **options):
        user, created = User.objects.get_or_create(
            username="support",
            defaults={"role": User.Role.EMPLOYEE, "is_active": True},
        )
        changed = []
        if created:
            user.set_unusable_password()
            changed.append("password")
        if not user.is_active:
            user.is_active = True
            changed.append("is_active")
        if user.role not in (User.Role.EMPLOYEE, User.Role.ADMIN, User.Role.SUPER_ADMIN):
            user.role = User.Role.EMPLOYEE
            changed.append("role")
        if changed:
            user.save(update_fields=[*changed, "updated_at"])
        self.stdout.write(self.style.SUCCESS("Support account created." if created else "Support account verified."))
