import logging
from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
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

    def test_detail_returns_single_complete_object_with_nullable_values(self):
        event = LogEvent.objects.create(
            source="backend",
            level="error",
            category="api_error",
            message="Detail failure",
            context={"safe": "value"},
            user=self.user,
            status_code=500,
            duration_ms=17,
        )
        self.client.force_authenticate(self.superadmin)
        response = self.client.get(f"/api/observability/logs/{event.pk}/")
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.data, dict)
        self.assertEqual(set(response.data), {
            "id", "source", "level", "category", "message", "error_type",
            "stack_trace", "context", "request_id", "frontend_url", "release",
            "user_agent", "ip_address", "username", "user", "method", "path",
            "status_code", "duration_ms", "is_resolved", "created_at",
        })
        self.assertEqual(response.data["username"], self.user.username)
        self.assertEqual(response.data["user"]["id"], self.user.pk)
        for field in ("error_type", "stack_trace", "request_id", "frontend_url", "release", "user_agent", "ip_address", "method", "path"):
            self.assertIsNone(response.data[field])
        self.assertEqual(self.client.get("/api/observability/logs/999999/").status_code, 404)

    def test_non_superadmin_cannot_access_any_management_endpoint(self):
        event = LogEvent.objects.create(source="backend", level="error", category="test", message="failure")
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.get("/api/observability/logs/").status_code, 403)
        self.assertEqual(self.client.get("/api/observability/logs/summary/").status_code, 403)
        self.assertEqual(self.client.get(f"/api/observability/logs/{event.pk}/").status_code, 403)
        self.assertEqual(
            self.client.patch(f"/api/observability/logs/{event.pk}/resolve/", {"is_resolved": True}, format="json").status_code,
            403,
        )

    def test_search_is_partial_and_covers_supported_fields(self):
        related = User.objects.create_user(username="search-person", password="Pass123!")
        event = LogEvent.objects.create(
            source="backend",
            level="error",
            category="provider",
            message="Payment gateway timed out",
            path="/api/wallet/purchase/",
            error_type="ProviderTimeoutError",
            request_id="req-unique-123",
            user=related,
            context={"provider": "safe-market-source"},
        )
        LogEvent.objects.create(source="backend", level="warning", category="other", message="unrelated")
        self.client.force_authenticate(self.superadmin)
        for term in ("gateway timed", "wallet/pur", "timeout", "search-pers", "unique-12", "market-source"):
            response = self.client.get("/api/observability/logs/", {"search": term})
            self.assertEqual(response.status_code, 200, term)
            self.assertEqual(response.data["count"], 1, term)
            self.assertEqual(response.data["results"][0]["id"], event.pk, term)

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

    def test_purge_default_removes_only_logs_older_than_five_days_and_summary_uses_remaining(self):
        now = timezone.now()
        old = LogEvent.objects.create(source="backend", level="error", category="old", message="old")
        boundary = LogEvent.objects.create(source="backend", level="warning", category="boundary", message="boundary")
        recent = LogEvent.objects.create(source="frontend", level="error", category="recent", message="recent")
        LogEvent.objects.filter(pk=old.pk).update(created_at=now - timedelta(days=5, microseconds=1))
        LogEvent.objects.filter(pk=boundary.pk).update(created_at=now - timedelta(days=5))

        output = StringIO()
        with patch("apps.observability.management.commands.purge_observability_logs.timezone.now", return_value=now):
            call_command("purge_observability_logs", stdout=output)

        self.assertIn("Deleted observability logs: 1", output.getvalue())
        self.assertFalse(LogEvent.objects.filter(pk=old.pk).exists())
        self.assertEqual(LogEvent.objects.filter(pk__in=(boundary.pk, recent.pk)).count(), 2)
        self.client.force_authenticate(self.superadmin)
        summary = self.client.get("/api/observability/logs/summary/")
        self.assertEqual(summary.status_code, 200)
        self.assertEqual(summary.data["unresolved"], 2)

    def test_purge_all_only_deletes_observability_logs(self):
        LogEvent.objects.create(source="backend", level="error", category="one", message="one")
        LogEvent.objects.create(source="frontend", level="warning", category="two", message="two")
        user_id = self.user.pk
        output = StringIO()
        call_command("purge_observability_logs", "--all", stdout=output)
        self.assertIn("Deleted observability logs: 2", output.getvalue())
        self.assertEqual(LogEvent.objects.count(), 0)
        self.assertTrue(User.objects.filter(pk=user_id).exists())

    def test_frontend_ingest_remains_public(self):
        self.client.credentials(HTTP_AUTHORIZATION="Bearer expired-or-malformed")
        response = self.client.post(
            "/api/observability/frontend/",
            {"category": "network_error", "message": "Public frontend report"},
            format="json",
            HTTP_ORIGIN="https://app.sokanex.com",
        )
        self.assertEqual(response.status_code, 202)

    def test_sanitizer_preserves_status_code_and_redacts_otp_code(self):
        response = self.client.post(
            "/api/observability/frontend/",
            {
                "category": "api_error",
                "message": "Provider failed",
                "context": {"status_code": 503, "otp_code": "123456"},
            },
            format="json",
            HTTP_ORIGIN="https://m.sokanex.com",
        )
        self.assertEqual(response.status_code, 202)
        event = LogEvent.objects.get(message="Provider failed")
        self.assertEqual(event.context["status_code"], 503)
        self.assertEqual(event.context["otp_code"], "[REDACTED]")
