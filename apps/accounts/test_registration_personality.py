from datetime import timedelta
from unittest.mock import patch

from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework_simplejwt.tokens import AccessToken
from rest_framework.test import APIClient

from apps.activity.models import UserActivity
from .models import FinancialPersonalityAssessment, OTPChallenge, User, UserDevice


@override_settings(
    PAYAMITO_ENABLED=True,
    PAYAMITO_USERNAME="test-user",
    PAYAMITO_API_KEY="test-key",
    PAYAMITO_FROM_NUMBER="5000",
)
class RegistrationOTPTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()

    def request_code(self, phone="+989121234567", code=4839):
        with patch("apps.accounts.otp.secrets.randbelow", return_value=code), patch(
            "apps.accounts.otp.PayamitoService.send_otp"
        ) as send:
            response = self.client.post(
                "/api/accounts/auth/registration/request/", {"phone": phone}
            )
        return response, send

    def test_new_phone_registers_once_and_returns_usable_jwt(self):
        requested, send = self.request_code()
        self.assertEqual(requested.status_code, 200)
        self.assertEqual(requested.data["expires_in"], 120)
        self.assertEqual(requested.data["resend_after"], 60)
        send.assert_called_once_with("09121234567", "4839")
        challenge = OTPChallenge.objects.get()
        self.assertEqual(challenge.purpose, OTPChallenge.Purpose.REGISTRATION_LOGIN)
        self.assertNotIn("4839", challenge.code_digest)

        verified = self.client.post(
            "/api/accounts/auth/registration/verify/",
            {"phone": "۰۹۱۲۱۲۳۴۵۶۷", "code": "4839"},
            HTTP_X_DEVICE_ID="registration-browser",
        )
        self.assertEqual(verified.status_code, 200)
        self.assertTrue(verified.data["created"])
        self.assertIn("access", verified.data)
        self.assertIn("refresh", verified.data)
        self.assertTrue(verified.data["profile_incomplete"])
        self.assertIn("first_name", verified.data["missing_profile_fields"])
        user = User.objects.get(phone="09121234567")
        self.assertEqual(user.username, "09121234567")
        self.assertEqual(user.role, User.Role.USER)
        self.assertEqual(user.access_level, 1)
        self.assertFalse(user.has_usable_password())
        self.assertTrue(user.is_verified)
        self.assertTrue(UserDevice.objects.filter(user=user).exists())
        self.assertTrue(
            UserActivity.objects.filter(user=user, activity_type=UserActivity.Type.REGISTER).exists()
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {verified.data['access']}")
        self.assertEqual(self.client.get("/api/dashboard/").status_code, 200)

    @override_settings(CRM_ENABLED=True, CRM_API_KEY="wrong-key")
    @patch("apps.accounts.crm.request.urlopen")
    def test_otp_verify_is_fail_open_and_never_calls_crm_http(self, urlopen):
        requested, _ = self.request_code(phone="09351234567")
        self.assertEqual(requested.status_code, 200)
        verified = self.client.post(
            "/api/accounts/auth/registration/verify/",
            {"phone": "09351234567", "code": "4839"},
        )
        self.assertEqual(verified.status_code, 200)
        self.assertIn("access", verified.data)
        urlopen.assert_not_called()

    def test_existing_user_logs_in_without_creating_another_user(self):
        user = User.objects.create_user(
            username="09121234567", phone="09121234567", password="OldPassword123!"
        )
        self.request_code()
        response = self.client.post(
            "/api/accounts/auth/registration/verify/",
            {"phone": "989121234567", "code": "4839"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["created"])
        self.assertEqual(response.data["user"]["id"], user.pk)
        self.assertEqual(User.objects.filter(phone="09121234567").count(), 1)
        self.assertTrue(
            UserActivity.objects.filter(user=user, activity_type=UserActivity.Type.LOGIN).exists()
        )
        password_login = self.client.post(
            "/api/token/", {"username": user.username, "password": "OldPassword123!"}
        )
        self.assertEqual(password_login.status_code, 200)

    def test_request_response_does_not_enumerate_users(self):
        User.objects.create_user(username="09121234567", phone="09121234567")
        existing, _ = self.request_code()
        OTPChallenge.objects.update(created_at=timezone.now() - timedelta(seconds=61))
        cache.clear()
        new, _ = self.request_code(phone="09351234567")
        self.assertEqual(existing.status_code, new.status_code)
        self.assertEqual(existing.data, new.data)

    def test_replay_expiration_bruteforce_and_purpose_isolation(self):
        self.request_code()
        payload = {"phone": "09121234567", "code": "4839"}
        self.assertEqual(
            self.client.post("/api/accounts/auth/registration/verify/", payload).status_code,
            200,
        )
        replay = self.client.post("/api/accounts/auth/registration/verify/", payload)
        self.assertEqual(replay.status_code, 400)
        self.assertEqual(replay.data["error_code"], "INVALID_OTP")

        OTPChallenge.objects.all().delete()
        cache.clear()
        self.request_code(phone="09351234567")
        OTPChallenge.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        expired = self.client.post(
            "/api/accounts/auth/registration/verify/",
            {"phone": "09351234567", "code": "4839"},
        )
        self.assertEqual(expired.status_code, 400)

        OTPChallenge.objects.all().delete()
        cache.clear()
        self.request_code(phone="09361234567")
        for _ in range(5):
            self.client.post(
                "/api/accounts/auth/registration/verify/",
                {"phone": "09361234567", "code": "0000"},
            )
        self.assertIsNotNone(OTPChallenge.objects.get().locked_at)

    def test_inactive_user_is_rejected_with_machine_code(self):
        User.objects.create_user(
            username="09121234567", phone="09121234567", is_active=False
        )
        self.request_code()
        response = self.client.post(
            "/api/accounts/auth/registration/verify/",
            {"phone": "09121234567", "code": "4839"},
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data["error_code"], "ACCOUNT_INACTIVE")

    def test_registration_resend_and_ip_rate_limits(self):
        first, _ = self.request_code()
        second, _ = self.request_code()
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 429)
        self.assertIn("Retry-After", second)

        OTPChallenge.objects.update(created_at=timezone.now() - timedelta(seconds=61))
        cache.clear()
        third, _ = self.request_code()
        self.assertEqual(third.status_code, 200)

        OTPChallenge.objects.all().delete()
        cache.clear()
        for index in range(3):
            response, _ = self.request_code(phone=f"0935000000{index}")
            self.assertEqual(response.status_code, 200)
        blocked, _ = self.request_code(phone="09350000009")
        self.assertEqual(blocked.status_code, 429)

    @patch("apps.accounts.otp.PayamitoService.send_otp")
    @patch("apps.accounts.otp.secrets.randbelow", return_value=4839)
    def test_login_otp_cannot_be_used_for_registration(self, randbelow, send_otp):
        requested = self.client.post(
            "/api/accounts/auth/otp/request/", {"phone": "09121234567"}
        )
        self.assertEqual(requested.status_code, 200)
        response = self.client.post(
            "/api/accounts/auth/registration/verify/",
            {"phone": "09121234567", "code": "4839"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error_code"], "INVALID_OTP")

    def test_database_rejects_duplicate_canonical_phone(self):
        User.objects.create_user(username="first", phone="09121234567")
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.create_user(username="second", phone="09121234567")


class FinancialPersonalityAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="personality-user", phone="09121234567", is_verified=True
        )
        self.other = User.objects.create_user(username="personality-other")
        self.client.force_authenticate(self.user)

    @staticmethod
    def answers(option="a"):
        return [
            {"question_id": question_id, "option_id": option}
            for question_id in range(1, 21)
        ]

    def test_incomplete_duplicate_and_invalid_answers_are_rejected(self):
        incomplete = self.client.post(
            "/api/accounts/personality-test/submit/",
            {"answers": self.answers()[:19]},
            format="json",
        )
        duplicate = self.answers()
        duplicate[-1]["question_id"] = 19
        duplicate_response = self.client.post(
            "/api/accounts/personality-test/submit/",
            {"answers": duplicate},
            format="json",
        )
        invalid = self.answers()
        invalid[0]["option_id"] = "x"
        invalid_response = self.client.post(
            "/api/accounts/personality-test/submit/",
            {"answers": invalid},
            format="json",
        )
        self.assertEqual(incomplete.status_code, 400)
        self.assertEqual(duplicate_response.status_code, 400)
        self.assertEqual(invalid_response.status_code, 400)
        self.assertIn("answers", incomplete.data["errors"])

    def test_submit_requires_authentication(self):
        self.client.force_authenticate(user=None)
        response = self.client.post(
            "/api/accounts/personality-test/submit/",
            {"answers": self.answers()},
            format="json",
        )
        self.assertEqual(response.status_code, 401)

    def test_submit_accepts_regular_access_token(self):
        self.client.force_authenticate(user=None)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(self.user)}")
        response = self.client.post(
            "/api/accounts/personality-test/submit/",
            {"answers": self.answers()},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.data["completed"])

    def test_get_before_completion_returns_incomplete_contract(self):
        response = self.client.get("/api/accounts/personality-test/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data,
            {"completed": False, "personality_type": None},
        )

    def test_server_calculated_fields_cannot_be_submitted(self):
        response = self.client.post(
            "/api/accounts/personality-test/submit/",
            {
                "answers": self.answers(),
                "scores": {"security": 999},
                "personality_type": "CAPITAL_GUARDIAN",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("scores", response.data["errors"])
        self.assertIn("personality_type", response.data["errors"])
        self.assertFalse(
            FinancialPersonalityAssessment.objects.filter(user=self.user).exists()
        )

    def test_database_prevents_two_current_results_for_one_user(self):
        FinancialPersonalityAssessment.objects.create(
            user=self.user,
            personality_type=FinancialPersonalityAssessment.PersonalityType.WEALTH_ARCHITECT,
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            FinancialPersonalityAssessment.objects.create(
                user=self.user,
                personality_type=FinancialPersonalityAssessment.PersonalityType.CAPITAL_GUARDIAN,
            )

    def test_submit_get_profile_history_and_user_isolation(self):
        first = self.client.post(
            "/api/accounts/personality-test/submit/",
            {"answers": self.answers("a")},
            format="json",
        )
        second = self.client.post(
            "/api/accounts/personality-test/submit/",
            {"answers": self.answers("b")},
            format="json",
        )
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertEqual(
            FinancialPersonalityAssessment.objects.filter(user=self.user).count(), 2
        )
        self.assertEqual(
            FinancialPersonalityAssessment.objects.filter(
                user=self.user, is_current=True
            ).count(),
            1,
        )
        current = self.client.get("/api/accounts/personality-test/")
        profile = self.client.get("/api/accounts/profile/details/")
        self.assertTrue(current.data["completed"])
        self.assertEqual(
            profile.data["personality_result"]["personality_type"],
            current.data["personality_type"],
        )
        self.assertTrue(
            UserActivity.objects.filter(
                user=self.user,
                activity_type=UserActivity.Type.PERSONALITY_TEST_COMPLETED,
            ).exists()
        )

        FinancialPersonalityAssessment.objects.create(
            user=self.other,
            personality_type=FinancialPersonalityAssessment.PersonalityType.CAPITAL_GUARDIAN,
            score_security=99,
        )
        own_result = self.client.get("/api/accounts/personality-test/")
        self.assertNotEqual(own_result.data["scores"]["security"], 99)

    def test_profile_status_is_available_with_blank_identity_fields(self):
        profile = self.client.get("/api/accounts/profile/")
        dashboard = self.client.get("/api/dashboard/")
        self.assertEqual(profile.status_code, 200)
        self.assertTrue(profile.data["profile_incomplete"])
        self.assertIn("first_name", profile.data["missing_profile_fields"])
        self.assertTrue(dashboard.data["data"]["user"]["profile_incomplete"])
