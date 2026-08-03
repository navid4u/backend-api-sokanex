from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from datetime import timedelta
from rest_framework.test import APIClient

from apps.activity.models import UserActivity
from common.phone import normalize_iran_phone

from .models import OTPChallenge, UserDevice, UserProfile


User = get_user_model()


@override_settings(
    PAYAMITO_ENABLED=True,
    PAYAMITO_USERNAME="test-user",
    PAYAMITO_API_KEY="test-key",
    PAYAMITO_FROM_NUMBER="5000",
)
class OTPAuthenticationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="09121234567", phone="09121234567", password="StrongPass123!"
        )
        UserProfile.objects.create(user=self.user)

    def test_phone_normalization_variants(self):
        for value in ("09121234567", "9121234567", "+989121234567", "00989121234567", "989121234567", "۰۹۱۲۱۲۳۴۵۶۷"):
            self.assertEqual(normalize_iran_phone(value), "09121234567")

    @patch("apps.accounts.otp.PayamitoService.send_otp")
    @patch("apps.accounts.otp.secrets.randbelow", return_value=4839)
    def test_request_and_verify_issue_jwt_device_and_activity(self, randbelow, send_otp):
        request_response = self.client.post("/api/accounts/auth/otp/request/", {"phone": "+989121234567"})
        self.assertEqual(request_response.status_code, 200)
        self.assertEqual(request_response.data["data"]["expires_in"], 120)
        challenge = OTPChallenge.objects.get()
        self.assertNotIn("4839", challenge.code_digest)
        send_otp.assert_called_once_with("09121234567", "4839")

        verify_response = self.client.post(
            "/api/accounts/auth/otp/verify/",
            {"phone": "09121234567", "code": "4839"},
            HTTP_X_DEVICE_NAME="OTP test device",
        )
        self.assertEqual(verify_response.status_code, 200)
        self.assertIn("access", verify_response.data["data"])
        self.assertIn("refresh", verify_response.data["data"])
        self.assertTrue(UserDevice.objects.filter(user=self.user).exists())
        self.assertTrue(UserActivity.objects.filter(user=self.user, activity_type="LOGIN").exists())

    @patch("apps.accounts.otp.PayamitoService.send_otp")
    def test_cooldown_returns_429_and_retry_after(self, send_otp):
        self.client.post("/api/accounts/auth/otp/request/", {"phone": "09121234567"})
        response = self.client.post("/api/accounts/auth/otp/request/", {"phone": "09121234567"})
        self.assertEqual(response.status_code, 429)
        self.assertIn("Retry-After", response)

    def test_mobile_registration_is_canonical_and_password_confirmed(self):
        response = self.client.post("/api/accounts/register/", {
            "first_name": "Ali", "last_name": "Ahmadi", "phone": "+989351234567",
            "username": "ignored", "password": "StrongPass123!", "password_confirm": "StrongPass123!",
        })
        self.assertEqual(response.status_code, 201)
        created = User.objects.get(phone="09351234567")
        self.assertEqual(created.username, "09351234567")
        self.assertTrue(created.check_password("StrongPass123!"))

    def test_password_login_accepts_international_phone(self):
        response = self.client.post(
            "/api/token/",
            {"username": "+989121234567", "password": "StrongPass123!"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.data)

    @patch("apps.accounts.otp.PayamitoService.send_otp")
    @patch("apps.accounts.otp.secrets.randbelow", return_value=4839)
    def test_otp_is_single_use(self, randbelow, send_otp):
        self.client.post("/api/accounts/auth/otp/request/", {"phone": self.user.phone})
        payload = {"phone": self.user.phone, "code": "4839"}
        self.assertEqual(self.client.post("/api/accounts/auth/otp/verify/", payload).status_code, 200)
        self.assertEqual(self.client.post("/api/accounts/auth/otp/verify/", payload).status_code, 400)

    @patch("apps.accounts.otp.PayamitoService.send_otp")
    @patch("apps.accounts.otp.secrets.randbelow", return_value=4839)
    def test_expired_otp_is_rejected(self, randbelow, send_otp):
        self.client.post("/api/accounts/auth/otp/request/", {"phone": self.user.phone})
        OTPChallenge.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        response = self.client.post(
            "/api/accounts/auth/otp/verify/", {"phone": self.user.phone, "code": "4839"}
        )
        self.assertEqual(response.status_code, 400)

    @patch("apps.accounts.otp.PayamitoService.send_otp")
    def test_fifth_invalid_attempt_locks_challenge(self, send_otp):
        self.client.post("/api/accounts/auth/otp/request/", {"phone": self.user.phone})
        for _ in range(5):
            self.client.post(
                "/api/accounts/auth/otp/verify/", {"phone": self.user.phone, "code": "0000"}
            )
        challenge = OTPChallenge.objects.get()
        self.assertEqual(challenge.attempts, 5)
        self.assertIsNotNone(challenge.locked_at)

    def test_auth_preflight_allows_app_origin(self):
        response = self.client.options(
            "/api/accounts/auth/otp/request/",
            HTTP_ORIGIN="https://app.sokanex.com",
            HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Access-Control-Allow-Origin"], "https://app.sokanex.com")
