from rest_framework.test import APITestCase

from apps.accounts.models import User
from .models import TraderPost


class SocialV2ContractTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="social-reader", password="pass")
        self.author = User.objects.create_user(username="social-author", password="pass", first_name="Top")
        for index in range(3):
            TraderPost.objects.create(author=self.author, text=f"post {index}")
        self.client.force_authenticate(self.user)

    def test_top_contributors_public_profile_and_posts(self):
        top = self.client.get("/api/chat/social/users/top-contributors/?limit=1")
        self.assertEqual(top.status_code, 200)
        self.assertEqual(top.data[0]["id"], self.author.id)
        self.assertEqual(top.data[0]["posts_count"], 3)
        self.assertNotIn("email", top.data[0])
        profile = self.client.get(f"/api/chat/social/users/{self.author.id}/")
        posts = self.client.get(f"/api/chat/social/users/{self.author.id}/posts/?ordering=-created_at")
        self.assertEqual(profile.status_code, 200)
        self.assertEqual(posts.status_code, 200)
        self.assertEqual(posts.data["count"], 3)

    def test_feed_cursor_pagination_has_stable_next(self):
        response = self.client.get("/api/chat/social/feed/?page_size=2")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["results"]), 2)
        self.assertTrue(response.data["next"])
