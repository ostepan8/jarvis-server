import sqlite3
import httpx
import pytest
from httpx import ASGITransport
import server2


@pytest.mark.asyncio
async def test_signup_and_login(tmp_path):
    db = sqlite3.connect(tmp_path / "auth.db")
    db.execute(
        "CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT UNIQUE, password_hash TEXT)"
    )
    db.commit()
    server2.app.router.on_startup.clear()
    server2.app.router.on_shutdown.clear()
    server2.app.state.auth_db = db
    transport = ASGITransport(app=server2.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/signup", json={"email": "a@test.com", "password": "pw"}
        )
        assert resp.status_code == 200
        assert "token" in resp.json()
        resp = await client.post(
            "/login", json={"email": "a@test.com", "password": "pw"}
        )
        assert resp.status_code == 200
        token = resp.json()["token"]
        resp = await client.get("/verify", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json()["email"] == "a@test.com"
    db.close()


@pytest.mark.asyncio
async def test_invalid_login(tmp_path):
    db = sqlite3.connect(tmp_path / "auth.db")
    db.execute(
        "CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT UNIQUE, password_hash TEXT)"
    )
    hashed = server2.pwd_context.hash("realpass")
    db.execute(
        "INSERT INTO users (email, password_hash) VALUES ('b@test.com', ?)", (hashed,)
    )
    db.commit()
    server2.app.router.on_startup.clear()
    server2.app.router.on_shutdown.clear()
    server2.app.state.auth_db = db
    transport = ASGITransport(app=server2.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/login", json={"email": "b@test.com", "password": "wrong"}
        )
        assert resp.status_code == 401
        assert resp.json()["error"] == "Authentication failed"
    db.close()
