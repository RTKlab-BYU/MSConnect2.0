"""Encryption and lookup helpers for administrator-managed AI credentials."""

import base64
import hashlib
import logging

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings

from .models import AssistantProviderCredential

logger = logging.getLogger(__name__)


def _fernet():
    key = hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt_api_key(value: str) -> str:
    return _fernet().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_api_key(value: str) -> str:
    try:
        return _fernet().decrypt(value.encode("ascii")).decode("utf-8")
    except (InvalidToken, UnicodeError, ValueError) as exc:
        raise ValueError("Stored AI credential cannot be decrypted with the current Django secret key.") from exc


def provider_api_key(provider: str) -> str:
    stored = AssistantProviderCredential.objects.filter(provider=provider).first()
    if stored and stored.encrypted_api_key:
        try:
            return decrypt_api_key(stored.encrypted_api_key)
        except ValueError:
            logger.exception("Unable to decrypt the stored %s assistant credential", provider)
    setting_name = {
        "openai": "MSCONNECT_ASSISTANT_OPENAI_API_KEY",
        "anthropic": "MSCONNECT_ASSISTANT_ANTHROPIC_API_KEY",
    }[provider]
    return str(getattr(settings, setting_name, "") or "")


def provider_key_configured(provider: str) -> bool:
    return bool(provider_api_key(provider))
