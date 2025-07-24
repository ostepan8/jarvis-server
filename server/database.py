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
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS user_agents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            agent_name TEXT,
            allowed INTEGER DEFAULT 1,
            UNIQUE(user_id, agent_name),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )
    conn.commit()
    return conn


def close_database(db: Optional[sqlite3.Connection]) -> None:
    """Close the database connection."""
    if db:
        db.close()


def get_user_agent_permissions(db: sqlite3.Connection, user_id: int) -> dict[str, bool]:
    """Return mapping of agent_name -> allowed for the given user."""
    cur = db.execute(
        "SELECT agent_name, allowed FROM user_agents WHERE user_id = ?",
        (user_id,),
    )
    return {row[0]: bool(row[1]) for row in cur.fetchall()}


def set_user_agent_permissions(db: sqlite3.Connection, user_id: int, mapping: dict[str, bool]) -> None:
    """Update agent permissions for a user."""
    for name, allowed in mapping.items():
        db.execute(
            """
            INSERT INTO user_agents (user_id, agent_name, allowed)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id, agent_name) DO UPDATE SET allowed=excluded.allowed
            """,
            (user_id, name, int(allowed)),
        )
    db.commit()
