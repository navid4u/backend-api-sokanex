from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


def _fernet():
    if not settings.AI_SETTINGS_ENCRYPTION_KEY:
        raise ImproperlyConfigured("AI_SETTINGS_ENCRYPTION_KEY is required to store the provider token.")
    return Fernet(settings.AI_SETTINGS_ENCRYPTION_KEY.encode())


def encrypt_token(value):
    return _fernet().encrypt(value.encode()).decode()


def decrypt_token(value):
    try:
        return _fernet().decrypt(value.encode()).decode()
    except InvalidToken as exc:
        raise ImproperlyConfigured("The stored AI provider token cannot be decrypted.") from exc


def token_configuration_status(value):
    """Return a non-sensitive health summary for the stored provider token."""
    if not value:
        return False, "token_missing"
    if not settings.AI_SETTINGS_ENCRYPTION_KEY:
        return False, "encryption_key_missing"
    try:
        decrypt_token(value)
    except (ImproperlyConfigured, ValueError, TypeError):
        return False, "token_unreadable"
    return True, "configured"
