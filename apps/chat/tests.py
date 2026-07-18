from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import User

from .models import ChatRoom, Message, RoomMembership


class ChatAPITests(APITestCase):
    def setUp(self):
        self.customer = User.objects.create_user(
            username="chat_customer",
            email="chat_customer@example.com",
            password="StrongPass123!",
            role=User.Role.USER,
        )
        self.other_customer = User.objects.create_user(
            username="chat_other",
            email="chat_other@example.com",
            password="StrongPass123!",
            role=User.Role.USER,
        )
        self.employee = User.objects.create_user(
            username="chat_employee",
            email="chat_employee@example.com",
            password="StrongPass123!",
            role=User.Role.EMPLOYEE,
        )

        self.public_room = ChatRoom.objects.create(
            name="Public Trading Room",
            description="Public room",
            is_public=True,
            is_active=True,
            created_by=self.employee,
        )
        self.private_room = ChatRoom.objects.create(
            name="Private Trading Room",
            description="Private room",
            is_public=False,
            is_active=True,
            created_by=self.employee,
        )
        self.inactive_room = ChatRoom.objects.create(
            name="Inactive Trading Room",
            is_public=True,
            is_active=False,
            created_by=self.employee,
        )

        RoomMembership.objects.create(
            room=self.private_room,
            user=self.employee,
            role=RoomMembership.Role.ADMIN,
        )

        self.list_url = reverse(
            "chat-room-list-create"
        )

    def authenticate(self, user):
        self.client.force_authenticate(user=user)

    def test_room_list_requires_authentication(self):
        response = self.client.get(self.list_url)

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_customer_sees_only_active_public_rooms(self):
        self.authenticate(self.customer)

        response = self.client.get(self.list_url)

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        names = [
            item["name"]
            for item in response.data["results"]
        ]

        self.assertIn(
            self.public_room.name,
            names,
        )
        self.assertNotIn(
            self.private_room.name,
            names,
        )
        self.assertNotIn(
            self.inactive_room.name,
            names,
        )

    def test_private_room_is_visible_to_member(self):
        RoomMembership.objects.create(
            room=self.private_room,
            user=self.customer,
            role=RoomMembership.Role.MEMBER,
        )
        self.authenticate(self.customer)

        response = self.client.get(self.list_url)

        names = [
            item["name"]
            for item in response.data["results"]
        ]

        self.assertIn(
            self.private_room.name,
            names,
        )

    def test_employee_can_create_room_and_becomes_admin(self):
        self.authenticate(self.employee)

        payload = {
            "name": "New Employee Room",
            "description": "Created by employee",
            "is_public": True,
            "is_active": True,
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

        room = ChatRoom.objects.get(
            name="New Employee Room"
        )

        membership = RoomMembership.objects.get(
            room=room,
            user=self.employee,
        )

        self.assertEqual(
            membership.role,
            RoomMembership.Role.ADMIN,
        )
        self.assertTrue(room.slug)

    def test_customer_cannot_create_room(self):
        self.authenticate(self.customer)

        response = self.client.post(
            self.list_url,
            {
                "name": "Forbidden Room",
                "is_public": True,
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_customer_can_join_public_room(self):
        self.authenticate(self.customer)

        url = reverse(
            "chat-room-join",
            kwargs={
                "slug": self.public_room.slug,
            },
        )

        response = self.client.post(url)

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )
        self.assertTrue(
            RoomMembership.objects.filter(
                room=self.public_room,
                user=self.customer,
            ).exists()
        )
        self.assertEqual(
            response.data["membership_role"],
            RoomMembership.Role.MEMBER,
        )

    def test_customer_cannot_join_private_room(self):
        self.authenticate(self.customer)

        url = reverse(
            "chat-room-join",
            kwargs={
                "slug": self.private_room.slug,
            },
        )

        response = self.client.post(url)

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertFalse(
            RoomMembership.objects.filter(
                room=self.private_room,
                user=self.customer,
            ).exists()
        )

    def test_non_member_cannot_access_room_messages(self):
        self.authenticate(self.customer)

        url = reverse(
            "chat-room-messages",
            kwargs={
                "slug": self.public_room.slug,
            },
        )

        response = self.client.get(url)

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_member_can_create_text_message(self):
        RoomMembership.objects.create(
            room=self.public_room,
            user=self.customer,
        )
        self.authenticate(self.customer)

        url = reverse(
            "chat-room-messages",
            kwargs={
                "slug": self.public_room.slug,
            },
        )

        response = self.client.post(
            url,
            {
                "text": "Hello traders",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

        message = Message.objects.get(
            text="Hello traders"
        )

        self.assertEqual(
            message.sender,
            self.customer,
        )
        self.assertEqual(
            message.room,
            self.public_room,
        )

    def test_empty_message_is_rejected(self):
        RoomMembership.objects.create(
            room=self.public_room,
            user=self.customer,
        )
        self.authenticate(self.customer)

        url = reverse(
            "chat-room-messages",
            kwargs={
                "slug": self.public_room.slug,
            },
        )

        response = self.client.post(
            url,
            {},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertIn(
            "non_field_errors",
            response.data["errors"],
        )

    def test_reply_must_belong_to_same_room(self):
        RoomMembership.objects.create(
            room=self.public_room,
            user=self.customer,
        )

        other_message = Message.objects.create(
            room=self.private_room,
            sender=self.employee,
            text="Message from another room",
        )

        self.authenticate(self.customer)

        url = reverse(
            "chat-room-messages",
            kwargs={
                "slug": self.public_room.slug,
            },
        )

        response = self.client.post(
            url,
            {
                "text": "Invalid reply",
                "reply_to": other_message.pk,
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertIn(
            "reply_to",
            response.data["errors"],
        )

    def test_member_can_leave_public_room(self):
        RoomMembership.objects.create(
            room=self.public_room,
            user=self.customer,
        )
        self.authenticate(self.customer)

        url = reverse(
            "chat-room-leave",
            kwargs={
                "slug": self.public_room.slug,
            },
        )

        response = self.client.post(url)

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )
        self.assertFalse(
            RoomMembership.objects.filter(
                room=self.public_room,
                user=self.customer,
            ).exists()
        )

    def test_room_admin_cannot_leave_room(self):
        self.authenticate(self.employee)

        url = reverse(
            "chat-room-leave",
            kwargs={
                "slug": self.private_room.slug,
            },
        )

        response = self.client.post(url)

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertIn(
            "room",
            response.data["errors"],
        )

    def test_sender_can_soft_delete_own_message(self):
        message = Message.objects.create(
            room=self.public_room,
            sender=self.customer,
            text="Delete my message",
        )
        self.authenticate(self.customer)

        url = reverse(
            "chat-message-delete",
            kwargs={
                "pk": message.pk,
            },
        )

        response = self.client.delete(url)

        self.assertEqual(
            response.status_code,
            status.HTTP_204_NO_CONTENT,
        )

        message.refresh_from_db()

        self.assertTrue(message.is_deleted)
        self.assertEqual(message.text, "")

    def test_other_customer_cannot_delete_message(self):
        message = Message.objects.create(
            room=self.public_room,
            sender=self.customer,
            text="Protected message",
        )
        self.authenticate(self.other_customer)

        url = reverse(
            "chat-message-delete",
            kwargs={
                "pk": message.pk,
            },
        )

        response = self.client.delete(url)

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

        message.refresh_from_db()

        self.assertFalse(message.is_deleted)
        self.assertEqual(
            message.text,
            "Protected message",
        )

    def test_employee_can_update_and_delete_room(self):
        self.authenticate(self.employee)

        url = reverse(
            "chat-room-detail",
            kwargs={
                "slug": self.public_room.slug,
            },
        )

        update_response = self.client.patch(
            url,
            {
                "description": "Updated description",
            },
            format="json",
        )

        self.assertEqual(
            update_response.status_code,
            status.HTTP_200_OK,
        )

        self.public_room.refresh_from_db()

        self.assertEqual(
            self.public_room.description,
            "Updated description",
        )

        delete_response = self.client.delete(url)

        self.assertEqual(
            delete_response.status_code,
            status.HTTP_204_NO_CONTENT,
        )
        self.assertFalse(
            ChatRoom.objects.filter(
                pk=self.public_room.pk,
            ).exists()
        )