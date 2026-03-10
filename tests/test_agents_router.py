"""Tests for server.routers.agents — agent introspection endpoints."""

import os
import sqlite3
from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import pytest
from httpx import ASGITransport

import server
from server.database import init_database


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _setup_app(tmp_path, agents_dict: dict | None = None):
    """Prepare the app with a mock jarvis_system and a temp database."""
    db_path = str(tmp_path / "agents_test.db")
    os.environ["AUTH_DB_PATH"] = db_path
    db = init_database()

    mock_jarvis = MagicMock()
    if agents_dict is None:
        agents_dict = {
            "CalendarAgent": {
                "name": "CalendarAgent",
                "capabilities": ["create_event", "list_events"],
                "description": "Manages calendar events",
                "required_resources": [],
            },
            "SearchAgent": {
                "name": "SearchAgent",
                "capabilities": ["search"],
                "description": "Weather forecasts",
                "required_resources": [],
            },
        }
    mock_jarvis.list_agents.return_value = agents_dict

    def get_caps(name):
        if name in agents_dict:
            info = agents_dict[name]
            return {
                "name": info["name"],
                "capabilities": info["capabilities"],
                "description": info["description"],
                "status": "active",
            }
        return {"error": f"Agent '{name}' not found", "available_agents": list(agents_dict.keys())}

    mock_jarvis.get_agent_capabilities.side_effect = get_caps

    # Simulate the network.agents property for iteration
    mock_jarvis.network = SimpleNamespace(agents=agents_dict)

    server.app.router.on_startup.clear()
    server.app.router.on_shutdown.clear()
    server.app.state.jarvis_system = mock_jarvis
    server.app.state.auth_db = db

    return db, mock_jarvis


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestListAgents:
    """Tests for GET /agents/ ."""

    @pytest.mark.asyncio
    async def test_list_agents_returns_all(self, tmp_path):
        db, _ = _setup_app(tmp_path)
        transport = ASGITransport(app=server.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/agents/")
            assert resp.status_code == 200
            data = resp.json()
            assert "CalendarAgent" in data
            assert "SearchAgent" in data
        db.close()

    @pytest.mark.asyncio
    async def test_list_agents_empty_network(self, tmp_path):
        db, _ = _setup_app(tmp_path, agents_dict={})
        transport = ASGITransport(app=server.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/agents/")
            assert resp.status_code == 200
            assert resp.json() == {}
        db.close()


class TestGetAgent:
    """Tests for GET /agents/{agent_name} ."""

    @pytest.mark.asyncio
    async def test_get_existing_agent(self, tmp_path):
        db, _ = _setup_app(tmp_path)
        transport = ASGITransport(app=server.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/agents/CalendarAgent")
            assert resp.status_code == 200
            data = resp.json()
            assert data["name"] == "CalendarAgent"
        db.close()

    @pytest.mark.asyncio
    async def test_get_nonexistent_agent_returns_404(self, tmp_path):
        db, _ = _setup_app(tmp_path)
        transport = ASGITransport(app=server.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/agents/NonExistentAgent")
            assert resp.status_code == 404
            assert "not found" in resp.json()["detail"].lower()
        db.close()


class TestGetAgentCapabilities:
    """Tests for GET /agents/{agent_name}/capabilities ."""

    @pytest.mark.asyncio
    async def test_get_capabilities_for_existing_agent(self, tmp_path):
        db, _ = _setup_app(tmp_path)
        transport = ASGITransport(app=server.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/agents/CalendarAgent/capabilities")
            assert resp.status_code == 200
            data = resp.json()
            assert data["name"] == "CalendarAgent"
            assert "create_event" in data["capabilities"]
        db.close()

    @pytest.mark.asyncio
    async def test_get_capabilities_for_missing_agent(self, tmp_path):
        db, _ = _setup_app(tmp_path)
        transport = ASGITransport(app=server.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/agents/FakeAgent/capabilities")
            assert resp.status_code == 200
            data = resp.json()
            assert "error" in data
        db.close()
