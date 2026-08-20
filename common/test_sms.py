import json
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings

from .sms import PayamitoPatternService, SMSProviderError


@override_settings(
    PAYAMITO_ENABLED=True, PAYAMITO_USERNAME="user", PAYAMITO_API_KEY="key",
    PAYAMITO_TIMEOUT_SECONDS=6,
)
class PayamitoPatternServiceTests(SimpleTestCase):
    @patch("common.sms.urlopen")
    def test_uses_service_pattern_contract_without_sender_number(self, urlopen):
        response = MagicMock()
        response.read.return_value = json.dumps({
            "Value": "1234567890123456", "RetStatus": 1, "StrRetStatus": "Ok"
        }).encode()
        urlopen.return_value.__enter__.return_value = response
        result = PayamitoPatternService.send("09121234567", 123, ["4839"])
        request = urlopen.call_args.args[0]
        payload = json.loads(request.data.decode())
        self.assertEqual(request.full_url, PayamitoPatternService.endpoint)
        self.assertEqual(payload, {
            "username": "user", "password": "key", "text": "4839",
            "to": "09121234567", "bodyId": 123,
        })
        self.assertNotIn("from", payload)
        self.assertEqual(result["message_id"], "1234567890123456")

    def test_rejects_link_in_pattern_variable(self):
        with self.assertRaises(SMSProviderError) as context:
            PayamitoPatternService.send("09121234567", 123, ["https://example.com"])
        self.assertEqual(context.exception.provider_code, "-10")
