from django.test import override_settings
from rest_framework.test import APITestCase

from apps.accounts.models import User, UserMarketGrant

from .models import Course, CourseSession


class AcademyMarketV2Tests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="academy-market-owner", role=User.Role.SUPER_ADMIN)
        self.student = User.objects.create_user(username="academy-market-student")
        self.crypto = Course.objects.create(
            title="Crypto course", market="crypto", instructor=self.owner,
            status=Course.Status.PUBLISHED,
        )
        self.forex = Course.objects.create(
            title="Forex course", market="forex", instructor=self.owner,
            status=Course.Status.PUBLISHED,
        )
        self.unclassified = Course.objects.create(
            title="Old course", instructor=self.owner, status=Course.Status.PUBLISHED,
        )
        self.forex_session = CourseSession.objects.create(
            course=self.forex, title="Forex lesson", order=1,
        )
        self.client.force_authenticate(self.student)

    @override_settings(MARKET_ACCESS_V2_ENABLED=True)
    def test_market_gate_list_detail_session_and_enroll(self):
        UserMarketGrant.objects.create(
            user=self.student, market="crypto", source=UserMarketGrant.Source.ADMIN,
            granted_by=self.owner,
        )
        listing = self.client.get("/api/academy/courses/?market=crypto")
        self.assertEqual(listing.status_code, 200)
        self.assertEqual([item["id"] for item in listing.data["results"]], [self.crypto.pk])
        self.assertEqual(listing.data["results"][0]["market"], "crypto")
        self.assertEqual(self.client.get(f"/api/academy/courses/{self.forex.slug}/").status_code, 403)
        self.assertEqual(self.client.get(f"/api/academy/sessions/{self.forex_session.pk}/").status_code, 403)
        self.assertEqual(self.client.post(f"/api/academy/courses/{self.forex.slug}/enroll/").status_code, 403)
        self.assertNotIn(self.unclassified.pk, [row["id"] for row in self.client.get("/api/academy/courses/").data["results"]])

    @override_settings(MARKET_ACCESS_V2_ENABLED=False)
    def test_legacy_visibility_is_retained(self):
        response = self.client.get("/api/academy/courses/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(self.unclassified.pk, [item["id"] for item in response.data["results"]])
