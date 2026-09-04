from django.core.files.uploadedfile import SimpleUploadedFile
from io import BytesIO
from PIL import Image
from rest_framework.test import APITestCase

from apps.accounts.models import User


class SignalCreateContractTests(APITestCase):
    def setUp(self):
        self.trader = User.objects.create_user(username="contract-trader", role=User.Role.TRADER)
        self.client.force_authenticate(self.trader)
        self.payload = {
            "symbol": "eurusd", "market": "forex", "direction": "buy",
            "entry_price": "1.10", "stop_loss": "1.00", "take_profit": "1.20",
        }

    def test_minimal_json_builds_title_and_returns_complete_object(self):
        response = self.client.post("/api/signals/", self.payload, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["title"], "EURUSD - خرید")
        self.assertEqual(response.data["status"], "pending")
        self.assertEqual(response.data["trader"], self.trader.username)
        self.assertIn("created_at", response.data)
        mine = self.client.get("/api/signals/my-signals/")
        self.assertEqual(mine.data["results"][0]["id"], response.data["id"])

    def test_multipart_with_optional_image(self):
        content = BytesIO()
        Image.new("RGB", (2, 2), "red").save(content, format="PNG")
        image = SimpleUploadedFile(
            "signal.png",
            content.getvalue(),
            content_type="image/png",
        )
        payload = {**self.payload, "image": image}
        response = self.client.post("/api/signals/", payload, format="multipart")
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.data["image"])

    def test_price_validation_is_farsi_400(self):
        response = self.client.post(
            "/api/signals/", {**self.payload, "stop_loss": "1.15"}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("برای سیگنال خرید", str(response.data["errors"]["prices"]))
