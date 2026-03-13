#!/usr/bin/env python3
"""Decrypt an encrypted .env archive and restore files to the project."""

import argparse
import base64
import io
import json
import os
import sys
import tarfile

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes


SALT_LENGTH = 16


def derive_key(password: str, salt: bytes) -> bytes:
    """Derive a Fernet key from a password and salt using PBKDF2-HMAC-SHA256."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=600_000,
    )
    return base64.urlsafe_b64encode(kdf.derive(password.encode()))


def find_project_root() -> str:
    """Walk up from cwd to find the directory containing .git."""
    path = os.path.abspath(os.getcwd())
    while True:
        if os.path.isdir(os.path.join(path, ".git")):
            return path
        parent = os.path.dirname(path)
        if parent == path:
            print("Could not locate project root (.git directory).", file=sys.stderr)
            sys.exit(1)
        path = parent


def is_safe_path(member_name: str) -> bool:
    """Reject archive members with path traversal or absolute paths."""
    if os.path.isabs(member_name):
        return False
    normalized = os.path.normpath(member_name)
    if normalized.startswith("..") or "/.." in normalized:
        return False
    return True


def main():
    parser = argparse.ArgumentParser(description="Import .env files from an encrypted archive")
    parser.add_argument("--file", required=True, help="Path to the .enc archive")
    parser.add_argument("--password", required=True, help="Decryption password")
    parser.add_argument("--force", action="store_true",
                        help="Actually write files (default is dry-run)")
    args = parser.parse_args()

    enc_path = os.path.expanduser(args.file)
    if not os.path.isfile(enc_path):
        print(f"File not found: {enc_path}", file=sys.stderr)
        sys.exit(1)

    with open(enc_path, "rb") as f:
        data = f.read()

    if len(data) <= SALT_LENGTH:
        print("Archive too small to be valid.", file=sys.stderr)
        sys.exit(1)

    salt = data[:SALT_LENGTH]
    token = data[SALT_LENGTH:]

    key = derive_key(args.password, salt)
    fernet = Fernet(key)

    try:
        plaintext = fernet.decrypt(token)
    except InvalidToken:
        print("Decryption failed. Wrong password or corrupted archive.", file=sys.stderr)
        sys.exit(1)

    root = find_project_root()
    buf = io.BytesIO(plaintext)
    files_info = []

    with tarfile.open(fileobj=buf, mode="r:gz") as tar:
        for member in tar.getmembers():
            if not member.isfile():
                continue

            if not is_safe_path(member.name):
                print(f"Skipping unsafe path: {member.name}", file=sys.stderr)
                continue

            dest = os.path.join(root, member.name)
            exists = os.path.isfile(dest)

            files_info.append({
                "path": member.name,
                "size": member.size,
                "exists": exists,
                "action": "overwrite" if exists else "create",
            })

            if args.force:
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                extracted = tar.extractfile(member)
                if extracted is not None:
                    with open(dest, "wb") as out:
                        out.write(extracted.read())

    summary = {
        "status": "ok",
        "mode": "write" if args.force else "dry-run",
        "files": files_info,
        "file_count": len(files_info),
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
