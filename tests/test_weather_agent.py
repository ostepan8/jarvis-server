import pytest
import asyncio

from jarvis.agents.weather_agent import WeatherAgent
from jarvis.agents.message import Message
from jarvis.ai_clients.base import BaseAIClient


class DummyAIClient(BaseAIClient):
    async def strong_chat(self, messages, tools=None):
        return None, None

    async def weak_chat(self, messages, tools=None):
        return None, None

class MockResponse:
    def __init__(self, data, status_code=200):
        self._data = data
        self.status_code = status_code
    def json(self):
        return self._data

@pytest.mark.asyncio
async def test_get_current_weather(monkeypatch):
    agent = WeatherAgent(ai_client=DummyAIClient(), api_key="key")
    async def mock_get(url, params=None):
        assert "weather" in url
        assert params["q"] == "London"
        assert params["appid"] == "key"
        return MockResponse({
            "weather": [{"description": "sunny"}],
            "main": {"temp": 25}
        })
    monkeypatch.setattr(agent.client, "get", mock_get)
    result = await asyncio.to_thread(agent._get_current_weather, "London")
    assert result["location"] == "London"
    assert result["temperature"] == 25
    assert result["description"] == "Sunny"

@pytest.mark.asyncio
async def test_handle_request(monkeypatch):
    agent = WeatherAgent(ai_client=DummyAIClient(), api_key="key")
    async def fake_process(cmd):
        return {"location": "Paris", "temperature": 10, "description": "cloudy"}

    monkeypatch.setattr(agent, "_process_weather_command", fake_process)
    captured = {}
    async def fake_send(to, result, request_id, msg_id):
        captured["result"] = result
        captured["to"] = to
        captured["req"] = request_id
    monkeypatch.setattr(agent, "send_capability_response", fake_send)
    message = Message(
        from_agent="tester",
        to_agent="WeatherAgent",
        message_type="capability_request",
        content={"capability": "weather_command", "data": {"command": "Paris"}},
        request_id="1"
    )
    await agent._handle_capability_request(message)
    assert captured["result"]["location"] == "Paris"
