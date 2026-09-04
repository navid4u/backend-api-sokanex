import json
from io import StringIO
from unittest.mock import MagicMock, patch
from urllib.error import URLError
from urllib.error import HTTPError

from django.test import override_settings
from django.core.management import call_command
from django.utils import timezone
from django.core.cache import cache
from django.urls import reverse
from rest_framework.test import APITestCase

from .crm import CrmContactSyncService
from .models import CrmContactSync, User


@override_settings(
    CRM_ENABLED=True,
    CRM_API_KEY="secret-test-key",
    CRM_BASE_URL="https://navaphone.com",
    CRM_TIMEOUT_SECONDS=1,
    CRM_MAX_ATTEMPTS=3,
    CRM_RETRY_BASE_SECONDS=1,
    CRM_FOLLOWUP_OPERATOR="operator-1",
)
class CrmContactSyncTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="09121234567", phone="09121234567",
            first_name="علی", last_name="احمدی", email="ali@example.com",
            password="StrongPass123!",
        )
        cache.clear()
        self.sync = CrmContactSyncService.queue_user(self.user.pk)

    @staticmethod
    def response(payload, status=200):
        response = MagicMock()
        response.getcode.return_value = status
        response.read.return_value = json.dumps(payload).encode()
        response.__enter__.return_value = response
        return response

    @patch("apps.accounts.crm.request.urlopen")
    def test_success_and_identical_payload_are_idempotent(self, urlopen):
        urlopen.return_value = self.response({"status": 1000, "data": {"ulid": "01CRMULID"}})
        CrmContactSyncService.sync(self.sync)
        self.sync.refresh_from_db()
        self.assertEqual(self.sync.status, CrmContactSync.Status.SYNCED)
        self.assertEqual(self.sync.remote_ulid, "01CRMULID")
        CrmContactSyncService.queue_user(self.user.pk)
        self.assertEqual(urlopen.call_count, 1)
        sent = json.loads(urlopen.call_args.args[0].data.decode())
        self.assertEqual(sent["phone_number"], "989121234567")
        self.assertNotIn("secret-test-key", json.dumps(sent))

    @patch("apps.accounts.crm.request.urlopen", side_effect=URLError("offline"))
    def test_timeout_is_retried_without_breaking_profile_save(self, urlopen):
        self.client.force_authenticate(self.user)
        response = self.client.patch(
            "/api/accounts/profile/", {"first_name": " علیرضا ", "last_name": " احمدی "}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "علیرضا")
        CrmContactSyncService.sync(self.sync)
        self.sync.refresh_from_db()
        self.assertEqual(self.sync.status, CrmContactSync.Status.FAILED)
        self.assertIsNotNone(self.sync.next_retry_at)

    @patch("apps.accounts.crm.request.urlopen")
    def test_token_expired_code_is_recorded(self, urlopen):
        urlopen.return_value = self.response({"status": 2001, "data": {}})
        CrmContactSyncService.sync(self.sync)
        self.sync.refresh_from_db()
        self.assertEqual(self.sync.last_response_code, "2001")
        self.assertEqual(self.sync.status, CrmContactSync.Status.FAILED)
        self.assertIsNone(self.sync.next_retry_at)
        self.assertEqual(CrmContactSyncService.circuit_state()["reason"], "auth_error")

    @patch("apps.accounts.crm.request.urlopen")
    def test_http_auth_errors_open_circuit_without_retry(self, urlopen):
        urlopen.side_effect = HTTPError("https://navaphone.com", 401, "Unauthorized", {}, None)
        CrmContactSyncService.sync(self.sync)
        self.sync.refresh_from_db()
        self.assertEqual(self.sync.status, CrmContactSync.Status.FAILED)
        self.assertIsNone(self.sync.next_retry_at)
        self.assertEqual(self.sync.last_response_code, "401")

    @patch("apps.accounts.crm.request.urlopen")
    def test_login_refresh_register_and_profile_never_call_crm_http(self, urlopen):
        login = self.client.post(
            "/api/token/", {"username": self.user.username, "password": "StrongPass123!"}, format="json"
        )
        self.assertEqual(login.status_code, 200)
        refresh = self.client.post("/api/token/refresh/", {"refresh": login.data["refresh"]}, format="json")
        self.assertEqual(refresh.status_code, 200)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
        self.assertEqual(self.client.get("/api/dashboard/").status_code, 200)
        self.assertEqual(
            self.client.patch("/api/accounts/profile/", {"first_name": "رضا"}, format="json").status_code,
            200,
        )
        self.client.credentials()
        registration = self.client.post(
            "/api/accounts/register/",
            {
                "phone": "09351234567", "first_name": "مینا", "last_name": "محمدی",
                "password": "AnotherStrong123!", "password_confirm": "AnotherStrong123!",
            },
            format="json",
        )
        self.assertEqual(registration.status_code, 201)
        urlopen.assert_not_called()

    @patch("apps.accounts.crm.request.urlopen")
    def test_retry_management_command_processes_due_job(self, urlopen):
        urlopen.return_value = self.response({"status": 1000, "data": {"ulid": "RETRYULID"}})
        self.sync.next_retry_at = timezone.now()
        self.sync.save(update_fields=("next_retry_at", "updated_at"))
        output = StringIO()
        call_command("retry_crm_syncs", limit=10, stdout=output)
        self.sync.refresh_from_db()
        self.assertEqual(self.sync.status, CrmContactSync.Status.SYNCED)
        self.assertIn("Processed CRM syncs: 1", output.getvalue())

    @patch("apps.accounts.crm.request.urlopen")
    def test_changed_synced_contact_requires_review_not_duplicate(self, urlopen):
        urlopen.return_value = self.response({"status": 1000, "data": {"ulid": "01CRMULID"}})
        CrmContactSyncService.sync(self.sync)
        self.user.first_name = "رضا"
        self.user.save(update_fields=("first_name", "updated_at"))
        sync = CrmContactSyncService.queue_user(self.user.pk)
        self.assertEqual(sync.status, CrmContactSync.Status.NEEDS_REVIEW)
        self.assertEqual(urlopen.call_count, 1)

    def test_admin_api_and_public_profile_status(self):
        self.client.force_authenticate(self.user)
        profile = self.client.get("/api/accounts/profile/")
        self.assertEqual(profile.data["crm_sync_status"], "pending")
        self.assertEqual(self.client.get(reverse("crm-sync-list")).status_code, 403)
        admin = User.objects.create_user(username="crm-admin", role=User.Role.ADMIN)
        self.client.force_authenticate(admin)
        self.assertEqual(self.client.get(reverse("crm-sync-list")).status_code, 200)
        health = self.client.get(reverse("crm-integration-health"))
        self.assertEqual(health.status_code, 200)
        self.assertIn(health.data["status"], ("configured", "degraded", "healthy"))

    def test_profile_name_validation_and_completion_contract(self):
        self.client.force_authenticate(self.user)
        invalid = self.client.patch(
            "/api/accounts/profile/", {"first_name": " ا ", "last_name": " ب "}, format="json"
        )
        self.assertEqual(invalid.status_code, 400)
        self.assertIn("first_name", invalid.data["errors"])
        valid = self.client.patch(
            "/api/accounts/profile/", {"first_name": " علی ", "last_name": " احمدی "}, format="json"
        )
        self.assertEqual(valid.status_code, 200)
        self.assertEqual(valid.data["user"]["first_name"], "علی")
        self.assertIn("profile_complete", valid.data["user"])
        self.assertIn("missing_profile_fields", valid.data["user"])
