"""Tests for server.routers.admin — admin dashboard and analytics endpoints."""

import os
import sqlite3
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, PropertyMock

import httpx
import pytest
from httpx import ASGITransport

import server
from tests import disable_lifespan
from server.database import init_database
from server.dependencies import get_jarvis, get_auth_db, get_fact_service
from server.routers import admin as admin_module


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _setup_app(tmp_path, with_jarvis=True):
    """Prepare the app with a temp database and a mock jarvis system."""
    db_path = str(tmp_path / "admin_test.db")
    os.environ["AUTH_DB_PATH"] = db_path
    db = init_database()

    mock_jarvis = MagicMock()
    mock_jarvis.usage_logger = None
    mock_jarvis.interaction_logger = None
    mock_jarvis._agent_refs = {}
    mock_jarvis.list_agents.return_value = {}
    mock_jarvis.network = SimpleNamespace(agents={})
    mock_jarvis.logger = MagicMock()
    mock_jarvis.process_request = AsyncMock(
        return_value={"response": "admin result", "success": True}
    )

    disable_lifespan(server.app)
    server.app.state.auth_db = db
    server.app.state.jarvis_system = mock_jarvis if with_jarvis else None

    # Clear the dashboard cache between tests
    admin_module._dashboard_cache = None
    admin_module._cache_timestamp = 0

    def cleanup():
        server.app.dependency_overrides.clear()
        admin_module._dashboard_cache = None
        admin_module._cache_timestamp = 0
        db.close()

    return db, mock_jarvis, cleanup


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

