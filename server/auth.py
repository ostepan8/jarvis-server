from __future__ import annotations

import os
from datetime import datetime, timedelta, UTC
from typing import Optional

from passlib.context import CryptContext

# Fix for JWT import - ensure we're using PyJWT
try:
    import jwt

    # Test if jwt.encode exists
    test_payload = {"test": "test"}
    jwt.encode(test_payload, "secret", algorithm="HS256")
except (ImportError, AttributeError):
    try:
        # Try alternative import
        import PyJWT as jwt
    except ImportError:
        import sys
        sys.stderr.write("Please install PyJWT: pip install PyJWT\n")
        raise ImportError("PyJWT is required for authentication")


# Use pbkdf2_sha256 instead of bcrypt to avoid version issues
# This is still cryptographically secure and more reliable
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

JWT_SECRET = os.getenv("JWT_SECRET")
if not JWT_SECRET:
    raise RuntimeError("JWT_SECRET environment variable must be set")
JWT_ALGORITHM = "HS256"
TOKEN_EXPIRE_MINUTES = int(os.getenv("TOKEN_EXPIRE_MINUTES", 60))


def create_token(email: str) -> str:
    """Create a JWT token for the given email."""
    # Fix: Use timezone-aware datetime
    expire = datetime.now(UTC) + timedelta(minutes=TOKEN_EXPIRE_MINUTES)
    payload = {"sub": email, "exp": expire}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> Optional[str]:
    """Decode a JWT token and return the email if valid."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload.get("sub")
    except jwt.PyJWTError:
        return None


def hash_password(password: str) -> str:
    """Hash a password using pbkdf2_sha256."""
    return pwd_context.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return pwd_context.verify(password, hashed_password)
