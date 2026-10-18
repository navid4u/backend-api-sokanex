"""Preview, back up, and explicitly activate 100-row VIP channel retention."""

import json
import os
import shutil
import zipfile
from pathlib import Path

from django.core import serializers
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.signals.models import VIPChannelRetention, VIPSignalPost
from apps.signals.retention import prune_vip_channel, retention_candidates


class Command(BaseCommand):
    help = "Dry-run VIP channel retention, or back up and explicitly apply it."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--confirm", action="store_true")
        parser.add_argument("--backup-path", type=str)

    def handle(self, *args, **options):
        channels = (VIPSignalPost.Channel.CRYPTO, VIPSignalPost.Channel.FOREX)
        if not options["apply"]:
            self.stdout.write(json.dumps({channel: {
                "total": VIPSignalPost.objects.filter(channel=channel).count(),
                "prune_ids": retention_candidates(channel),
            } for channel in channels}, sort_keys=True))
            return
        if not options["confirm"] or not options["backup_path"]:
            raise CommandError("--apply requires --confirm and an absolute --backup-path.")
        backup = Path(options["backup_path"])
        if not backup.is_absolute() or backup.suffix != ".zip" or not backup.parent.is_dir():
            raise CommandError("Backup must be an absolute .zip path in an existing directory.")
        if backup.exists():
            raise CommandError("Backup path already exists; refusing to overwrite it.")
        # Reserve the backup name first; even an empty initial prune has a record.
        try:
            fd = os.open(backup, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(fd)
        except OSError as exc:
            raise CommandError("Could not create the backup archive.") from exc
        try:
            with transaction.atomic():
                locks = list(VIPChannelRetention.objects.select_for_update().order_by("channel"))
                if {row.channel for row in locks} != set(channels):
                    raise CommandError("Channel lock rows are missing; apply migrations first.")
                victims = {channel: list(VIPSignalPost.objects.filter(
                    channel=channel, pk__in=retention_candidates(channel),
                )) for channel in channels}
                all_posts = [post for posts in victims.values() for post in posts]
                with zipfile.ZipFile(backup, mode="w", compression=zipfile.ZIP_DEFLATED,
                                     allowZip64=True) as archive:
                    archive.writestr("vip-posts.json", serializers.serialize("json", all_posts))
                    manifest = {channel: [post.pk for post in victims[channel]] for channel in channels}
                    archive.writestr("manifest.json", json.dumps(manifest))
                    names = set()
                    for post in all_posts:
                        for field in (post.image, post.video, post.audio):
                            name = field.name if field else ""
                            if not name or name in names:
                                continue
                            prefix = f"signals/vip/{post.channel.lower()}/"
                            if not name.startswith(prefix) or ".." in name.split("/"):
                                raise CommandError("Unexpected media path in VIP post; aborting.")
                            names.add(name)
                            with field.storage.open(name, "rb") as source:
                                with archive.open(f"media/{name}", "w", force_zip64=True) as target:
                                    shutil.copyfileobj(source, target, length=1024 * 1024)
                if not zipfile.is_zipfile(backup):
                    raise CommandError("Backup verification failed; no rows removed.")
                deleted = {channel: prune_vip_channel(channel) for channel in channels}
                now = timezone.now()
                for lock in locks:
                    if lock.activated_at is None:
                        lock.activated_at = now
                        lock.save(update_fields=("activated_at",))
            self.stdout.write(json.dumps({"deleted": deleted, "backup": str(backup)}, sort_keys=True))
        except Exception:
            # Keep the archive as forensic evidence. The transaction is rolled back.
            self.stderr.write("VIP prune failed; database transaction rolled back. Inspect backup archive.")
            raise
