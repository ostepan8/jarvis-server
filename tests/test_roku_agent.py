import pytest
import asyncio
from unittest.mock import AsyncMock

from jarvis.agents.roku_agent import RokuAgent
from jarvis.agents.message import Message
from jarvis.ai_clients.base import BaseAIClient


class DummyAIClient(BaseAIClient):
    async def strong_chat(self, messages, tools=None):
        return None, None

    async def weak_chat(self, messages, tools=None):
        return None, None


@pytest.mark.asyncio
async def test_roku_agent_initialization():
    """Test that RokuAgent can be initialized successfully."""
    agent = RokuAgent(
        ai_client=DummyAIClient(),
        device_ip="192.168.1.100",
    )
    assert agent.device_ip == "192.168.1.100"
    assert agent.roku_service is not None
    assert agent.function_registry is not None
    assert agent.command_processor is not None
    await agent.close()


@pytest.mark.asyncio
async def test_roku_service_methods_exist(monkeypatch):
    """Test that RokuService has all expected methods."""
    agent = RokuAgent(
        ai_client=DummyAIClient(),
        device_ip="192.168.1.100",
    )

    # Check that key service methods exist
    assert hasattr(agent.roku_service, "get_device_info")
    assert hasattr(agent.roku_service, "list_apps")
    assert hasattr(agent.roku_service, "launch_app_by_name")
    assert hasattr(agent.roku_service, "play")
    assert hasattr(agent.roku_service, "pause")
    assert hasattr(agent.roku_service, "volume_up")
    assert hasattr(agent.roku_service, "home")

    await agent.close()


@pytest.mark.asyncio
async def test_roku_capabilities():
    """Test that RokuAgent exposes correct capabilities."""
    agent = RokuAgent(
        ai_client=DummyAIClient(),
        device_ip="192.168.1.100",
    )

    capabilities = agent.capabilities
    assert "roku_command" in capabilities
    assert "roku_play" in capabilities
    assert "roku_pause" in capabilities
    assert "roku_volume_up" in capabilities
    assert "roku_home" in capabilities
    assert "roku_launch_app" in capabilities

    await agent.close()


@pytest.mark.asyncio
async def test_handle_capability_request(monkeypatch):
    """Test handling of capability requests."""
    agent = RokuAgent(
        ai_client=DummyAIClient(),
        device_ip="192.168.1.100",
    )

    # Mock the command processor
    async def fake_process(cmd):
        return {
            "response": "Launched Netflix",
            "actions": [
                {"function": "launch_app_by_name", "result": {"success": True}}
            ],
            "iterations": 1,
        }

    monkeypatch.setattr(agent.command_processor, "process_command", fake_process)

    # Mock the send response
    captured = {}

    async def fake_send(to, result, request_id, msg_id):
        captured["result"] = result
        captured["to"] = to
        captured["req"] = request_id

    monkeypatch.setattr(agent, "send_capability_response", fake_send)

    # Create a test message
    message = Message(
        from_agent="tester",
        to_agent="RokuAgent",
        message_type="capability_request",
        content={"capability": "roku_command", "data": {"prompt": "launch netflix"}},
        request_id="test-123",
    )

    # Handle the request
    await agent._handle_capability_request(message)

    # Verify the response
    assert captured["result"]["response"] == "Launched Netflix"
    assert captured["to"] == "tester"
    assert captured["req"] == "test-123"

    await agent.close()


@pytest.mark.asyncio
async def test_function_registry_mapping():
    """Test that function registry maps functions correctly."""
    agent = RokuAgent(
        ai_client=DummyAIClient(),
        device_ip="192.168.1.100",
    )

    # Test that functions are mapped
    registry = agent.function_registry
    assert registry.get_function("play") is not None
    assert registry.get_function("pause") is not None
    assert registry.get_function("home") is not None
    assert registry.get_function("volume_up") is not None
    assert registry.get_function("launch_app_by_name") is not None

    # Test that invalid function returns None
    assert registry.get_function("invalid_function") is None

    await agent.close()


@pytest.mark.asyncio
async def test_roku_service_power_operations(monkeypatch):
    """Test power on/off operations through the service."""
    agent = RokuAgent(
        ai_client=DummyAIClient(),
        device_ip="192.168.1.100",
    )

    # Mock the HTTP client
    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = AsyncMock()

    async def mock_post(url):
        return mock_response

    monkeypatch.setattr(agent.roku_service.client, "post", mock_post)

    # Test power on
    result = await agent.roku_service.power_on()
    assert result["success"] is True
    assert "PowerOn" in result["message"]

    # Test power off
    result = await agent.roku_service.power_off()
    assert result["success"] is True
    assert "PowerOff" in result["message"]

    await agent.close()
