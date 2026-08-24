from unittest.mock import patch

from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.academy.models import Course, CourseEnrollment, CoursePurchase
from .models import LedgerEntry, Payment, PaymentProvider
from .services import WalletService


@override_settings(ZARINPAL_MERCHANT_ID="merchant", PAYMENT_CALLBACK_BASE_URL="https://api.test")
class BillingV2Tests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="billing-user", password="pass")
        self.instructor = User.objects.create_user(username="teacher", password="pass")
        self.provider = PaymentProvider.objects.get(code="ZARINPAL")
        self.provider.is_active = True
        self.provider.save(update_fields=["is_active"])
        self.client.force_authenticate(self.user)

    @patch("apps.wallet.providers.ZarinpalAdapter.create")
    def test_payment_creation_is_idempotent(self, create):
        create.return_value = ("authority-1", "https://gateway.test/pay")
        payload = {"provider": "ZARINPAL", "amount_irt": 100000, "purpose": "WALLET_DEPOSIT", "idempotency_key": "deposit-1"}
        first = self.client.post("/api/billing/payments/", payload, format="json")
        second = self.client.post("/api/billing/payments/", payload, format="json")
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(Payment.objects.count(), 1)
        create.assert_called_once()

    @patch("apps.wallet.providers.ZarinpalAdapter.verify")
    def test_verify_is_idempotent_and_ledger_balances(self, verify):
        payment = Payment.objects.create(
            user=self.user, provider=self.provider, authority="auth", amount_irt=250000,
            purpose=Payment.Purpose.WALLET_DEPOSIT, status=Payment.Status.PENDING,
            idempotency_key="verify-1",
        )
        verify.return_value = "ref-1"
        payload = {"payment_id": str(payment.id), "authority": "auth", "status": "OK"}
        self.assertEqual(self.client.post("/api/billing/payments/verify/", payload, format="json").status_code, 200)
        self.assertEqual(self.client.post("/api/billing/payments/verify/", payload, format="json").status_code, 200)
        wallet = WalletService.get_wallet(self.user)
        self.assertEqual(WalletService.balance_irt(wallet), 250000)
        entries = LedgerEntry.objects.filter(transaction=payment.ledger_transaction)
        self.assertEqual(sum(e.amount_irt for e in entries if e.direction == "DEBIT"), sum(e.amount_irt for e in entries if e.direction == "CREDIT"))
        verify.assert_called_once()

    def test_wallet_course_purchase_is_atomic_and_cannot_repeat(self):
        wallet = WalletService.get_wallet(self.user)
        WalletService.post(wallet, 500000, "TEST_CREDIT")
        course = Course.objects.create(
            title="Paid", instructor=self.instructor, status=Course.Status.PUBLISHED,
            is_free=False, price=200000, purchase_required=True,
        )
        url = f"/api/academy/courses/{course.slug}/purchase/"
        first = self.client.post(url, {"payment_method": "WALLET"}, format="json")
        second = self.client.post(url, {"payment_method": "WALLET"}, format="json")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 400)
        self.assertEqual(WalletService.balance_irt(wallet), 300000)
        self.assertTrue(CoursePurchase.objects.filter(user=self.user, course=course).exists())
        self.assertTrue(CourseEnrollment.objects.filter(user=self.user, course=course).exists())

