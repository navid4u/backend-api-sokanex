import json
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings

from .sms import PayamitoSMSService, SMSProviderError, render_sms_template


@override_settings(
    PAYAMITO_ENABLED=True, PAYAMITO_USERNAME="user", PAYAMITO_API_KEY="key",
    PAYAMITO_FROM_NUMBER="9981803296", PAYAMITO_TIMEOUT_SECONDS=6,
)
class PayamitoSMSServiceTests(SimpleTestCase):
    @patch("common.sms.urlopen")
    def test_uses_text_message_contract_with_service_sender_number(self, urlopen):
        response = MagicMock()
        response.read.return_value = json.dumps({
            "Value": "1234567890123456", "RetStatus": 1, "StrRetStatus": "Ok"
        }).encode()
        urlopen.return_value.__enter__.return_value = response
        result = PayamitoSMSService.send("09121234567", "کد ورود: 4839")
        request = urlopen.call_args.args[0]
        payload = json.loads(request.data.decode())
        self.assertEqual(request.full_url, PayamitoSMSService.endpoint)
        self.assertEqual(payload, {
            "username": "user", "password": "key", "text": "کد ورود: 4839",
            "to": "09121234567", "from": "9981803296", "isFlash": False,
        })
        self.assertNotIn("bodyId", payload)
        self.assertEqual(result["message_id"], "1234567890123456")

    @override_settings(PAYAMITO_FROM_NUMBER="")
    def test_requires_sender_number(self):
        with self.assertRaises(SMSProviderError) as context:
            PayamitoSMSService.send("09121234567", "test")
        self.assertEqual(context.exception.provider_code, "missing_sender")

    def test_rejects_invalid_message_template(self):
        with self.assertRaises(SMSProviderError) as context:
            render_sms_template("Code: {wrong_name}", code="4839")
        self.assertEqual(context.exception.provider_code, "invalid_template")

    @patch("common.sms.urlopen")
    def test_insufficient_credit_is_classified_without_exposing_credentials(self, urlopen):
        response = MagicMock()
        response.read.return_value = json.dumps({
            "Value": "0", "RetStatus": 0, "StrRetStatus": "اعتبار کافی نیست"
        }).encode("utf-8")
        urlopen.return_value.__enter__.return_value = response

        with self.assertLogs("django.request", level="WARNING") as logs:
            with self.assertRaises(SMSProviderError) as context:
                PayamitoSMSService.send("09121234567", "test")

        self.assertEqual(
            context.exception.provider_code, "SMS_PROVIDER_INSUFFICIENT_CREDIT"
        )
        output = " ".join(logs.output)
        self.assertIn("SMS_PROVIDER_INSUFFICIENT_CREDIT", output)
        self.assertNotIn("key", output)

    @override_settings(PAYAMITO_TIMEOUT_SECONDS=30)
    @patch("common.sms.urlopen")
    def test_timeout_is_capped_at_ten_seconds(self, urlopen):
        response = MagicMock()
        response.read.return_value = json.dumps({
            "Value": "1", "RetStatus": 1, "StrRetStatus": "Ok"
        }).encode()
        urlopen.return_value.__enter__.return_value = response
        PayamitoSMSService.send("09121234567", "test")
        self.assertEqual(urlopen.call_args.kwargs["timeout"], 10)
