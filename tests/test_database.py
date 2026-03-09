"""Tests for server.database — SQLite CRUD operations."""

import json
import os
import sqlite3

import pytest

from server.database import (
    init_database,
    close_database,
    get_user_agent_permissions,
    set_user_agent_permissions,
    get_user_profile,
    set_user_profile,
    get_user_config,
    set_user_config,
)


@pytest.fixture
def db(tmp_path):
    """Create a fresh database for each test."""
    db_path = str(tmp_path / "test_auth.db")
    os.environ["AUTH_DB_PATH"] = db_path
    conn = init_database()
    # Insert a test user to satisfy foreign key references
    conn.execute(
        "INSERT INTO users (email, password_hash) VALUES (?, ?)",
        ("test@example.com", "hashed_pw"),
    )
    conn.commit()
    yield conn
    close_database(conn)


class TestInitDatabase:
    """Tests for init_database and close_database."""

    def test_creates_users_table(self, tmp_path):
        os.environ["AUTH_DB_PATH"] = str(tmp_path / "init_test.db")
        conn = init_database()
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='users'"
        )
        assert cur.fetchone() is not None
        close_database(conn)

    def test_creates_user_agents_table(self, tmp_path):
        os.environ["AUTH_DB_PATH"] = str(tmp_path / "init_test.db")
        conn = init_database()
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='user_agents'"
        )
        assert cur.fetchone() is not None
        close_database(conn)

    def test_creates_user_profiles_table(self, tmp_path):
        os.environ["AUTH_DB_PATH"] = str(tmp_path / "init_test.db")
        conn = init_database()
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='user_profiles'"
        )
        assert cur.fetchone() is not None
        close_database(conn)

    def test_creates_user_configs_table(self, tmp_path):
        os.environ["AUTH_DB_PATH"] = str(tmp_path / "init_test.db")
        conn = init_database()
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='user_configs'"
        )
        assert cur.fetchone() is not None
        close_database(conn)

    def test_idempotent_init(self, tmp_path):
        """Calling init_database twice does not error."""
        os.environ["AUTH_DB_PATH"] = str(tmp_path / "init_test.db")
        conn = init_database()
        close_database(conn)
        conn2 = init_database()
        close_database(conn2)

    def test_close_database_none_safe(self):
        """close_database(None) should not raise."""
        close_database(None)


class TestUserAgentPermissions:
    """Tests for get/set_user_agent_permissions."""

    def test_empty_permissions(self, db):
        perms = get_user_agent_permissions(db, 1)
        assert perms == {}

    def test_set_and_get_permissions(self, db):
        mapping = {"CalendarAgent": True, "WeatherAgent": False}
        set_user_agent_permissions(db, 1, mapping)
        perms = get_user_agent_permissions(db, 1)
        assert perms == {"CalendarAgent": True, "WeatherAgent": False}

    def test_update_existing_permission(self, db):
        set_user_agent_permissions(db, 1, {"CalendarAgent": True})
        set_user_agent_permissions(db, 1, {"CalendarAgent": False})
        perms = get_user_agent_permissions(db, 1)
        assert perms["CalendarAgent"] is False

    def test_multiple_users_independent(self, db):
        db.execute(
            "INSERT INTO users (email, password_hash) VALUES (?, ?)",
            ("user2@example.com", "hash2"),
        )
        db.commit()
        set_user_agent_permissions(db, 1, {"CalendarAgent": True})
        set_user_agent_permissions(db, 2, {"CalendarAgent": False})
        assert get_user_agent_permissions(db, 1)["CalendarAgent"] is True
        assert get_user_agent_permissions(db, 2)["CalendarAgent"] is False


