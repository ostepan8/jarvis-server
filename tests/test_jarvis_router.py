"""Tests for server.routers.jarvis — main request processing endpoint."""

import os
import sqlite3
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from httpx import ASGITransport

import server
from tests import disable_lifespan
from server.auth import create_token, hash_password
from server.database import init_database
from server.dependencies import (
    get_user_jarvis,
    get_user_allowed_agents,
    get_current_user,
    get_auth_db,
    get_jarvis,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _setup_app(tmp_path, agents_dict=None, process_response=None):
    """Prepare the app with mock jarvis_system, temp db, and a test user.

    We override FastAPI dependencies so that the POST /jarvis/ endpoint does
    not call the real ``JarvisSystem.initialize()`` (which requires MongoDB).
    """
    db_path = str(tmp_path / "jarvis_router_test.db")
    os.environ["AUTH_DB_PATH"] = db_path
    db = init_database()

    # Create test user
    pw_hash = hash_password("testpass")
    db.execute(
        "INSERT INTO users (email, password_hash) VALUES (?, ?)",
        ("jarvis@test.com", pw_hash),
    )
    db.commit()

    if agents_dict is None:
        agents_dict = {
            "CalendarAgent": {
                "name": "CalendarAgent",
                "capabilities": ["create_event"],
                "description": "Calendar",
                "required_resources": [],
            },
        }

    mock_jarvis = MagicMock()
    mock_jarvis.list_agents.return_value = agents_dict
    mock_jarvis.network = SimpleNamespace(agents=agents_dict)

    if process_response is None:
        process_response = {
            "response": "Done!",
            "success": True,
            "actions": [],
        }
    mock_jarvis.process_request = AsyncMock(return_value=process_response)

    def get_caps(name):
        if name in agents_dict:
            return {"name": name, "capabilities": agents_dict[name]["capabilities"]}
        return {"error": f"Agent '{name}' not found"}

    mock_jarvis.get_agent_capabilities.side_effect = get_caps

    disable_lifespan(server.app)
    server.app.state.jarvis_system = mock_jarvis
    server.app.state.auth_db = db
    server.app.state.user_systems = {}

    token = create_token("jarvis@test.com")

    # Override dependencies to avoid real initialization (use lambda, not async)
    _agents_set = set(agents_dict.keys())
    server.app.dependency_overrides[get_user_jarvis] = lambda: mock_jarvis
    server.app.dependency_overrides[get_current_user] = lambda: {"id": 1, "email": "jarvis@test.com"}
    server.app.dependency_overrides[get_user_allowed_agents] = lambda: _agents_set

    def cleanup():
        server.app.dependency_overrides.clear()
        db.close()

    return db, mock_jarvis, token, cleanup


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestJarvisPostEndpoint:
    """Tests for POST /jarvis/ ."""

    @pytest.mark.asyncio
    async def test_authenticated_request_succeeds(self, tmp_path):
        db, mock_jarvis, token, cleanup = _setup_app(tmp_path)
        try:
            transport = ASGITransport(app=server.app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/jarvis/",
                    json={"command": "create an event"},
                    headers={"Authorization": f"Bearer {token}"},
                )
                assert resp.status_code == 200
                data = resp.json()
                assert data["success"] is True
                assert data["response"] == "Done!"
        finally:
            cleanup()

    @pytest.mark.asyncio
    async def test_unauthenticated_request_returns_401(self, tmp_path):
        """Without the dependency override, the real get_current_user
        would reject the request. We restore dependencies for this test."""
        db_path = str(tmp_path / "jarvis_router_test_unauth.db")
        os.environ["AUTH_DB_PATH"] = db_path
        db = init_database()

        disable_lifespan(server.app)
        server.app.state.auth_db = db
        server.app.state.jarvis_system = MagicMock()
        server.app.dependency_overrides.clear()

        try:
            transport = ASGITransport(app=server.app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/jarvis/",
                    json={"command": "hello"},
                )
                assert resp.status_code == 401
        finally:
            db.close()

    @pytest.mark.asyncio
    async def test_invalid_token_returns_401(self, tmp_path):
        db_path = str(tmp_path / "jarvis_router_test_badtok.db")
        os.environ["AUTH_DB_PATH"] = db_path
        db = init_database()

        disable_lifespan(server.app)
        server.app.state.auth_db = db
        server.app.state.jarvis_system = MagicMock()
        server.app.dependency_overrides.clear()

        try:
            transport = ASGITransport(app=server.app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/jarvis/",
                    json={"command": "hello"},
                    headers={"Authorization": "Bearer badtoken"},
                )
                assert resp.status_code == 401
        finally:
            db.close()

    @pytest.mark.asyncio
    async def test_missing_command_returns_422(self, tmp_path):
        db, _, token, cleanup = _setup_app(tmp_path)
        try:
            transport = ASGITransport(app=server.app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/jarvis/",
                    json={},
                    headers={"Authorization": f"Bearer {token}"},
                )
                assert resp.status_code == 422
        finally:
            cleanup()

    @pytest.mark.asyncio
    async def test_process_request_receives_metadata(self, tmp_path):
        db, mock_jarvis, token, cleanup = _setup_app(tmp_path)
        try:
            transport = ASGITransport(app=server.app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                await client.post(
                    "/jarvis/",
                    json={"command": "hello"},
                    headers={
                        "Authorization": f"Bearer {token}",
                        "X-Device": "phone",
                        "X-Source": "voice",
                    },
                )
                call_args = mock_jarvis.process_request.call_args
                assert call_args is not None
                # process_request(command, tz, metadata, allowed_agents=...)
                metadata = call_args[0][2]
                assert metadata["device"] == "phone"
                assert metadata["source"] == "voice"
        finally:
            cleanup()

    @pytest.mark.asyncio
    async def test_process_request_called_with_command(self, tmp_path):
        db, mock_jarvis, token, cleanup = _setup_app(tmp_path)
        try:
            transport = ASGITransport(app=server.app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                await client.post(
                    "/jarvis/",
                    json={"command": "what is the weather"},
                    headers={"Authorization": f"Bearer {token}"},
                )
                call_args = mock_jarvis.process_request.call_args
                assert call_args[0][0] == "what is the weather"
        finally:
            cleanup()

    @pytest.mark.asyncio
    async def test_process_request_error_propagates(self, tmp_path):
        error_resp = {"response": "Something went wrong", "success": False, "actions": []}
        db, mock_jarvis, token, cleanup = _setup_app(
            tmp_path, process_response=error_resp
        )
        try:
            transport = ASGITransport(app=server.app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/jarvis/",
                    json={"command": "do something"},
                    headers={"Authorization": f"Bearer {token}"},
                )
                assert resp.status_code == 200
                data = resp.json()
                assert data["success"] is False
        finally:
            cleanup()


class TestJarvisAgentsSubEndpoints:
    """Tests for GET /jarvis/agents and /jarvis/agents/{name}/capabilities ."""

    @pytest.mark.asyncio
    async def test_list_agents_via_jarvis_prefix(self, tmp_path):
        db, _, _, cleanup = _setup_app(tmp_path)
        try:
            transport = ASGITransport(app=server.app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/jarvis/agents")
                assert resp.status_code == 200
                data = resp.json()
                assert "CalendarAgent" in data
        finally:
            cleanup()

    @pytest.mark.asyncio
    async def test_get_capabilities_via_jarvis_prefix(self, tmp_path):
        db, _, _, cleanup = _setup_app(tmp_path)
        try:
            transport = ASGITransport(app=server.app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/jarvis/agents/CalendarAgent/capabilities")
                assert resp.status_code == 200
                data = resp.json()
                assert data["name"] == "CalendarAgent"
        finally:
            cleanup()
