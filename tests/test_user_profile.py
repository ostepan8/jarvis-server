import sqlite3
import httpx
import pytest
from httpx import ASGITransport

import server


class DummyJarvis:
    def __init__(self):
        self.last_metadata = None

    async def process_request(self, command, tz, metadata, allowed_agents=None):
        self.last_metadata = metadata
        return {"response": "ok"}

    def list_agents(self):
        return {"A": {}}


@pytest.mark.asyncio
async def test_user_profile_endpoints(tmp_path):
    db = sqlite3.connect(tmp_path / "auth.db", check_same_thread=False)
    db.execute(
        "CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT UNIQUE, password_hash TEXT)"
    )
    db.execute(
        "CREATE TABLE user_agents (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, agent_name TEXT, allowed INTEGER, UNIQUE(user_id, agent_name))"
    )
    db.execute(
        "CREATE TABLE user_profiles (user_id INTEGER PRIMARY KEY, name TEXT, preferred_personality TEXT, interests TEXT, conversation_style TEXT, humor_preference TEXT, topics_of_interest TEXT, language_preference TEXT, interaction_count INTEGER DEFAULT 0, favorite_games TEXT, last_seen TEXT, required_resources TEXT)"
    )
    db.commit()

    server.app.router.on_startup.clear()
    server.app.router.on_shutdown.clear()
    server.app.state.auth_db = db

    jarvis = DummyJarvis()

    async def override_get_jarvis():
        return jarvis

    server.app.dependency_overrides[server.get_jarvis] = override_get_jarvis

    transport = ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/auth/signup", json={"email": "p@test.com", "password": "pw"})
        token = resp.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        resp = await client.post(
            "/users/me/profile",
            json={"name": "Alice", "interests": ["ai"]},
            headers=headers,
        )
        assert resp.status_code == 200

        resp = await client.get("/users/me/profile", headers=headers)
        assert resp.json()["name"] == "Alice"
        assert resp.json()["interests"] == ["ai"]

        await client.post("/jarvis/", json={"command": "hi"}, headers=headers)
        assert jarvis.last_metadata["profile"]["name"] == "Alice"

    db.close()