class TestUserProfile:
    """Tests for get/set_user_profile."""

    def test_empty_profile(self, db):
        profile = get_user_profile(db, 1)
        assert profile == {}

    def test_set_and_get_simple_profile(self, db):
        set_user_profile(db, 1, {"name": "Alice", "conversation_style": "formal"})
        profile = get_user_profile(db, 1)
        assert profile["name"] == "Alice"
        assert profile["conversation_style"] == "formal"

    def test_set_profile_with_list_fields(self, db):
        set_user_profile(db, 1, {"interests": ["music", "coding"]})
        profile = get_user_profile(db, 1)
        assert profile["interests"] == ["music", "coding"]

    def test_update_existing_profile(self, db):
        set_user_profile(db, 1, {"name": "Alice"})
        set_user_profile(db, 1, {"name": "Bob"})
        profile = get_user_profile(db, 1)
        assert profile["name"] == "Bob"

    def test_topics_of_interest_stored_as_json(self, db):
        set_user_profile(db, 1, {"topics_of_interest": ["AI", "ML"]})
        profile = get_user_profile(db, 1)
        assert profile["topics_of_interest"] == ["AI", "ML"]

    def test_favorite_games_stored_as_json(self, db):
        set_user_profile(db, 1, {"favorite_games": ["chess", "go"]})
        profile = get_user_profile(db, 1)
        assert profile["favorite_games"] == ["chess", "go"]

    def test_required_resources_stored_as_json(self, db):
        set_user_profile(db, 1, {"required_resources": ["calendar", "weather"]})
        profile = get_user_profile(db, 1)
        assert profile["required_resources"] == ["calendar", "weather"]

    def test_interaction_count(self, db):
        set_user_profile(db, 1, {"interaction_count": 42})
        profile = get_user_profile(db, 1)
        assert profile["interaction_count"] == 42

    def test_empty_dict_does_not_create_profile(self, db):
        """Setting an empty profile dict should not insert a row."""
        set_user_profile(db, 1, {})
        profile = get_user_profile(db, 1)
        assert profile == {}


class TestUserConfig:
    """Tests for get/set_user_config."""

    def test_empty_config(self, db):
        config = get_user_config(db, 1)
        assert config == {}

    def test_set_and_get_non_sensitive_config(self, db):
        set_user_config(db, 1, {"calendar_api_url": "http://cal.local"})
        config = get_user_config(db, 1)
        assert config["calendar_api_url"] == "http://cal.local"

    def test_set_and_get_sensitive_config_roundtrip(self, db):
        """Sensitive fields are encrypted on write and decrypted on read."""
        set_user_config(db, 1, {"openai_api_key": "sk-secret-key"})
        config = get_user_config(db, 1)
        assert config["openai_api_key"] == "sk-secret-key"

    def test_multiple_config_fields(self, db):
        set_user_config(
            db,
            1,
            {
                "openai_api_key": "sk-test",
                "hue_bridge_ip": "192.168.1.1",
                "weather_api_key": "wk-test",
            },
        )
        config = get_user_config(db, 1)
        assert config["openai_api_key"] == "sk-test"
        assert config["hue_bridge_ip"] == "192.168.1.1"
        assert config["weather_api_key"] == "wk-test"

    def test_update_existing_config(self, db):
        set_user_config(db, 1, {"hue_bridge_ip": "10.0.0.1"})
        set_user_config(db, 1, {"hue_bridge_ip": "10.0.0.2"})
        config = get_user_config(db, 1)
        assert config["hue_bridge_ip"] == "10.0.0.2"

    def test_empty_config_dict_no_op(self, db):
        """set_user_config with empty dict should be a no-op."""
        set_user_config(db, 1, {})
        config = get_user_config(db, 1)
        assert config == {}

    def test_none_sensitive_value_stored_as_empty(self, db):
        """None values for sensitive fields encrypt to empty string."""
        set_user_config(db, 1, {"openai_api_key": None, "hue_bridge_ip": "10.0.0.1"})
        config = get_user_config(db, 1)
        # decrypt of empty string returns ""
        assert config["openai_api_key"] is None or config["openai_api_key"] == ""
        assert config["hue_bridge_ip"] == "10.0.0.1"
