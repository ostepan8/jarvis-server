"""Tests for server.routers.goodmorning — good morning routine endpoint."""

import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from httpx import ASGITransport

import server
from tests import disable_lifespan
from server.database import init_database
from server.routers.goodmorning import _build_greeting


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _setup_app(tmp_path):
    """Prepare the app with a mock jarvis system."""
    db_path = str(tmp_path / "gm_test.db")
    os.environ["AUTH_DB_PATH"] = db_path
    db = init_database()

    mock_jarvis = MagicMock()
    mock_jarvis.logger = MagicMock()
    mock_jarvis.network = SimpleNamespace(agents={})

    disable_lifespan(server.app)
    server.app.state.jarvis_system = mock_jarvis
    server.app.state.auth_db = db

    def cleanup():
        server.app.dependency_overrides.clear()
        db.close()

    return db, mock_jarvis, cleanup


# ---------------------------------------------------------------------------
# Tests for POST /goodmorning
# ---------------------------------------------------------------------------

class TestGoodmorningEndpoint:
    """Tests for POST /goodmorning ."""

    @pytest.mark.asyncio
    async def test_goodmorning_returns_ok(self, tmp_path):
        db, _, cleanup = _setup_app(tmp_path)
        try:
            transport = ASGITransport(app=server.app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post("/goodmorning", json={})
                assert resp.status_code == 200
                data = resp.json()
                assert data["status"] == "ok"
                assert data["message"] == "Good morning queued"
        finally:
            cleanup()

    @pytest.mark.asyncio
    async def test_goodmorning_with_payload(self, tmp_path):
        db, _, cleanup = _setup_app(tmp_path)
        try:
            transport = ASGITransport(app=server.app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                payload = {
                    "timezone": "America/New_York",
                    "wake_time": "2026-03-09T07:00:00-04:00",
                    "context": {
                        "earliest_event": {
                            "title": "Standup",
                            "start": "2026-03-09T09:00:00-04:00",
                        }
                    },
                }
                resp = await client.post("/goodmorning", json=payload)
                assert resp.status_code == 200
                data = resp.json()
                assert data["status"] == "ok"
                # The payload should be echoed in "received"
                assert data["received"]["json"] is not None
        finally:
            cleanup()

    @pytest.mark.asyncio
    async def test_goodmorning_with_empty_body(self, tmp_path):
        db, _, cleanup = _setup_app(tmp_path)
        try:
            transport = ASGITransport(app=server.app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/goodmorning",
                    content=b"",
                    headers={"content-type": "application/json"},
                )
                assert resp.status_code == 200
                data = resp.json()
                assert data["status"] == "ok"
        finally:
            cleanup()

    @pytest.mark.asyncio
    async def test_goodmorning_with_invalid_json(self, tmp_path):
        db, _, cleanup = _setup_app(tmp_path)
        try:
            transport = ASGITransport(app=server.app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/goodmorning",
                    content=b"not-json-content",
                    headers={"content-type": "text/plain"},
                )
                assert resp.status_code == 200
                data = resp.json()
                assert data["status"] == "ok"
        finally:
            cleanup()


# ---------------------------------------------------------------------------
# Tests for _build_greeting (unit tests)
# ---------------------------------------------------------------------------

class TestBuildGreeting:
    """Unit tests for the _build_greeting helper."""

    def test_minimal_greeting(self):
        greeting = _build_greeting({})
        assert "Good morning" in greeting
        assert "Time to rise and shine" in greeting

    def test_greeting_with_time(self):
        greeting = _build_greeting({
            "timezone": "America/New_York",
            "wake_time": "2026-03-09T07:00:00-04:00",
        })
        assert "Good morning" in greeting
        assert "7:00 AM" in greeting

    def test_greeting_with_event(self):
        greeting = _build_greeting({
            "timezone": "America/New_York",
            "wake_time": "2026-03-09T07:00:00-04:00",
            "context": {
                "earliest_event": {
                    "title": "Standup",
                    "start": "2026-03-09T09:00:00-04:00",
                }
            },
        })
        assert "Standup" in greeting
        assert "9:00 AM" in greeting

    def test_greeting_with_first_events_list(self):
        greeting = _build_greeting({
            "timezone": "UTC",
            "context": {
                "first_events": [
                    {"title": "Meeting", "start": "2026-03-09T10:00:00Z"},
                ]
            },
        })
        assert "Meeting" in greeting

    def test_greeting_with_no_timezone(self):
        """Should still produce a greeting when timezone is missing."""
        greeting = _build_greeting({
            "wake_time": "2026-03-09T07:00:00Z",
        })
        assert "Good morning" in greeting

    def test_greeting_with_empty_context(self):
        greeting = _build_greeting({"context": {}})
        assert "Good morning" in greeting

    def test_greeting_with_invalid_wake_time(self):
        """Invalid wake_time should not crash, just skip time display."""
        greeting = _build_greeting({"wake_time": "not-a-date"})
        assert "Good morning" in greeting
