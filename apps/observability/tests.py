import logging

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from .models import LogEvent


User = get_user_model()


@override_settings(OBSERVABILITY_SLOW_REQUEST_MS=999999)
class ObservabilityTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.superadmin = User.objects.create_user(
            username="log-admin", password="Pass123!", role=User.Role.SUPER_ADMIN
        )
        self.user = User.objects.create_user(username="normal-log-user", password="Pass123!")

    def test_frontend_error_is_ingested_and_sensitive_context_is_redacted(self):
        response = self.client.post("/api/observability/frontend/", {
            "client_event_id": "event-1",
            "category": "api_error",
            "message": "API request failed",
            "frontend_url": "https://app.sokanex.com/dashboard",
            "context": {"status": 503, "access_token": "must-not-be-stored"},
        }, format="json", HTTP_ORIGIN="https://app.sokanex.com")
        self.assertEqual(response.status_code, 202)
        event = LogEvent.objects.get(source="frontend")
        self.assertEqual(event.context["access_token"], "[REDACTED]")
        self.assertNotIn("must-not-be-stored", str(event.context))

    def test_frontend_event_is_idempotent(self):
        payload = {"client_event_id": "same-event", "category": "javascript_error", "message": "boom"}
        self.assertEqual(self.client.post("/api/observability/frontend/", payload, format="json").status_code, 202)
        self.assertEqual(self.client.post("/api/observability/frontend/", payload, format="json").status_code, 202)
        self.assertEqual(LogEvent.objects.filter(client_event_id="same-event").count(), 1)

    def test_only_superadmin_can_view_logs(self):
        LogEvent.objects.create(source="backend", level="error", category="test", message="failure")
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.get("/api/observability/logs/").status_code, 403)
        self.client.force_authenticate(self.superadmin)
        response = self.client.get("/api/observability/logs/?category=test")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)

    def test_superadmin_can_filter_and_resolve(self):
        event = LogEvent.objects.create(source="backend", level="error", category="provider", message="timeout")
        LogEvent.objects.create(source="frontend", level="warning", category="network_error", message="offline")
        self.client.force_authenticate(self.superadmin)
        response = self.client.get("/api/observability/logs/?source=backend&search=timeout")
        self.assertEqual(response.data["count"], 1)
        resolved = self.client.patch(
            f"/api/observability/logs/{event.pk}/resolve/", {"is_resolved": True}, format="json"
        )
        self.assertEqual(resolved.status_code, 200)
        event.refresh_from_db()
        self.assertTrue(event.is_resolved)
        self.assertEqual(event.resolved_by, self.superadmin)

        filtered = self.client.get("/api/observability/logs/?is_resolved=true")
        self.assertGreaterEqual(filtered.data["count"], 1)
        invalid = self.client.get("/api/observability/logs/?is_resolved=maybe")
        self.assertEqual(invalid.status_code, 400)

    def test_python_warning_is_persisted(self):
        logging.getLogger("apps.test_component").warning("provider temporarily unavailable")
        self.assertTrue(LogEvent.objects.filter(category="python_log", message__icontains="provider").exists())

    def test_validation_log_contains_errors_but_not_request_values(self):
        self.client.force_authenticate(self.user)
        response = self.client.patch(
            "/api/accounts/profile/details/",
            {"exercise_days_per_week": 99, "bio": "private biography"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        event = LogEvent.objects.get(category="validation_error")
        self.assertIn("exercise_days_per_week", event.context["validation_errors"])
        self.assertNotIn("private biography", str(event.context))
