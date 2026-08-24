from django.urls import reverse
from rest_framework.test import APITestCase

from apps.accounts.models import User
from .models import Course, CourseEnrollment, CoursePurchase, CourseSession


class PaidCourseContentAccessTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="paid-reader", password="pass")
        self.teacher = User.objects.create_user(username="paid-teacher", password="pass")
        self.course = Course.objects.create(
            title="Protected paid course",
            instructor=self.teacher,
            status=Course.Status.PUBLISHED,
            is_free=False,
            price=250000,
            purchase_required=True,
        )
        self.session = CourseSession.objects.create(
            course=self.course,
            title="Private session",
            order=1,
            video_url="https://private.example/video",
            text="Full private lesson text",
            is_preview=True,
        )
        self.client.force_authenticate(self.user)

    def test_paid_course_flags_and_session_content_are_protected(self):
        course_response = self.client.get(
            reverse("academy-course-detail", kwargs={"slug": self.course.slug})
        )
        self.assertEqual(course_response.status_code, 200)
        self.assertFalse(course_response.data["is_enrolled"])
        self.assertFalse(course_response.data["is_purchased"])
        self.assertFalse(course_response.data["can_access_content"])

        sessions = self.client.get(
            reverse("academy-course-sessions", kwargs={"slug": self.course.slug})
        )
        item = sessions.data["results"][0]
        self.assertTrue(item["is_locked"])
        self.assertEqual(item["video_url"], "")
        self.assertIsNone(item["video_file"])
        self.assertIsNone(item["audio_file"])
        self.assertEqual(item["text"], "")
        self.assertIsNone(item["image"])

        detail = self.client.get(
            reverse("academy-session-detail", kwargs={"pk": self.session.pk})
        )
        ticket = self.client.post(
            reverse("academy-media-ticket", kwargs={"pk": self.session.pk}), {}
        )
        self.assertEqual(detail.status_code, 403)
        self.assertEqual(ticket.status_code, 403)

    def test_purchase_and_enrollment_unlock_content(self):
        CoursePurchase.objects.create(
            user=self.user,
            course=self.course,
            amount_irt=self.course.price,
            payment_method=CoursePurchase.Method.WALLET,
        )
        CourseEnrollment.objects.create(user=self.user, course=self.course)

        course_response = self.client.get(
            reverse("academy-course-detail", kwargs={"slug": self.course.slug})
        )
        self.assertTrue(course_response.data["is_enrolled"])
        self.assertTrue(course_response.data["is_purchased"])
        self.assertTrue(course_response.data["can_access_content"])

        detail = self.client.get(
            reverse("academy-session-detail", kwargs={"pk": self.session.pk})
        )
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.data["video_url"], "https://private.example/video")
        self.assertEqual(detail.data["text"], "Full private lesson text")
