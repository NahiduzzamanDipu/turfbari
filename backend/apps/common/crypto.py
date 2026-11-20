"""Encrypt small secrets (e.g. an API key the admin saves in the UI) at rest with Fernet.

The key is derived from DJANGO_SECRET_KEY, so rotating that secret makes old values unreadable — the
admin then simply saves the credential again (decrypt() returns None instead of failing).
"""

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


def _fernet() -> Fernet:
    digest = hashlib.sha256(f"turfbari-credentials:{settings.SECRET_KEY}".encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode() if value else ""


def decrypt(token: str) -> str | None:
    if not token:
        return None
    try:
        return _fernet().decrypt(token.encode()).decode()
    except (InvalidToken, ValueError):
        return None


def mask(value: str | None) -> str:
    if not value:
        return ""
    return f"{value[:3]}{'•' * 6}{value[-3:]}" if len(value) > 8 else "•" * len(value)
