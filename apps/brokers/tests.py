from decimal import Decimal

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import User

from .models import Broker


class BrokerAPITests(APITestCase):
    def setUp(self):
        self.customer = User.objects.create_user(
            username="broker_customer",
            email="broker_customer@example.com",
            password="StrongPass123!",
            role=User.Role.USER,
        )
        self.trader = User.objects.create_user(
            username="broker_trader",
            email="broker_trader@example.com",
            password="StrongPass123!",
            role=User.Role.TRADER,
        )
        self.employee = User.objects.create_user(
            username="broker_employee",
            email="broker_employee@example.com",
            password="StrongPass123!",
            role=User.Role.EMPLOYEE,
        )

        self.active_broker = Broker.objects.create(
            name="Active Broker",
            short_description="An active broker",
            website_url="https://active.example.com",
            country="United Kingdom",
            regulation="FCA",
            minimum_deposit=Decimal("100.00"),
            rating=Decimal("4.5"),
            features=["Demo account", "Fast execution"],
            is_active=True,
            sort_order=1,
        )
        self.inactive_broker = Broker.objects.create(
            name="Inactive Broker",
            website_url="https://inactive.example.com",
            country="Cyprus",
            rating=Decimal("3.0"),
            features=[],
            is_active=False,
            sort_order=2,
        )

        self.list_url = reverse("broker-list-create")
        self.management_url = reverse("broker-management-list")

    def authenticate(self, user):
        self.client.force_authenticate(user=user)

    def test_broker_list_requires_authentication(self):
        response = self.client.get(self.list_url)

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_customer_list_contains_only_active_brokers(self):
        self.authenticate(self.customer)

        response = self.client.get(self.list_url)

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        broker_names = [
            item["name"]
            for item in response.data["results"]
        ]

        self.assertIn(
            self.active_broker.name,
            broker_names,
        )
        self.assertNotIn(
            self.inactive_broker.name,
            broker_names,
        )

    def test_customer_can_retrieve_active_broker(self):
        self.authenticate(self.customer)

        url = reverse(
            "broker-detail",
            kwargs={
                "slug": self.active_broker.slug,
            },
        )

        response = self.client.get(url)

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            response.data["name"],
            self.active_broker.name,
        )
        self.assertIn(
            "website_url",
            response.data,
        )

    def test_customer_cannot_retrieve_inactive_broker(self):
        self.authenticate(self.customer)

        url = reverse(
            "broker-detail",
            kwargs={
                "slug": self.inactive_broker.slug,
            },
        )

        response = self.client.get(url)

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_employee_management_list_contains_inactive_brokers(self):
        self.authenticate(self.employee)

        response = self.client.get(self.management_url)

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        broker_names = [
            item["name"]
            for item in response.data["results"]
        ]

        self.assertIn(
            self.active_broker.name,
            broker_names,
        )
        self.assertIn(
            self.inactive_broker.name,
            broker_names,
        )

    def test_customer_cannot_access_management_list(self):
        self.authenticate(self.customer)

        response = self.client.get(self.management_url)

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_employee_can_create_broker(self):
        self.authenticate(self.employee)

        payload = {
            "name": "New Broker",
            "description": "Broker description",
            "website_url": "https://new-broker.example.com",
            "country": "UAE",
            "minimum_deposit": "50.00",
            "rating": "4.2",
            "features": [
                "Copy trading",
                "Mobile app",
            ],
            "is_active": True,
            "sort_order": 3,
        }

        response = self.client.post(
            self.list_url,
            payload,
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

        broker = Broker.objects.get(
            name="New Broker",
        )

        self.assertTrue(broker.slug)
        self.assertEqual(
            broker.features,
            payload["features"],
        )

    def test_customer_and_trader_cannot_create_broker(self):
        payload = {
            "name": "Forbidden Broker",
            "website_url": "https://forbidden.example.com",
            "features": [],
        }

        for user in (
            self.customer,
            self.trader,
        ):
            self.authenticate(user)

            response = self.client.post(
                self.list_url,
                payload,
                format="json",
            )

            self.assertEqual(
                response.status_code,
                status.HTTP_403_FORBIDDEN,
            )

        self.assertFalse(
            Broker.objects.filter(
                name="Forbidden Broker",
            ).exists()
        )

    def test_features_must_be_a_list_of_strings(self):
        self.authenticate(self.employee)

        payload = {
            "name": "Invalid Features Broker",
            "website_url": (
                "https://invalid-features.example.com"
            ),
            "features": [
                "Valid item",
                123,
            ],
        }

        response = self.client.post(
            self.list_url,
            payload,
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertIn(
            "features",
            response.data["errors"],

        )

    def test_rating_cannot_be_greater_than_five(self):
        self.authenticate(self.employee)

        payload = {
            "name": "Invalid Rating Broker",
            "website_url": (
                "https://invalid-rating.example.com"
            ),
            "rating": "5.1",
            "features": [],
        }

        response = self.client.post(
            self.list_url,
            payload,
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertIn(
            "rating",
            response.data["errors"],

        )

    def test_employee_can_update_broker(self):
        self.authenticate(self.employee)

        url = reverse(
            "broker-detail",
            kwargs={
                "slug": self.active_broker.slug,
            },
        )

        response = self.client.patch(
            url,
            {
                "rating": "4.9",
                "is_active": False,
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.active_broker.refresh_from_db()

        self.assertEqual(
            self.active_broker.rating,
            Decimal("4.9"),
        )
        self.assertFalse(
            self.active_broker.is_active
        )

    def test_only_employee_can_delete_broker(self):
        customer_url = reverse(
            "broker-detail",
            kwargs={
                "slug": self.active_broker.slug,
            },
        )

        self.authenticate(self.customer)

        customer_response = self.client.delete(
            customer_url
        )

        self.assertEqual(
            customer_response.status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertTrue(
            Broker.objects.filter(
                pk=self.active_broker.pk,
            ).exists()
        )

        employee_url = reverse(
            "broker-detail",
            kwargs={
                "slug": self.inactive_broker.slug,
            },
        )

        self.authenticate(self.employee)

        employee_response = self.client.delete(
            employee_url
        )

        self.assertEqual(
            employee_response.status_code,
            status.HTTP_204_NO_CONTENT,
        )
        self.assertFalse(
            Broker.objects.filter(
                pk=self.inactive_broker.pk,
            ).exists()
        )