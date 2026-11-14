import tempfile
from io import BytesIO
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from PIL import Image
from rest_framework.test import APITestCase

from apps.accounts.models import User

from .models import ChatRoom, Message, RoomMembership


@override_settings(SOCIAL_PRIVATE_MEDIA_ROOT=tempfile.mkdtemp(), MEDIA_ROOT=tempfile.mkdtemp())
class PrivateRoomMediaTests(APITestCase):
    def setUp(self):
        self.member = User.objects.create_user(username="room-media-member")
        self.other = User.objects.create_user(username="room-media-other")
        self.manager = User.objects.create_user(username="room-media-manager", role=User.Role.SUPER_ADMIN)
        self.room = ChatRoom.objects.create(name="Media room", is_public=False, created_by=self.manager)
        RoomMembership.objects.create(room=self.room, user=self.member)

    def test_private_room_image_requires_membership_and_uses_private_storage(self):
        buffer = BytesIO()
        Image.new("RGB", (1, 1), "red").save(buffer, format="PNG")
        self.room.image.save("cover.png", SimpleUploadedFile("cover.png", buffer.getvalue(), content_type="image/png"))
        self.assertTrue(self.room.image.storage.exists(self.room.image.name))
        self.client.force_authenticate(self.member)
        detail = self.client.get(f"/api/chat/{self.room.slug}/")
        self.assertEqual(detail.status_code, 200)
        url = detail.data["image"]
        self.assertIn(f"/api/chat/rooms/{self.room.pk}/image/", url)
        self.assertNotIn("/media/chat/", url)
        allowed = self.client.get(url)
        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(b"".join(allowed.streaming_content), buffer.getvalue())
        self.assertEqual(allowed["Cache-Control"], "private, no-store")
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(url).status_code, 401)
        self.client.force_authenticate(self.manager)
        self.assertEqual(self.client.get(url).status_code, 200)
        self.room.is_active = False
        self.room.save(update_fields=["is_active"])
        self.client.force_authenticate(self.member)
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_private_attachment_requires_active_membership(self):
        self.client.force_authenticate(self.member)
        uploaded = SimpleUploadedFile("note.txt", b"private room text", content_type="text/plain")
        created = self.client.post(f"/api/chat/{self.room.slug}/messages/", {"attachment": uploaded}, format="multipart")
        self.assertEqual(created.status_code, 201, created.data)
        message = Message.objects.get(pk=created.data["id"])
        self.assertTrue(message.attachment.storage.exists(message.attachment.name))
        url = created.data["attachment"]
        self.assertIn(f"/api/chat/messages/{message.pk}/attachment/", url)
        self.assertNotIn("/media/chat/", url)
        allowed = self.client.get(url, HTTP_RANGE="bytes=0-6")
        self.assertEqual(allowed.status_code, 206)
        self.assertEqual(b"".join(allowed.streaming_content), b"private")
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.client.force_authenticate(self.member)
        RoomMembership.objects.filter(room=self.room, user=self.member).delete()
        self.assertEqual(self.client.get(url).status_code, 404)
        RoomMembership.objects.create(room=self.room, user=self.member)
        message.is_deleted = True
        message.save(update_fields=["is_deleted"])
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_community_feature_is_boolean_in_both_flag_states(self):
        self.client.force_authenticate(self.member)
        with patch.dict("os.environ", {"SOCIAL_COMMUNITY_V3_ENABLED": "False"}):
            self.assertIs(self.client.get("/api/chat/social/community/").data["features"]["community_v3"], False)
        with patch.dict("os.environ", {"SOCIAL_COMMUNITY_V3_ENABLED": "True"}):
            self.assertIs(self.client.get("/api/chat/social/community/").data["features"]["community_v3"], True)

    def test_social_video_over_20_mib_is_rejected(self):
        self.client.force_authenticate(self.member)
        oversized = SimpleUploadedFile("big.mp4", b"\x00\x00\x00\x18ftyp" + b"0" * (20 * 1024 * 1024), content_type="video/mp4")
        response = self.client.post("/api/chat/social/feed/", {"market": "general", "video": oversized}, format="multipart")
        self.assertEqual(response.status_code, 400)
        self.assertIn("video", response.data["errors"])
