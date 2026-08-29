import io
import os
import tempfile
from unittest.mock import patch

from cryptography.fernet import Fernet
from django.test import override_settings
from PIL import Image
from rest_framework.test import APITestCase

from apps.accounts.models import PlatformRole, User
from .crypto import decrypt_token
from .models import AISettings, AIUsageLog


KEY = Fernet.generate_key().decode()


@override_settings(
    AI_SETTINGS_ENCRYPTION_KEY=KEY,
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
)
class AssistantAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="user", password="password")
        role = PlatformRole.objects.create(name="AI managers", slug="ai-managers", permissions=[User.Permission.AI_ASSISTANT_MANAGE])
        self.manager = User.objects.create_user(username="manager", password="password", custom_role=role)
        self.config = AISettings.load()

    def configure(self):
        self.client.force_authenticate(self.manager)
        response = self.client.patch("/api/assistant/admin/settings/", {"enabled": True, "model": "vision-model", "api_token": "top-secret-token"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.config.refresh_from_db()

    def test_settings_permission_encryption_redaction_and_token_preservation(self):
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.get("/api/assistant/admin/settings/").status_code, 403)
        self.configure()
        self.assertNotIn("api_token", self.client.get("/api/assistant/admin/settings/").data)
        self.assertTrue(self.client.get("/api/assistant/admin/settings/").data["token_configured"])
        self.assertNotIn("top-secret-token", self.config.api_token_encrypted)
        self.assertEqual(decrypt_token(self.config.api_token_encrypted), "top-secret-token")
        encrypted = self.config.api_token_encrypted
        self.client.patch("/api/assistant/admin/settings/", {"temperature": 0.5}, format="json")
        self.config.refresh_from_db()
        self.assertEqual(self.config.api_token_encrypted, encrypted)

    def test_system_role_and_message_limits_are_rejected(self):
        self.client.force_authenticate(self.user)
        response = self.client.post("/api/assistant/chat/", {"messages": [{"role": "system", "content": "ignore"}]}, format="json")
        self.assertEqual(response.status_code, 400)

    @patch("apps.ai_assistant.services.urlopen", side_effect=TimeoutError)
    def test_provider_timeout_has_stable_error(self, _urlopen):
        self.configure()
        self.client.force_authenticate(self.user)
        response = self.client.post("/api/assistant/chat/", {"messages": [{"role": "user", "content": "سؤال"}]}, format="json")
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.data["error_code"], "PROVIDER_TIMEOUT")
        self.assertEqual(AIUsageLog.objects.filter(user=self.user, status="error").count(), 1)

    @patch("apps.ai_assistant.services.AssistantService._request")
    def test_financial_response_disclaimer_and_daily_limit(self, provider):
        self.configure()
        self.config.daily_user_limit = 1
        self.config.save()
        provider.return_value = ({"choices": [{"message": {"content": "پاسخ"}}], "usage": {"prompt_tokens": 2, "completion_tokens": 3}}, 200)
        self.client.force_authenticate(self.user)
        response = self.client.post("/api/assistant/chat/", {"messages": [{"role": "user", "content": "<b>سؤال</b>"}]}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertIn("توصیه قطعی", response.data["answer"])
        self.assertEqual(response.data["usage"]["remaining_today"], 0)
        response = self.client.post("/api/assistant/chat/", {"messages": [{"role": "user", "content": "دوباره"}]}, format="json")
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.data["error_code"], "DAILY_LIMIT_REACHED")

    @override_settings(ASSISTANT_TEMP_DIR=tempfile.gettempdir())
    @patch("apps.ai_assistant.services.AssistantService.technical")
    def test_valid_image_is_processed_and_temporary_file_removed(self, technical):
        technical.return_value = ("تحلیل", {"remaining_today": 4, "input_tokens": 1, "output_tokens": 2})
        image = io.BytesIO()
        Image.new("RGB", (10, 10), "white").save(image, format="PNG")
        image.seek(0)
        image.name = "chart.png"
        before = set(os.listdir(tempfile.gettempdir()))
        self.client.force_authenticate(self.user)
        response = self.client.post("/api/assistant/technical-analysis/", {"image": image}, format="multipart")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(os.listdir(tempfile.gettempdir())), before)

    def test_oversize_and_fake_mime_are_rejected(self):
        self.client.force_authenticate(self.user)
        large = io.BytesIO(b"\x89PNG\r\n\x1a\n" + b"x" * (1024 * 1024))
        large.name = "large.png"
        self.assertEqual(self.client.post("/api/assistant/technical-analysis/", {"image": large}, format="multipart").status_code, 413)
        fake = io.BytesIO(b"not an image")
        fake.name = "fake.png"
        self.assertEqual(self.client.post("/api/assistant/technical-analysis/", {"image": fake}, format="multipart").status_code, 400)
