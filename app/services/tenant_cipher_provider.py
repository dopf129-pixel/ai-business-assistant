"""Shared Fernet access for tenant-scoped encrypted values.

The provider reuses the credential key already configured for the bot. It
never creates, stores, or rotates key material.
"""

from __future__ import annotations

import os

from cryptography.fernet import Fernet, InvalidToken


MASTER_KEY_ENV = "OZON_CREDENTIAL_MASTER_KEY"


def get_tenant_fernet(master_key=None):
    """Return the configured Fernet instance, or ``None`` when unavailable."""
    configured_key = master_key or os.getenv(MASTER_KEY_ENV)
    key = str(configured_key or "").strip().encode("utf-8")
    if not key:
        return None
    try:
        return Fernet(key)
    except Exception:
        return None


def encrypt_tenant_value(value, *, master_key=None):
    """Encrypt text with the existing tenant key; fail closed if unavailable."""
    fernet = get_tenant_fernet(master_key)
    if fernet is None or value is None or isinstance(value, bool):
        return None
    if not isinstance(value, (str, int)):
        return None
    try:
        text = str(value)
        if not text.strip():
            return None
        plaintext = text.encode("utf-8")
    except (TypeError, ValueError, UnicodeError):
        return None
    return fernet.encrypt(plaintext).decode("ascii")


def decrypt_tenant_value(token, *, master_key=None):
    """Decrypt a stored value; malformed tokens or keys return ``None``."""
    fernet = get_tenant_fernet(master_key)
    if fernet is None:
        return None
    try:
        return fernet.decrypt(str(token).encode("ascii")).decode("utf-8")
    except (InvalidToken, TypeError, ValueError, UnicodeError):
        return None
