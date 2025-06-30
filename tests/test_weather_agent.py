import pytest

from jarvis.agents.weather_agent import WeatherAgent
from jarvis.agents.message import Message

class MockResponse:
    def __init__(self, data):
        self._data = data
    def json(self):
        return self._data

@pytest.mark.asyncio
async def test_get_current_weather(monkeypatch):
    agent = WeatherAgent(api_key="key")
    async def mock_get(url, params=None):
        assert "weather" in url
        assert params["q"] == "London"
        assert params["appid"] == "key"
        return MockResponse({
            "weather": [{"description": "sunny"}],
            "main": {"temp": 25}
        })
    monkeypatch.setattr(agent.client, "get", mock_get)
    result = await agent.get_current_weather("London")
    assert result == {"location": "London", "temperature": 25, "description": "sunny"}

@pytest.mark.asyncio
async def test_handle_request(monkeypatch):
    agent = WeatherAgent(api_key="key")
    async def fake_get_current_weather(loc):
        return {"location": loc, "temperature": 10, "description": "cloudy"}

    monkeypatch.setattr(agent, "get_current_weather", fake_get_current_weather)
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
        content={"capability": "get_current_weather", "data": {"location": "Paris"}},
        request_id="1"
    )
    await agent._handle_capability_request(message)
    assert captured["result"]["location"] == "Paris"
