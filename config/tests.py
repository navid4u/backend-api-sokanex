from unittest.mock import patch

from django.db import DatabaseError
from django.test import TestCase
from django.urls import reverse


class HealthCheckTests(TestCase):
    def test_health_check_returns_healthy_status(
        self
    ):
        response = self.client.get(
            reverse("health-check")
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        data = response.json()

        self.assertEqual(
            data["status"],
            "healthy",
        )
        self.assertEqual(
            data["database"],
            "healthy",
        )
        self.assertEqual(
            data["service"],
            "trading-platform-api",
        )
        self.assertIn(
            "timestamp",
            data,
        )

    @patch(
        "config.views.connection.cursor"
    )
    def test_health_check_returns_503_when_database_fails(
        self,
        mocked_cursor,
    ):
        mocked_cursor.side_effect = (
            DatabaseError(
                "Database unavailable"
            )
        )

        response = self.client.get(
            reverse("health-check")
        )

        self.assertEqual(
            response.status_code,
            503,
        )

        data = response.json()

        self.assertEqual(
            data["status"],
            "unhealthy",
        )
        self.assertEqual(
            data["database"],
            "unhealthy",
        )

        self.assertNotContains(
            response,
            "Database unavailable",
            status_code=503,
        )