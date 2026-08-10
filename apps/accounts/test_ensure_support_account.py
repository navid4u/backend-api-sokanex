from django.core.management import call_command
from django.test import TestCase

from .models import User


class EnsureSupportAccountCommandTests(TestCase):
    def test_creates_active_account_without_embedded_password(self):
        User.objects.filter(username="support").delete()
        call_command("ensure_support_account")
        support = User.objects.get(username="support")
        self.assertTrue(support.is_active)
        self.assertFalse(support.has_usable_password())

    def test_preserves_password_set_by_operator(self):
        support, _ = User.objects.get_or_create(username="support")
        support.set_password("OperatorStrongPassword123!")
        support.save()
        call_command("ensure_support_account")
        support.refresh_from_db()
        self.assertTrue(support.check_password("OperatorStrongPassword123!"))
