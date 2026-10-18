import json
import tempfile
import zipfile
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from apps.videos.models import Video

from .models import VIPChannelRetention, VIPSignalPost
from .replies import ingest_vip_post
from .retention import LIMIT, retention_candidates
from .serializers import VIPSignalPostSerializer


class VIPRetentionTests(TestCase):
    def setUp(self):
        self.crypto_lock = VIPChannelRetention.objects.get(channel="CRYPTO")
        self.forex_lock = VIPChannelRetention.objects.get(channel="FOREX")

    @override_settings(VIP_SIGNAL_RETENTION_ENABLED=True)
    def test_ingest_101_prunes_only_own_channel_and_retry_keeps_count(self):
        self.crypto_lock.activated_at = timezone.now()
        self.crypto_lock.save(update_fields=("activated_at",))
        for number in range(LIMIT):
            VIPSignalPost.objects.create(channel="CRYPTO", text=str(number), external_id=f"c:{number}")
        forex = VIPSignalPost.objects.create(channel="FOREX", text="forex")
        oldest = VIPSignalPost.objects.filter(channel="CRYPTO").order_by("pk").first().pk
        new, created = ingest_vip_post("CRYPTO", {"text": "new", "external_id": "c:100"})
        self.assertTrue(created)
        self.assertEqual(VIPSignalPost.objects.filter(channel="CRYPTO").count(), LIMIT)
        self.assertFalse(VIPSignalPost.objects.filter(pk=oldest).exists())
        self.assertTrue(VIPSignalPost.objects.filter(pk=forex.pk).exists())
        repeated, created = ingest_vip_post("CRYPTO", {"text": "different", "external_id": "c:100"})
        self.assertFalse(created)
        self.assertEqual(repeated.pk, new.pk)
        self.assertEqual(VIPSignalPost.objects.filter(channel="CRYPTO").count(), LIMIT)

    def test_parent_snapshot_is_preserved_before_prune(self):
        parent = VIPSignalPost.objects.create(channel="CRYPTO", text="parent text", external_id="parent")
        child = VIPSignalPost.objects.create(
            channel="CRYPTO", text="reply", external_id="child", parent=parent,
            reply_to_external_id="parent", reply_snapshot={},
        )
        for number in range(LIMIT - 1):
            VIPSignalPost.objects.create(channel="CRYPTO", text=str(number))
        self.assertEqual(retention_candidates("CRYPTO"), [parent.pk])
        from .retention import prune_vip_channel
        self.assertEqual(prune_vip_channel("CRYPTO"), 1)
        child.refresh_from_db()
        self.assertIsNone(child.parent_id)
        self.assertEqual(child.reply_to_external_id, "parent")
        preview = VIPSignalPostSerializer(child).data["reply_preview"]
        self.assertFalse(preview["available"])
        self.assertEqual(preview["text"], "parent text")

    def test_shared_media_is_not_deleted_after_commit(self):
        with tempfile.TemporaryDirectory() as directory, override_settings(MEDIA_ROOT=directory):
            first = VIPSignalPost.objects.create(channel="CRYPTO", text="old")
            first.image.save("shared.png", SimpleUploadedFile("shared.png", b"image", content_type="image/png"))
            shared_name = first.image.name
            second = VIPSignalPost.objects.create(channel="CRYPTO", text="other", image=shared_name)
            for number in range(LIMIT - 1):
                VIPSignalPost.objects.create(channel="CRYPTO", text=str(number))
            from .retention import prune_vip_channel
            with self.captureOnCommitCallbacks(execute=True):
                self.assertEqual(prune_vip_channel("CRYPTO"), 1)
            self.assertTrue(VIPSignalPost.objects.filter(pk=second.pk).exists())
            self.assertTrue(second.image.storage.exists(shared_name))

    def test_library_reference_keeps_pruned_media(self):
        with tempfile.TemporaryDirectory() as directory, override_settings(MEDIA_ROOT=directory):
            first = VIPSignalPost.objects.create(channel="FOREX", text="old")
            first.image.save("library.png", SimpleUploadedFile("library.png", b"image", content_type="image/png"))
            shared_name = first.image.name
            Video.objects.create(title="Shared library item", video_file=shared_name)
            for number in range(LIMIT):
                VIPSignalPost.objects.create(channel="FOREX", text=str(number))
            from .retention import prune_vip_channel
            with self.captureOnCommitCallbacks(execute=True):
                self.assertEqual(prune_vip_channel("FOREX"), 1)
            self.assertTrue(first.image.storage.exists(shared_name))

    def test_command_requires_backup_and_does_not_delete_other_models(self):
        for number in range(LIMIT + 1):
            VIPSignalPost.objects.create(channel="FOREX", text=str(number))
        self.assertEqual(VIPSignalPost.objects.filter(channel="FOREX").count(), LIMIT + 1)
        with tempfile.TemporaryDirectory() as directory:
            backup = Path(directory) / "vip-backup.zip"
            from django.core.management.base import CommandError
            with self.assertRaises(CommandError):
                call_command("prune_vip_signal_channels", apply=True, confirm=True)
            self.assertFalse(backup.exists())
            call_command("prune_vip_signal_channels", apply=True, confirm=True,
                         backup_path=str(backup))
            self.assertTrue(zipfile.is_zipfile(backup))
            with zipfile.ZipFile(backup) as archive:
                saved = json.loads(archive.read("vip-posts.json"))
                self.assertEqual(len(saved), 1)
            self.assertEqual(VIPSignalPost.objects.filter(channel="FOREX").count(), LIMIT)
            self.forex_lock.refresh_from_db()
            self.assertIsNotNone(self.forex_lock.activated_at)
