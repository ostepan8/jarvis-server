import sqlite3
import httpx
import pytest
from httpx import ASGITransport

import server

class DummyJarvis:
    def __init__(self):
        self.last_allowed = None
    async def process_request(self, command, tz, metadata, allowed_agents=None):
        self.last_allowed = allowed_agents
        return {"response": "done"}
    def list_agents(self):
        return {"A": {}, "B": {}}

@pytest.mark.asyncio
async def test_agent_preferences_endpoints(tmp_path):
    db = sqlite3.connect(tmp_path / "auth.db", check_same_thread=False)
    db.execute(
        "CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT UNIQUE, password_hash TEXT)"
    )
    db.execute(
        "CREATE TABLE user_agents (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, agent_name TEXT, allowed INTEGER, UNIQUE(user_id, agent_name))"
    )
    db.commit()

    server.app.router.on_startup.clear()
    server.app.router.on_shutdown.clear()
    server.app.state.auth_db = db

    jarvis = DummyJarvis()
    async def override_get_jarvis():
        return jarvis
    server.app.dependency_overrides[server.get_jarvis] = override_get_jarvis
    server.app.dependency_overrides[server.get_user_jarvis] = override_get_jarvis

    transport = ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/auth/signup", json={"email": "u@test.com", "password": "pw"})
        token = resp.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}
        resp = await client.post(
            "/users/me/agents", json={"allowed": ["A"], "disallowed": ["B"]}, headers=headers
        )
        assert resp.status_code == 200
        resp = await client.get("/users/me/agents", headers=headers)
        assert resp.json()["allowed"] == ["A"]
        assert resp.json()["disallowed"] == ["B"]

        await client.post("/jarvis/", json={"command": "test"}, headers=headers)
        assert jarvis.last_allowed == {"A"}

    db.close()

