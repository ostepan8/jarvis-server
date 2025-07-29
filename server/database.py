from __future__ import annotations

import os
import sqlite3
import json
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
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS user_profiles (
            user_id INTEGER PRIMARY KEY,
            name TEXT,
            preferred_personality TEXT,
            interests TEXT,
            conversation_style TEXT,
            humor_preference TEXT,
            topics_of_interest TEXT,
            language_preference TEXT,
            interaction_count INTEGER DEFAULT 0,
            favorite_games TEXT,
            last_seen TEXT,
            required_resources TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS user_configs (
            user_id INTEGER PRIMARY KEY,
            openai_api_key TEXT,
            anthropic_api_key TEXT,
            calendar_api_url TEXT,
            weather_api_key TEXT,
            hue_bridge_ip TEXT,
            hue_username TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
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


def get_user_profile(db: sqlite3.Connection, user_id: int) -> dict:
    """Return the stored profile for a user as a dict."""
    fields = [
        "name",
        "preferred_personality",
        "interests",
        "conversation_style",
        "humor_preference",
        "topics_of_interest",
        "language_preference",
        "interaction_count",
        "favorite_games",
        "last_seen",
        "required_resources",
    ]
    cur = db.execute(
        f"SELECT {', '.join(fields)} FROM user_profiles WHERE user_id = ?",
        (user_id,),
    )
    row = cur.fetchone()
    if not row:
        return {}

    profile = {}
    list_fields = {
        "interests",
        "topics_of_interest",
        "favorite_games",
        "required_resources",
    }
    for field, value in zip(fields, row):
        if field in list_fields and value:
            try:
                profile[field] = json.loads(value)
            except Exception:
                profile[field] = []
        else:
            profile[field] = value

    return profile


def set_user_profile(db: sqlite3.Connection, user_id: int, profile: dict) -> None:
    """Insert or update a user's profile."""
    existing = get_user_profile(db, user_id)
    list_fields = {
        "interests",
        "topics_of_interest",
        "favorite_games",
        "required_resources",
    }

    if not existing:
        fields = []
        values = []
        placeholders = []
        for field, value in profile.items():
            fields.append(field)
            if field in list_fields and value is not None:
                value = json.dumps(value)
            values.append(value)
            placeholders.append("?")

        if fields:
            db.execute(
                f"INSERT INTO user_profiles (user_id, {', '.join(fields)}) VALUES (?, {', '.join(placeholders)})",
                [user_id] + values,
            )
    else:
        updates = []
        values = []
        for field, value in profile.items():
            if field in list_fields and value is not None:
                value = json.dumps(value)
            updates.append(f"{field}=?")
            values.append(value)

        if updates:
            values.append(user_id)
            db.execute(
                f"UPDATE user_profiles SET {', '.join(updates)} WHERE user_id=?",
                values,
            )

    db.commit()


def get_user_config(db: sqlite3.Connection, user_id: int) -> dict:
    """Return decrypted config values for a user."""
    fields = [
        "openai_api_key",
        "anthropic_api_key",
        "calendar_api_url",
        "weather_api_key",
        "hue_bridge_ip",
        "hue_username",
    ]
    cur = db.execute(
        f"SELECT {', '.join(fields)} FROM user_configs WHERE user_id=?",
        (user_id,),
    )
    row = cur.fetchone()
    if not row:
        return {}
    from .crypto import decrypt

    sensitive = {
        "openai_api_key",
        "anthropic_api_key",
        "weather_api_key",
        "hue_username",
    }
    result = {}
    for field, value in zip(fields, row):
        if value is None:
            result[field] = None
        elif field in sensitive:
            result[field] = decrypt(value)
        else:
            result[field] = value
    return result


def set_user_config(db: sqlite3.Connection, user_id: int, config: dict) -> None:
    """Insert or update user configuration, encrypting sensitive fields."""
    if not config:
        return

    from .crypto import encrypt

    sensitive = {
        "openai_api_key",
        "anthropic_api_key",
        "weather_api_key",
        "hue_username",
    }

    fields = []
    values = []
    for field, value in config.items():
        if field in sensitive and value is not None:
            value = encrypt(value)
        fields.append(field)
        values.append(value)
    placeholders = ", ".join("?" for _ in fields)
    updates = ", ".join(f"{f}=excluded.{f}" for f in fields)
    db.execute(
        f"INSERT INTO user_configs (user_id, {', '.join(fields)}) "
        f"VALUES (?, {placeholders}) "
        f"ON CONFLICT(user_id) DO UPDATE SET {updates}",
        [user_id] + values,
    )
    db.commit()
