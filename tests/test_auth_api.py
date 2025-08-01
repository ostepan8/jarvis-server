import sqlite3
import httpx
import pytest
from httpx import ASGITransport
import server


@pytest.mark.asyncio
async def test_signup_and_login(tmp_path):
    db = sqlite3.connect(tmp_path / "auth.db")
    db.execute(
        "CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT UNIQUE, password_hash TEXT)"
    )
    db.commit()
    server.app.router.on_startup.clear()
    server.app.router.on_shutdown.clear()
    server.app.state.auth_db = db
    transport = ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/auth/signup", json={"email": "a@test.com", "password": "pw"}
        )
        assert resp.status_code == 200
        assert "token" in resp.json()
        resp = await client.post(
            "/auth/login", json={"email": "a@test.com", "password": "pw"}
        )
        assert resp.status_code == 200
        token = resp.json()["token"]
        resp = await client.get(
            "/auth/verify", headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 200
        assert resp.json()["email"] == "a@test.com"
    db.close()


@pytest.mark.asyncio
async def test_invalid_login(tmp_path):
    db = sqlite3.connect(tmp_path / "auth.db")
    db.execute(
        "CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT UNIQUE, password_hash TEXT)"
    )
    hashed = server.pwd_context.hash("realpass")
    db.execute(
        "INSERT INTO users (email, password_hash) VALUES ('b@test.com', ?)", (hashed,)
    )
    db.commit()
    server.app.router.on_startup.clear()
    server.app.router.on_shutdown.clear()
    server.app.state.auth_db = db
    transport = ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/auth/login", json={"email": "b@test.com", "password": "wrong"}
        )
        assert resp.status_code == 401
        assert resp.json()["error"] == "Authentication failed"
    db.close()
