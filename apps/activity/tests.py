from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from .models import UserActivity
from .services import ActivityService


User = get_user_model()


class RecentActivityTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="activity-user", password="StrongPass123!")

    def test_only_latest_twenty_five_are_kept(self):
        for index in range(30):
            ActivityService.record(
                self.user, UserActivity.Type.SECURITY, f"Activity {index}"
            )
        activities = UserActivity.objects.filter(user=self.user)
        self.assertEqual(activities.count(), 25)
        self.assertEqual(activities.first().title, "Activity 29")
        self.assertFalse(activities.filter(title="Activity 0").exists())

    def test_recent_activity_endpoint_is_private(self):
        client = APIClient()
        self.assertEqual(client.get("/api/activity/recent/").status_code, 401)
        client.force_authenticate(self.user)
        self.assertEqual(client.get("/api/activity/recent/").status_code, 200)

