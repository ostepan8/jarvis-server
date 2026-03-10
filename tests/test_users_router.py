"""Tests for server.routers.users — user profile/config endpoints."""

import os
import sqlite3
from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import pytest
from httpx import ASGITransport

import server
from server.auth import create_token, hash_password
from server.database import init_database
from server.dependencies import (
    get_current_user,
    get_auth_db,
    get_jarvis,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _setup_app(tmp_path):
    """Prepare the app with a temp database, a test user, and a mock jarvis."""
    db_path = str(tmp_path / "users_test.db")
    os.environ["AUTH_DB_PATH"] = db_path
    db = init_database()

    pw_hash = hash_password("testpass")
    db.execute(
        "INSERT INTO users (email, password_hash) VALUES (?, ?)",
        ("user@test.com", pw_hash),
    )
    db.commit()

    mock_jarvis = MagicMock()
    mock_jarvis.list_agents.return_value = {
        "CalendarAgent": {},
        "SearchAgent": {},
    }
    mock_jarvis._orchestrator = None  # Avoid AgentProfile update path

    server.app.router.on_startup.clear()
    server.app.router.on_shutdown.clear()
    server.app.state.jarvis_system = mock_jarvis
    server.app.state.auth_db = db

    token = create_token("user@test.com")

    # Override dependencies to avoid real JWT validation and use our mock
    server.app.dependency_overrides[get_current_user] = lambda: {
        "id": 1,
        "email": "user@test.com",
    }
    server.app.dependency_overrides[get_jarvis] = lambda: mock_jarvis

    def cleanup():
        server.app.dependency_overrides.clear()
        db.close()

    return db, mock_jarvis, token, cleanup


# ---------------------------------------------------------------------------
# Agent permissions
# ---------------------------------------------------------------------------

class TestUserAgentsEndpoints:
    """Tests for GET/POST /users/me/agents ."""

    @pytest.mark.asyncio
    async def test_get_agents_defaults_to_all(self, tmp_path):
        db, _, token, cleanup = _setup_app(tmp_path)
        try:
            transport = ASGITransport(app=server.app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get(
                    "/users/me/agents",
                    headers={"Authorization": f"Bearer {token}"},
                )
                assert resp.status_code == 200
                data = resp.json()
                assert "CalendarAgent" in data["allowed"]
                assert "SearchAgent" in data["allowed"]
                assert data["disallowed"] == []
        finally:
            cleanup()

    @pytest.mark.asyncio
    async def test_set_and_get_agents(self, tmp_path):
        db, _, token, cleanup = _setup_app(tmp_path)
        try:
            transport = ASGITransport(app=server.app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                # Set permissions
                resp = await client.post(
                    "/users/me/agents",
                    json={"allowed": ["CalendarAgent"], "disallowed": ["SearchAgent"]},
                    headers={"Authorization": f"Bearer {token}"},
                )
                assert resp.status_code == 200
                assert resp.json()["success"] is True

                # Read back
                resp = await client.get(
                    "/users/me/agents",
                    headers={"Authorization": f"Bearer {token}"},
                )
                data = resp.json()
                assert "CalendarAgent" in data["allowed"]
                assert "SearchAgent" in data["disallowed"]
        finally:
            cleanup()

    @pytest.mark.asyncio
    async def test_set_agents_empty_body(self, tmp_path):
        db, _, token, cleanup = _setup_app(tmp_path)
        try:
            transport = ASGITransport(app=server.app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/users/me/agents",
                    json={},
                    headers={"Authorization": f"Bearer {token}"},
                )
                assert resp.status_code == 200
        finally:
            cleanup()


# ---------------------------------------------------------------------------
# Profile endpoints
# ---------------------------------------------------------------------------

class TestUserProfileEndpoints:
    """Tests for GET/POST /users/me/profile ."""

    @pytest.mark.asyncio
    async def test_get_profile_empty(self, tmp_path):
        db, _, token, cleanup = _setup_app(tmp_path)
        try:
            transport = ASGITransport(app=server.app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get(
                    "/users/me/profile",
                    headers={"Authorization": f"Bearer {token}"},
                )
                assert resp.status_code == 200
                # Should be an empty dict or have all None fields
                data = resp.json()
                assert isinstance(data, dict)
        finally:
            cleanup()

    @pytest.mark.asyncio
    async def test_set_and_get_profile(self, tmp_path):
        db, _, token, cleanup = _setup_app(tmp_path)
        try:
            transport = ASGITransport(app=server.app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/users/me/profile",
                    json={"name": "Alice", "interests": ["coding", "music"]},
                    headers={"Authorization": f"Bearer {token}"},
                )
                assert resp.status_code == 200
                assert resp.json()["success"] is True

                resp = await client.get(
                    "/users/me/profile",
                    headers={"Authorization": f"Bearer {token}"},
                )
                data = resp.json()
                assert data["name"] == "Alice"
                assert data["interests"] == ["coding", "music"]
        finally:
            cleanup()

    @pytest.mark.asyncio
    async def test_update_profile_partial(self, tmp_path):
        db, _, token, cleanup = _setup_app(tmp_path)
        try:
            transport = ASGITransport(app=server.app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                # First set
                await client.post(
                    "/users/me/profile",
                    json={"name": "Bob", "conversation_style": "formal"},
                    headers={"Authorization": f"Bearer {token}"},
                )
                # Update only name
                await client.post(
                    "/users/me/profile",
                    json={"name": "Charlie"},
                    headers={"Authorization": f"Bearer {token}"},
                )
                resp = await client.get(
                    "/users/me/profile",
                    headers={"Authorization": f"Bearer {token}"},
                )
                data = resp.json()
                assert data["name"] == "Charlie"
                # conversation_style should still be "formal"
                assert data["conversation_style"] == "formal"
        finally:
            cleanup()


# ---------------------------------------------------------------------------
# Config endpoints
# ---------------------------------------------------------------------------

class TestUserConfigEndpoints:
    """Tests for GET/POST /users/me/config ."""

    @pytest.mark.asyncio
    async def test_get_config_empty(self, tmp_path):
        db, _, token, cleanup = _setup_app(tmp_path)
        try:
            transport = ASGITransport(app=server.app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get(
                    "/users/me/config",
                    headers={"Authorization": f"Bearer {token}"},
                )
                assert resp.status_code == 200
        finally:
            cleanup()

    @pytest.mark.asyncio
    async def test_set_and_get_config(self, tmp_path):
        db, _, token, cleanup = _setup_app(tmp_path)
        try:
            transport = ASGITransport(app=server.app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/users/me/config",
                    json={"hue_bridge_ip": "192.168.1.1", "calendar_api_url": "http://cal"},
                    headers={"Authorization": f"Bearer {token}"},
                )
                assert resp.status_code == 200
                assert resp.json()["success"] is True

                resp = await client.get(
                    "/users/me/config",
                    headers={"Authorization": f"Bearer {token}"},
                )
                data = resp.json()
                assert data["hue_bridge_ip"] == "192.168.1.1"
                assert data["calendar_api_url"] == "http://cal"
        finally:
            cleanup()

    @pytest.mark.asyncio
    async def test_sensitive_config_roundtrip(self, tmp_path):
        """Sensitive fields are encrypted and decrypted transparently."""
        db, _, token, cleanup = _setup_app(tmp_path)
        try:
            transport = ASGITransport(app=server.app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                await client.post(
                    "/users/me/config",
                    json={"openai_api_key": "sk-my-key"},
                    headers={"Authorization": f"Bearer {token}"},
                )
                resp = await client.get(
                    "/users/me/config",
                    headers={"Authorization": f"Bearer {token}"},
                )
                data = resp.json()
                assert data["openai_api_key"] == "sk-my-key"
        finally:
            cleanup()


# ---------------------------------------------------------------------------
# Auth enforcement (no dependency override)
# ---------------------------------------------------------------------------

class TestUsersAuthRequired:
    """Verify all /users/ endpoints require authentication."""

    @pytest.mark.asyncio
    async def test_get_agents_no_auth(self, tmp_path):
        db_path = str(tmp_path / "noauth.db")
        os.environ["AUTH_DB_PATH"] = db_path
        db = init_database()
        server.app.router.on_startup.clear()
        server.app.router.on_shutdown.clear()
        server.app.state.auth_db = db
        server.app.state.jarvis_system = MagicMock()
        server.app.dependency_overrides.clear()
        try:
            transport = ASGITransport(app=server.app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/users/me/agents")
                assert resp.status_code == 401
        finally:
            db.close()

    @pytest.mark.asyncio
    async def test_get_profile_no_auth(self, tmp_path):
        db_path = str(tmp_path / "noauth2.db")
        os.environ["AUTH_DB_PATH"] = db_path
        db = init_database()
        server.app.router.on_startup.clear()
        server.app.router.on_shutdown.clear()
        server.app.state.auth_db = db
        server.app.state.jarvis_system = MagicMock()
        server.app.dependency_overrides.clear()
        try:
            transport = ASGITransport(app=server.app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/users/me/profile")
                assert resp.status_code == 401
        finally:
            db.close()

    @pytest.mark.asyncio
    async def test_get_config_no_auth(self, tmp_path):
        db_path = str(tmp_path / "noauth3.db")
        os.environ["AUTH_DB_PATH"] = db_path
        db = init_database()
        server.app.router.on_startup.clear()
        server.app.router.on_shutdown.clear()
        server.app.state.auth_db = db
        server.app.state.jarvis_system = MagicMock()
        server.app.dependency_overrides.clear()
        try:
            transport = ASGITransport(app=server.app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/users/me/config")
                assert resp.status_code == 401
        finally:
            db.close()
