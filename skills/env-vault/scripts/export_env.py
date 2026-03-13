#!/usr/bin/env python3
"""Discover .env files in the project, compress and encrypt them into a single archive."""

import argparse
import base64
import io
import json
import os
import sys
import tarfile
from datetime import date

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes


PRUNE_DIRS = {".git", ".claude", "__pycache__", "node_modules", ".venv", "venv", ".tox", ".mypy_cache", ".pytest_cache"}


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


def discover_env_files(root: str) -> list[str]:
    """Return relative paths of all .env files under root, pruning irrelevant dirs."""
    env_files = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in PRUNE_DIRS]
        for fname in filenames:
            if fname == ".env" or (fname.startswith(".env.") and not fname.endswith(".example")):
                rel = os.path.relpath(os.path.join(dirpath, fname), root)
                env_files.append(rel)
    env_files.sort()
    return env_files


def main():
    parser = argparse.ArgumentParser(description="Export .env files as an encrypted archive")
    parser.add_argument("--password", required=True, help="Encryption password")
    parser.add_argument("--output", type=str, default=None,
                        help="Output path (default: ~/Downloads/jarvis-env-YYYY-MM-DD.enc)")
    args = parser.parse_args()

    root = find_project_root()
    env_files = discover_env_files(root)

    if not env_files:
        print("No .env files found.", file=sys.stderr)
        sys.exit(1)

    # Build tar.gz in memory
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for rel_path in env_files:
            full_path = os.path.join(root, rel_path)
            tar.add(full_path, arcname=rel_path)
    plaintext = buf.getvalue()

    # Encrypt
    salt = os.urandom(16)
    key = derive_key(args.password, salt)
    fernet = Fernet(key)
    token = fernet.encrypt(plaintext)

    # Write output
    if args.output:
        out_path = os.path.expanduser(args.output)
    else:
        downloads = os.path.expanduser("~/Downloads")
        os.makedirs(downloads, exist_ok=True)
        out_path = os.path.join(downloads, f"jarvis-env-{date.today().isoformat()}.enc")

    with open(out_path, "wb") as f:
        f.write(salt + token)

    summary = {
        "status": "ok",
        "output": out_path,
        "files": env_files,
        "file_count": len(env_files),
        "archive_bytes": len(salt + token),
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
