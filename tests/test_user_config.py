import sqlite3
import httpx
import pytest
from httpx import ASGITransport

import server


class DummyJarvis:
    async def process_request(self, command, tz, metadata, allowed_agents=None):
        return {"ok": True}

    def list_agents(self):
        return {"A": {}}


@pytest.mark.asyncio
async def test_user_config_crud(tmp_path):
    db = sqlite3.connect(tmp_path / "auth.db", check_same_thread=False)
    db.execute("CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT UNIQUE, password_hash TEXT)")
    db.execute("CREATE TABLE user_configs (user_id INTEGER PRIMARY KEY, openai_api_key TEXT, anthropic_api_key TEXT, calendar_api_url TEXT, weather_api_key TEXT, hue_bridge_ip TEXT, hue_username TEXT)")
    db.commit()

    server.app.router.on_startup.clear()
    server.app.router.on_shutdown.clear()
    server.app.state.auth_db = db

    jarvis = DummyJarvis()
    async def override_get_jarvis():
        return jarvis

    server.app.dependency_overrides[server.get_user_jarvis] = override_get_jarvis
    server.app.dependency_overrides[server.get_jarvis] = override_get_jarvis

    transport = ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/auth/signup", json={"email": "c@test.com", "password": "pw"})
        token = resp.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        resp = await client.post("/users/me/config", json={"calendar_api_url": "http://x"}, headers=headers)
        assert resp.status_code == 200

        resp = await client.get("/users/me/config", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["calendar_api_url"] == "http://x"

    db.close()
