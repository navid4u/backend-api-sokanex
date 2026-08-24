from django.core.management.base import BaseCommand

from apps.accounts.models import User


class Command(BaseCommand):
    help = "Idempotently create or secure the system support account."

    def handle(self, *args, **options):
        user, created = User.objects.get_or_create(
            username="support",
            defaults={"role": User.Role.SUPPORT, "is_active": True},
        )
        changed = []
        if created:
            user.set_unusable_password()
            changed.append("password")
        if not user.is_active:
            user.is_active = True
            changed.append("is_active")
        if user.role != User.Role.SUPPORT:
            user.role = User.Role.SUPPORT
            changed.append("role")
        if user.custom_role_id is not None:
            user.custom_role = None
            changed.append("custom_role")
        if user.is_staff:
            user.is_staff = False
            changed.append("is_staff")
        if user.is_superuser:
            user.is_superuser = False
            changed.append("is_superuser")
        if changed:
            user.save(update_fields=[*changed, "updated_at"])
        self.stdout.write(self.style.SUCCESS("Support account created." if created else "Support account verified."))
