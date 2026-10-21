"""Profile phone updates should produce an HTTP response, including conflicts."""

from django.test import override_settings
from rest_framework.test import APITestCase

from .models import User


@override_settings(CRM_ENABLED=False)
class ProfilePhoneUpdateTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="email-profile-user", email="profile@example.test",
            first_name="مینا", last_name="احمدی",
        )
        self.client.force_authenticate(self.user)

    def test_phone_update_and_details_both_return_success(self):
        preflight = self.client.options(
            "/api/accounts/profile/",
            HTTP_ORIGIN="https://app.sokanex.com",
            HTTP_ACCESS_CONTROL_REQUEST_METHOD="PATCH",
            HTTP_ACCESS_CONTROL_REQUEST_HEADERS="authorization,content-type",
        )
        self.assertEqual(preflight.status_code, 200)
        self.assertEqual(preflight["Access-Control-Allow-Origin"], "https://app.sokanex.com")
        response = self.client.patch(
            "/api/accounts/profile/", {"phone": "+989121234567"}, format="json",
            HTTP_ORIGIN="https://app.sokanex.com",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Access-Control-Allow-Origin"], "https://app.sokanex.com")
        self.user.refresh_from_db()
        self.assertEqual(self.user.phone, "09121234567")
        details = self.client.patch(
            "/api/accounts/profile/details/", {"city": "تهران"}, format="json",
        )
        self.assertEqual(details.status_code, 200)

    def test_duplicate_phone_is_a_validation_response_not_network_failure(self):
        User.objects.create_user(username="other", phone="09121234567")
        response = self.client.patch(
            "/api/accounts/profile/", {"phone": "09121234567"}, format="json",
            HTTP_ORIGIN="https://app.sokanex.com",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("phone", response.data.get("errors", response.data))
        self.assertEqual(response["Access-Control-Allow-Origin"], "https://app.sokanex.com")

    def test_existing_blank_names_do_not_block_adding_a_phone(self):
        self.user.first_name = ""
        self.user.last_name = ""
        self.user.save(update_fields=("first_name", "last_name"))
        response = self.client.patch(
            "/api/accounts/profile/",
            {"first_name": "", "last_name": "", "phone": "09121234567"},
            format="json", HTTP_ORIGIN="https://app.sokanex.com",
        )
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.phone, "09121234567")
        self.assertEqual((self.user.first_name, self.user.last_name), ("", ""))

    def test_saved_name_cannot_be_cleared_by_blank_form_values(self):
        response = self.client.patch(
            "/api/accounts/profile/",
            {"first_name": "", "last_name": "", "phone": "09121234567"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("first_name", response.data.get("errors", response.data))
        self.assertIn("last_name", response.data.get("errors", response.data))
        self.user.refresh_from_db()
        self.assertIsNone(self.user.phone)
