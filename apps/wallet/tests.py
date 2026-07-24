from decimal import Decimal

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import User

from .models import Transaction, Wallet


class WalletAPITests(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username="wallet_customer",
            email="wallet_customer@example.com",
            password="StrongPass123!",
            role=User.Role.USER,
        )

        self.other_user = User.objects.create_user(
            username="wallet_other",
            email="wallet_other@example.com",
            password="StrongPass123!",
            role=User.Role.USER,
        )

        self.wallet, _ = Wallet.objects.get_or_create(
            user=self.user,
        )

        self.other_wallet, _ = (
            Wallet.objects.get_or_create(
                user=self.other_user,
            )
        )

        self.credit_transaction = (
            Transaction.objects.create(
                wallet=self.wallet,
                transaction_type=(
                    Transaction.Type.CREDIT
                ),
                status=(
                    Transaction.Status.COMPLETED
                ),
                amount=Decimal("250.00000000"),
                balance_after=Decimal(
                    "250.00000000"
                ),
                description="Account deposit",
            )
        )

        self.debit_transaction = (
            Transaction.objects.create(
                wallet=self.wallet,
                transaction_type=(
                    Transaction.Type.DEBIT
                ),
                status=Transaction.Status.PENDING,
                amount=Decimal("50.00000000"),
                balance_after=Decimal(
                    "200.00000000"
                ),
                description="Signal purchase",
            )
        )

        Transaction.objects.create(
            wallet=self.other_wallet,
            transaction_type=Transaction.Type.CREDIT,
            status=Transaction.Status.COMPLETED,
            amount=Decimal("999.00000000"),
            balance_after=Decimal(
                "999.00000000"
            ),
            description="Other user transaction",
        )

        self.transaction_list_url = reverse(
            "transaction-list"
        )

    def authenticate(self):
        self.client.force_authenticate(
            user=self.user
        )

    def test_transaction_list_requires_authentication(
        self
    ):
        response = self.client.get(
            self.transaction_list_url
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_user_sees_only_own_transactions(
        self
    ):
        self.authenticate()

        response = self.client.get(
            self.transaction_list_url
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assertEqual(
            response.data["count"],
            2,
        )

    def test_user_can_search_transactions(
        self
    ):
        self.authenticate()

        response = self.client.get(
            self.transaction_list_url,
            {
                "search": "deposit",
            },
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assertEqual(
            response.data["count"],
            1,
        )

        self.assertEqual(
            response.data["results"][0][
                "description"
            ],
            "Account deposit",
        )

    def test_user_can_filter_transaction_status(
        self
    ):
        self.authenticate()

        response = self.client.get(
            self.transaction_list_url,
            {
                "status": (
                    Transaction.Status.COMPLETED
                ),
            },
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assertEqual(
            response.data["count"],
            1,
        )

        self.assertEqual(
            response.data["results"][0][
                "status"
            ],
            Transaction.Status.COMPLETED,
        )

    def test_user_can_filter_transaction_type(
        self
    ):
        self.authenticate()

        response = self.client.get(
            self.transaction_list_url,
            {
                "transaction_type": (
                    Transaction.Type.DEBIT
                ),
            },
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assertEqual(
            response.data["count"],
            1,
        )

        self.assertEqual(
            response.data["results"][0][
                "transaction_type"
            ],
            Transaction.Type.DEBIT,
        )

    def test_user_can_filter_transaction_amount(
        self
    ):
        self.authenticate()

        response = self.client.get(
            self.transaction_list_url,
            {
                "min_amount": "100",
                "max_amount": "300",
            },
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assertEqual(
            response.data["count"],
            1,
        )

        self.assertEqual(
            response.data["results"][0]["id"],
            self.credit_transaction.id,
        )

    def test_user_can_order_transactions_by_amount(
        self
    ):
        self.authenticate()

        response = self.client.get(
            self.transaction_list_url,
            {
                "ordering": "amount",
            },
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        returned_ids = [
            item["id"]
            for item in response.data["results"]
        ]

        self.assertEqual(
            returned_ids,
            [
                self.debit_transaction.id,
                self.credit_transaction.id,
            ],
        )