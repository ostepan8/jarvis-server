from __future__ import annotations

import os
from cryptography.fernet import Fernet, InvalidToken


_SECRET = os.getenv("CONFIG_SECRET")
if not _SECRET:
    # Generate a key if not provided to avoid crashes in dev/test
    _SECRET = Fernet.generate_key().decode()
    os.environ["CONFIG_SECRET"] = _SECRET

fernet = Fernet(_SECRET)


def encrypt(value: str | None) -> str:
    """Encrypt a string value."""
    if value is None:
        return ""
    return fernet.encrypt(value.encode()).decode()


def decrypt(value: str | None) -> str:
    """Decrypt a previously encrypted string."""
    if not value:
        return ""
    try:
        return fernet.decrypt(value.encode()).decode()
    except InvalidToken:
        return ""
