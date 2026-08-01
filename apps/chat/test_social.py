from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient


User = get_user_model()


class SocialNetworkAPITests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="social-one", password="StrongPass123!")
        self.other = User.objects.create_user(username="social-two", password="StrongPass123!")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_post_reaction_comment_save_and_follow_flow(self):
        response = self.client.post("/api/chat/social/feed/", {"text": "Market update"})
        self.assertEqual(response.status_code, 201)
        post_id = response.data["id"]
        self.assertEqual(
            self.client.post(f"/api/chat/social/posts/{post_id}/reaction/", {"reaction_type": "INSIGHTFUL"}).status_code,
            200,
        )
        self.assertEqual(
            self.client.post(f"/api/chat/social/posts/{post_id}/comments/", {"text": "Useful"}).status_code,
            201,
        )
        self.assertEqual(self.client.post(f"/api/chat/social/posts/{post_id}/save/").status_code, 200)
        self.assertEqual(self.client.post(f"/api/chat/social/users/{self.other.id}/follow/").status_code, 200)

    def test_user_cannot_edit_another_users_post(self):
        self.client.force_authenticate(self.other)
        post = self.client.post("/api/chat/social/feed/", {"text": "Other post"}).data
        self.client.force_authenticate(self.user)
        response = self.client.patch(f"/api/chat/social/posts/{post['id']}/", {"text": "Changed"})
        self.assertEqual(response.status_code, 400)

