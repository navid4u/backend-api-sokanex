"""Legacy paid-course rows stay for accounting but no longer gate education."""

from django.urls import reverse
from django.test import override_settings
from rest_framework.test import APITestCase

from apps.accounts.models import User, UserMarketPreference
from .models import Course, CourseEnrollment, CoursePurchase, CourseSession


class FreeAcademyContractTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="free-reader", password="pass")
        self.teacher = User.objects.create_user(username="free-teacher", password="pass", role=User.Role.SUPER_ADMIN)
        self.course = Course.objects.create(
            title="Formerly paid course", instructor=self.teacher,
            status=Course.Status.PUBLISHED, market="forex",
            is_free=False, price=250000, purchase_required=True,
        )
        self.session = CourseSession.objects.create(
            course=self.course, title="Lesson", order=1,
            video_url="https://private.example/video", text="Full lesson text",
        )
        self.client.force_authenticate(self.user)

    def test_historical_paid_course_is_readable_without_purchase_or_enrollment(self):
        course = self.client.get(reverse("academy-course-detail", kwargs={"slug": self.course.slug}))
        self.assertEqual(course.status_code, 200)
        self.assertTrue(course.data["is_free"])
        self.assertEqual(course.data["price"], 0)
        self.assertFalse(course.data["purchase_required"])
        self.assertTrue(course.data["can_access_content"])
        self.assertFalse(course.data["is_enrolled"])
        self.assertNotIn("is_purchased", course.data)

        sessions = self.client.get(reverse("academy-course-sessions", kwargs={"slug": self.course.slug}))
        self.assertFalse(sessions.data["results"][0]["is_locked"])
        detail = self.client.get(reverse("academy-session-detail", kwargs={"pk": self.session.pk}))
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.data["text"], "Full lesson text")
        self.assertEqual(detail.data["video_url"], "https://private.example/video")
        self.assertFalse(CoursePurchase.objects.exists())

    def test_purchase_routes_cannot_charge_and_enrollment_remains_available(self):
        purchase = self.client.post(
            reverse("academy-course-purchase", kwargs={"slug": self.course.slug}),
            {"payment_method": "WALLET"}, format="json",
        )
        self.assertEqual(purchase.status_code, 410)
        self.assertEqual(self.client.get(reverse("academy-course-purchase-status", kwargs={"slug": self.course.slug})).status_code, 410)
        self.assertFalse(CoursePurchase.objects.exists())
        enrolled = self.client.post(reverse("academy-course-enroll", kwargs={"slug": self.course.slug}))
        self.assertEqual(enrolled.status_code, 200)
        self.assertTrue(CourseEnrollment.objects.filter(user=self.user, course=self.course).exists())

    @override_settings(MARKET_ACCESS_V2_ENABLED=True)
    def test_selected_market_still_required_but_purchase_is_not(self):
        detail_url = reverse("academy-course-detail", kwargs={"slug": self.course.slug})
        self.assertEqual(self.client.get(detail_url).status_code, 403)
        UserMarketPreference.objects.create(user=self.user, market="forex")
        self.assertEqual(self.client.get(detail_url).status_code, 200)
        lesson = self.client.get(reverse("academy-session-detail", kwargs={"pk": self.session.pk}))
        self.assertEqual(lesson.status_code, 200)
        self.assertEqual(lesson.data["text"], "Full lesson text")
        self.assertFalse(CoursePurchase.objects.exists())

    def test_new_paid_course_values_are_rejected_but_old_records_are_not_erased(self):
        CoursePurchase.objects.create(user=self.user, course=self.course,
                                      amount_irt=250000, payment_method=CoursePurchase.Method.WALLET)
        self.client.force_authenticate(self.teacher)
        for payload in ({"is_free": False}, {"price": 1000}, {"purchase_required": True}):
            response = self.client.patch(reverse("academy-course-detail", kwargs={"slug": self.course.slug}),
                                         payload, format="json")
            self.assertEqual(response.status_code, 400)
        self.assertEqual(CoursePurchase.objects.filter(course=self.course).count(), 1)
        self.course.refresh_from_db()
        self.assertEqual(self.course.price, 250000)
