"""Tests for server.main — app setup, middleware, CORS, and route registration."""

import os
from unittest.mock import MagicMock

import httpx
import pytest
from httpx import ASGITransport

import server
from server.main import create_app
from server.database import init_database


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

class TestCreateApp:
    """Tests for the create_app factory function."""

    def test_create_app_returns_fastapi_instance(self):
        from fastapi import FastAPI
        app = create_app()
        assert isinstance(app, FastAPI)

    def test_create_app_title(self):
        app = create_app()
        assert app.title == "Jarvis API"

    def test_create_app_has_routers(self):
        app = create_app()
        # Collect all route paths
        paths = {route.path for route in app.routes}
        # Check key prefixes exist
        assert any("/jarvis" in p for p in paths)
        assert any("/auth" in p for p in paths)
        assert any("/agents" in p for p in paths)
        assert any("/protocols" in p for p in paths)
        assert any("/users" in p for p in paths)
        assert any("/goodmorning" in p for p in paths)
        assert any("/admin" in p for p in paths)


# ---------------------------------------------------------------------------
# CORS middleware
# ---------------------------------------------------------------------------

class TestCORSMiddleware:
    """Tests for CORS configuration."""

    @pytest.mark.asyncio
    async def test_cors_allows_localhost_3000(self, tmp_path):
        db_path = str(tmp_path / "cors_test.db")
        os.environ["AUTH_DB_PATH"] = db_path
        db = init_database()
        server.app.router.on_startup.clear()
        server.app.router.on_shutdown.clear()
        server.app.state.auth_db = db
        server.app.state.jarvis_system = MagicMock()

        try:
            transport = ASGITransport(app=server.app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                # Preflight request
                resp = await client.options(
                    "/agents/",
                    headers={
                        "Origin": "http://localhost:3000",
                        "Access-Control-Request-Method": "GET",
                    },
                )
                assert resp.status_code == 200
                assert (
                    resp.headers.get("access-control-allow-origin")
                    == "http://localhost:3000"
                )
        finally:
            db.close()

    @pytest.mark.asyncio
    async def test_cors_allows_vite_default(self, tmp_path):
        db_path = str(tmp_path / "cors_test2.db")
        os.environ["AUTH_DB_PATH"] = db_path
        db = init_database()
        server.app.router.on_startup.clear()
        server.app.router.on_shutdown.clear()
        server.app.state.auth_db = db
        server.app.state.jarvis_system = MagicMock()

        try:
            transport = ASGITransport(app=server.app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.options(
                    "/agents/",
                    headers={
                        "Origin": "http://localhost:5173",
                        "Access-Control-Request-Method": "GET",
                    },
                )
                assert resp.status_code == 200
                assert (
                    resp.headers.get("access-control-allow-origin")
                    == "http://localhost:5173"
                )
        finally:
            db.close()

    @pytest.mark.asyncio
    async def test_cors_rejects_unknown_origin(self, tmp_path):
        db_path = str(tmp_path / "cors_test3.db")
        os.environ["AUTH_DB_PATH"] = db_path
        db = init_database()
        server.app.router.on_startup.clear()
        server.app.router.on_shutdown.clear()
        server.app.state.auth_db = db
        server.app.state.jarvis_system = MagicMock()

        try:
            transport = ASGITransport(app=server.app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.options(
                    "/agents/",
                    headers={
                        "Origin": "http://evil.com",
                        "Access-Control-Request-Method": "GET",
                    },
                )
                # The response may be 200 (preflight) but should NOT have
                # the access-control-allow-origin set to the evil origin
                allow_origin = resp.headers.get("access-control-allow-origin")
                assert allow_origin != "http://evil.com"
        finally:
            db.close()


# ---------------------------------------------------------------------------
# Route existence
# ---------------------------------------------------------------------------

class TestRouteRegistration:
    """Tests verifying that all expected routes are registered."""

    @pytest.mark.asyncio
    async def test_auth_routes_exist(self, tmp_path):
        db_path = str(tmp_path / "routes_test.db")
        os.environ["AUTH_DB_PATH"] = db_path
        db = init_database()
        server.app.router.on_startup.clear()
        server.app.router.on_shutdown.clear()
        server.app.state.auth_db = db
        server.app.state.jarvis_system = MagicMock()

        try:
            transport = ASGITransport(app=server.app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                # signup should accept POST
                resp = await client.post(
                    "/auth/signup",
                    json={"email": "route@test.com", "password": "pass"},
                )
                assert resp.status_code in (200, 401)

                # login should accept POST
                resp = await client.post(
                    "/auth/login",
                    json={"email": "route@test.com", "password": "pass"},
                )
                assert resp.status_code in (200, 401)

                # verify should accept GET
                resp = await client.get("/auth/verify")
                assert resp.status_code in (200, 401)
        finally:
            db.close()

    @pytest.mark.asyncio
    async def test_nonexistent_route_returns_404(self, tmp_path):
        db_path = str(tmp_path / "routes_test2.db")
        os.environ["AUTH_DB_PATH"] = db_path
        db = init_database()
        server.app.router.on_startup.clear()
        server.app.router.on_shutdown.clear()
        server.app.state.auth_db = db
        server.app.state.jarvis_system = MagicMock()

        try:
            transport = ASGITransport(app=server.app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/nonexistent/path")
                assert resp.status_code == 404
        finally:
            db.close()

    @pytest.mark.asyncio
    async def test_method_not_allowed(self, tmp_path):
        db_path = str(tmp_path / "routes_test3.db")
        os.environ["AUTH_DB_PATH"] = db_path
        db = init_database()
        server.app.router.on_startup.clear()
        server.app.router.on_shutdown.clear()
        server.app.state.auth_db = db
        server.app.state.jarvis_system = MagicMock()

        try:
            transport = ASGITransport(app=server.app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                # POST to auth/verify which only supports GET
                resp = await client.post("/auth/verify")
                assert resp.status_code == 405
        finally:
            db.close()
