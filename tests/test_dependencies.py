"""Tests for server.dependencies — FastAPI dependency injection helpers."""

import os
import sqlite3
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from server.dependencies import (
    get_jarvis,
    get_auth_db,
    get_fact_service,
    get_current_user,
    get_user_allowed_agents,
    get_user_jarvis,
)
from server.auth import create_token


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_request(state_attrs: dict | None = None, headers: dict | None = None):
    """Build a minimal fake Request object with the given app.state and headers."""
    state = SimpleNamespace(**(state_attrs or {}))
    app = SimpleNamespace(state=state)
    _headers = headers or {}
    return SimpleNamespace(app=app, headers=_headers)


def _test_db(tmp_path):
    """Create a fresh auth database with a single user and all tables."""
    db_path = str(tmp_path / "dep_test.db")
    os.environ["AUTH_DB_PATH"] = db_path
    from server.database import init_database

    conn = init_database()
    conn.execute(
        "INSERT INTO users (email, password_hash) VALUES (?, ?)",
        ("dep@test.com", "hash"),
    )
    conn.commit()
    return conn


# ---------------------------------------------------------------------------
# get_jarvis
# ---------------------------------------------------------------------------

class TestGetJarvis:
    """Tests for the get_jarvis dependency."""

    @pytest.mark.asyncio
    async def test_returns_system_when_present(self):
        mock_system = MagicMock()
        request = _make_request({"jarvis_system": mock_system})
        result = await get_jarvis(request)
        assert result is mock_system

    @pytest.mark.asyncio
    async def test_raises_500_when_not_initialized(self):
        request = _make_request({})
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await get_jarvis(request)
        assert exc_info.value.status_code == 500
        assert "not initialized" in exc_info.value.detail


# ---------------------------------------------------------------------------
# get_auth_db
# ---------------------------------------------------------------------------

class TestGetAuthDb:
    """Tests for the get_auth_db dependency."""

    def test_returns_db_from_state(self):
        mock_db = MagicMock()
        request = _make_request({"auth_db": mock_db})
        assert get_auth_db(request) is mock_db


# ---------------------------------------------------------------------------
# get_fact_service
# ---------------------------------------------------------------------------

class TestGetFactService:
    """Tests for the get_fact_service dependency."""

    def test_returns_fact_memory_service(self, tmp_path):
        os.environ["AUTH_DB_PATH"] = str(tmp_path / "fact_test.db")
        svc = get_fact_service()
        from jarvis.services.fact_memory import FactMemoryService

        assert isinstance(svc, FactMemoryService)


# ---------------------------------------------------------------------------
# get_current_user
# ---------------------------------------------------------------------------

class TestGetCurrentUser:
    """Tests for the get_current_user dependency."""

    @pytest.mark.asyncio
    async def test_missing_auth_header_returns_401(self, tmp_path):
        db = _test_db(tmp_path)
        request = _make_request(headers={})
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(request, db)
        assert exc_info.value.status_code == 401
        db.close()

    @pytest.mark.asyncio
    async def test_malformed_auth_header_returns_401(self, tmp_path):
        db = _test_db(tmp_path)
        request = _make_request(headers={"Authorization": "NotBearer token"})
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(request, db)
        assert exc_info.value.status_code == 401
        db.close()

    @pytest.mark.asyncio
    async def test_invalid_token_returns_401(self, tmp_path):
        db = _test_db(tmp_path)
        request = _make_request(headers={"Authorization": "Bearer invalid_token"})
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(request, db)
        assert exc_info.value.status_code == 401
        db.close()

    @pytest.mark.asyncio
    async def test_valid_token_but_user_not_in_db_returns_401(self, tmp_path):
        db = _test_db(tmp_path)
        token = create_token("unknown@test.com")
        request = _make_request(headers={"Authorization": f"Bearer {token}"})
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(request, db)
        assert exc_info.value.status_code == 401
        assert "User not found" in exc_info.value.detail
        db.close()

    @pytest.mark.asyncio
    async def test_valid_token_and_existing_user_returns_user_dict(self, tmp_path):
        db = _test_db(tmp_path)
        token = create_token("dep@test.com")
        request = _make_request(headers={"Authorization": f"Bearer {token}"})
        user = await get_current_user(request, db)
        assert user["email"] == "dep@test.com"
        assert user["id"] == 1
        db.close()


# ---------------------------------------------------------------------------
# get_user_allowed_agents
# ---------------------------------------------------------------------------

class TestGetUserAllowedAgents:
    """Tests for the get_user_allowed_agents dependency."""

    @pytest.mark.asyncio
    async def test_no_permissions_returns_all_agents(self, tmp_path):
        db = _test_db(tmp_path)
        mock_jarvis = MagicMock()
        mock_jarvis.list_agents.return_value = {
            "CalendarAgent": {},
            "WeatherAgent": {},
        }
        current_user = {"id": 1, "email": "dep@test.com"}
        result = await get_user_allowed_agents(current_user, db, mock_jarvis)
        assert result == {"CalendarAgent", "WeatherAgent"}
        db.close()

    @pytest.mark.asyncio
    async def test_with_permissions_returns_allowed_only(self, tmp_path):
        db = _test_db(tmp_path)
        from server.database import set_user_agent_permissions

        # Need user_agents table
        db.execute(
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
        db.commit()
        set_user_agent_permissions(
            db, 1, {"CalendarAgent": True, "WeatherAgent": False}
        )
        mock_jarvis = MagicMock()
        current_user = {"id": 1, "email": "dep@test.com"}
        result = await get_user_allowed_agents(current_user, db, mock_jarvis)
        assert result == {"CalendarAgent"}
        db.close()
