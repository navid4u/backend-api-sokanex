import base64
import os
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Create one persistent VAPID key pair for Web Push."

    def add_arguments(self, parser):
        parser.add_argument("--force", action="store_true", help="Replace the existing private key (invalidates subscriptions).")

    def handle(self, *args, **options):
        path_value = settings.WEBPUSH_VAPID_PRIVATE_KEY_PATH
        if not path_value:
            raise CommandError("Set WEBPUSH_VAPID_PRIVATE_KEY_PATH before generating a key.")
        path = Path(path_value)
        if path.exists() and not options["force"]:
            raise CommandError("VAPID private key already exists; refusing to rotate it. Use --force only for an intentional key rotation.")
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        try:
            os.chmod(path.parent, 0o700)
        except OSError:
            pass
        private_key = ec.generate_private_key(ec.SECP256R1())
        private_bytes = private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
        path.write_bytes(private_bytes)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
        public_bytes = private_key.public_key().public_bytes(
            serialization.Encoding.X962,
            serialization.PublicFormat.UncompressedPoint,
        )
        public_key = base64.urlsafe_b64encode(public_bytes).decode("ascii").rstrip("=")
        self.stdout.write(self.style.SUCCESS("VAPID key pair created. The private key was saved with restrictive permissions and was not printed."))
        self.stdout.write(f"WEBPUSH_VAPID_PRIVATE_KEY_PATH={path}")
        self.stdout.write(f"WEBPUSH_VAPID_PUBLIC_KEY={public_key}")
