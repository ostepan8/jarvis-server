from __future__ import annotations

import os
import sqlite3
from typing import Optional


def init_database() -> sqlite3.Connection:
    """Initialize the authentication database."""
    db_path = os.getenv("AUTH_DB_PATH", "auth.db")
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT UNIQUE, password_hash TEXT)"
    )
    conn.commit()
    return conn


def close_database(db: Optional[sqlite3.Connection]) -> None:
    """Close the database connection."""
    if db:
        db.close()