class TestDashboardEndpoint:
    """Tests for GET /admin/dashboard ."""

    @pytest.mark.asyncio
    async def test_dashboard_returns_overview(self, tmp_path):
        db, _, cleanup = _setup_app(tmp_path)
        try:
            transport = ASGITransport(app=server.app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/admin/dashboard?use_cache=false")
                assert resp.status_code == 200
                data = resp.json()
                assert "overview" in data
                assert "log_stats" in data
                assert "protocol_stats" in data
                assert "user_stats" in data
                assert "memory_stats" in data
        finally:
            cleanup()

    @pytest.mark.asyncio
    async def test_dashboard_overview_fields(self, tmp_path):
        db, _, cleanup = _setup_app(tmp_path)
        try:
            transport = ASGITransport(app=server.app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/admin/dashboard?use_cache=false")
                overview = resp.json()["overview"]
                assert "total_users" in overview
                assert "total_interactions" in overview
                assert "total_logs" in overview
                assert "total_protocol_executions" in overview
        finally:
            cleanup()

    @pytest.mark.asyncio
    async def test_dashboard_user_stats_with_users(self, tmp_path):
        db, _, cleanup = _setup_app(tmp_path)
        # Insert some users
        db.execute(
            "INSERT INTO users (email, password_hash) VALUES (?, ?)",
            ("admin1@test.com", "hash"),
        )
        db.execute(
            "INSERT INTO users (email, password_hash) VALUES (?, ?)",
            ("admin2@test.com", "hash"),
        )
        db.commit()
        try:
            transport = ASGITransport(app=server.app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/admin/dashboard?use_cache=false")
                user_stats = resp.json()["user_stats"]
                assert user_stats["total_users"] == 2
        finally:
            cleanup()

    @pytest.mark.asyncio
    async def test_dashboard_caching(self, tmp_path):
        """The second request should return cached data."""
        db, _, cleanup = _setup_app(tmp_path)
        try:
            transport = ASGITransport(app=server.app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                resp1 = await client.get("/admin/dashboard?use_cache=false")
                assert resp1.status_code == 200
                # Second call uses cache
                resp2 = await client.get("/admin/dashboard")
                assert resp2.status_code == 200
                assert resp2.json() == resp1.json()
        finally:
            cleanup()


# ---------------------------------------------------------------------------
# Logs
# ---------------------------------------------------------------------------

class TestLogsEndpoint:
    """Tests for GET /admin/logs ."""

    @pytest.mark.asyncio
    async def test_logs_returns_empty_when_no_db(self, tmp_path):
        db, _, cleanup = _setup_app(tmp_path)
        # Point to a non-existent logs db
        os.environ["LOG_DB_PATH"] = str(tmp_path / "nonexistent_logs.db")
        try:
            transport = ASGITransport(app=server.app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/admin/logs")
                assert resp.status_code == 200
                data = resp.json()
                assert data["logs"] == []
                assert data["total"] == 0
        finally:
            cleanup()

    @pytest.mark.asyncio
    async def test_logs_with_data(self, tmp_path):
        db, _, cleanup = _setup_app(tmp_path)
        logs_path = str(tmp_path / "test_logs.db")
        os.environ["LOG_DB_PATH"] = logs_path

        # Create a logs database with data
        logs_db = sqlite3.connect(logs_path)
        logs_db.execute(
            "CREATE TABLE logs (id INTEGER PRIMARY KEY, timestamp TEXT, level TEXT, action TEXT, details TEXT)"
        )
        logs_db.execute(
            "INSERT INTO logs (timestamp, level, action, details) VALUES (?, ?, ?, ?)",
            ("2026-03-09T10:00:00", "INFO", "test_action", "test details"),
        )
        logs_db.execute(
            "INSERT INTO logs (timestamp, level, action, details) VALUES (?, ?, ?, ?)",
            ("2026-03-09T10:01:00", "ERROR", "error_action", "error details"),
        )
        logs_db.commit()
        logs_db.close()

        try:
            transport = ASGITransport(app=server.app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/admin/logs")
                assert resp.status_code == 200
                data = resp.json()
                assert data["total"] == 2
                assert len(data["logs"]) == 2
        finally:
            cleanup()

    @pytest.mark.asyncio
    async def test_logs_filter_by_level(self, tmp_path):
        db, _, cleanup = _setup_app(tmp_path)
        logs_path = str(tmp_path / "test_logs2.db")
        os.environ["LOG_DB_PATH"] = logs_path

        logs_db = sqlite3.connect(logs_path)
        logs_db.execute(
            "CREATE TABLE logs (id INTEGER PRIMARY KEY, timestamp TEXT, level TEXT, action TEXT, details TEXT)"
        )
        logs_db.execute(
            "INSERT INTO logs (timestamp, level, action, details) VALUES (?, ?, ?, ?)",
            ("2026-03-09T10:00:00", "INFO", "info_action", "info"),
        )
        logs_db.execute(
            "INSERT INTO logs (timestamp, level, action, details) VALUES (?, ?, ?, ?)",
            ("2026-03-09T10:01:00", "ERROR", "error_action", "error"),
        )
        logs_db.commit()
        logs_db.close()

        try:
            transport = ASGITransport(app=server.app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/admin/logs?level=ERROR")
                data = resp.json()
                assert data["total"] == 1
                assert all(log["level"] == "ERROR" for log in data["logs"])
        finally:
            cleanup()

    @pytest.mark.asyncio
    async def test_logs_pagination(self, tmp_path):
        db, _, cleanup = _setup_app(tmp_path)
        logs_path = str(tmp_path / "test_logs_pag.db")
        os.environ["LOG_DB_PATH"] = logs_path

        logs_db = sqlite3.connect(logs_path)
        logs_db.execute(
            "CREATE TABLE logs (id INTEGER PRIMARY KEY, timestamp TEXT, level TEXT, action TEXT, details TEXT)"
        )
        for i in range(5):
            logs_db.execute(
                "INSERT INTO logs (timestamp, level, action, details) VALUES (?, ?, ?, ?)",
                (f"2026-03-09T10:0{i}:00", "INFO", f"action_{i}", f"details_{i}"),
            )
        logs_db.commit()
        logs_db.close()

        try:
            transport = ASGITransport(app=server.app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/admin/logs?limit=2&offset=0")
                data = resp.json()
                assert len(data["logs"]) == 2
                assert data["limit"] == 2
                assert data["offset"] == 0
        finally:
            cleanup()


# ---------------------------------------------------------------------------
# Memories
# ---------------------------------------------------------------------------

class TestMemoriesEndpoint:
    """Tests for GET /admin/memories ."""

    @pytest.mark.asyncio
    async def test_memories_no_vector_memory(self, tmp_path):
        db, _, cleanup = _setup_app(tmp_path)
        try:
            transport = ASGITransport(app=server.app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/admin/memories")
                assert resp.status_code == 200
                data = resp.json()
                assert data["memories"] == []
                assert data["total"] == 0
        finally:
            cleanup()


# ---------------------------------------------------------------------------
# Interactions
# ---------------------------------------------------------------------------

class TestInteractionsEndpoint:
    """Tests for GET /admin/interactions ."""

    @pytest.mark.asyncio
    async def test_interactions_no_logger(self, tmp_path):
        db, _, cleanup = _setup_app(tmp_path)
        try:
            transport = ASGITransport(app=server.app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/admin/interactions")
                assert resp.status_code == 200
                data = resp.json()
                assert data["interactions"] == []
                assert "error" in data
        finally:
            cleanup()


# ---------------------------------------------------------------------------
# Admin query
# ---------------------------------------------------------------------------

class TestAdminQueryEndpoint:
    """Tests for POST /admin/query ."""

    @pytest.mark.asyncio
    async def test_admin_query_success(self, tmp_path):
        db, mock_jarvis, cleanup = _setup_app(tmp_path)
        try:
            transport = ASGITransport(app=server.app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/admin/query",
                    json={"command": "list events"},
                )
                assert resp.status_code == 200
                data = resp.json()
                assert data["success"] is True
                assert data["response"] == "admin result"
        finally:
            cleanup()

    @pytest.mark.asyncio
    async def test_admin_query_no_jarvis_returns_500(self, tmp_path):
        db, _, cleanup = _setup_app(tmp_path, with_jarvis=False)
        server.app.state.jarvis_system = None
        try:
            transport = ASGITransport(app=server.app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/admin/query",
                    json={"command": "test"},
                )
                assert resp.status_code == 500
        finally:
            cleanup()

    @pytest.mark.asyncio
    async def test_admin_query_missing_command_returns_422(self, tmp_path):
        db, _, cleanup = _setup_app(tmp_path)
        try:
            transport = ASGITransport(app=server.app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post("/admin/query", json={})
                assert resp.status_code == 422
        finally:
            cleanup()


# ---------------------------------------------------------------------------
# HTML pages (existence check — may return 404 if static files are missing)
# ---------------------------------------------------------------------------

class TestAdminHTMLEndpoints:
    """Tests for the HTML dashboard/log/memory page endpoints."""

    @pytest.mark.asyncio
    async def test_dashboard_html_returns_response(self, tmp_path):
        db, _, cleanup = _setup_app(tmp_path)
        try:
            transport = ASGITransport(app=server.app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/admin/dashboard/html")
                # Will be 200 if the static file exists, 404 otherwise
                assert resp.status_code in (200, 404)
        finally:
            cleanup()

    @pytest.mark.asyncio
    async def test_logs_html_returns_response(self, tmp_path):
        db, _, cleanup = _setup_app(tmp_path)
        try:
            transport = ASGITransport(app=server.app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/admin/logs/html")
                assert resp.status_code in (200, 404)
        finally:
            cleanup()

    @pytest.mark.asyncio
    async def test_memories_html_returns_response(self, tmp_path):
        db, _, cleanup = _setup_app(tmp_path)
        try:
            transport = ASGITransport(app=server.app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/admin/memories/html")
                assert resp.status_code in (200, 404)
        finally:
            cleanup()

    @pytest.mark.asyncio
    async def test_interactions_html_returns_response(self, tmp_path):
        db, _, cleanup = _setup_app(tmp_path)
        try:
            transport = ASGITransport(app=server.app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/admin/interactions/html")
                assert resp.status_code in (200, 404)
        finally:
            cleanup()
