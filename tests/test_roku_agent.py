"""Tests for RokuAgent multi-device refactor.

Covers:
- Initialization with device registry (single and multi-device)
- Backwards-compatible roku_service property
- execute_on_device routing
- execute_on_all broadcast
- Stale IP / offline recovery via rediscovery
- New device management capabilities in the capability set
- Function registry mappings
- Capability request handling
- Power operations through service
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from jarvis.agents.roku_agent import RokuAgent
from jarvis.agents.message import Message
from jarvis.ai_clients.base import BaseAIClient
from jarvis.services.roku_discovery import RokuDeviceInfo, RokuDeviceRegistry


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


class DummyAIClient(BaseAIClient):
    async def strong_chat(self, messages, tools=None):
        return None, None

    async def weak_chat(self, messages, tools=None):
        return None, None


def _make_device(
    serial: str = "TEST001",
    ip: str = "192.168.1.100",
    name: str = "Test Roku",
    model: str = "Roku Ultra",
    online: bool = True,
    friendly: str = "",
) -> RokuDeviceInfo:
    return RokuDeviceInfo(
        serial_number=serial,
        ip_address=ip,
        device_name=name,
        friendly_name=friendly,
        model=model,
        is_online=online,
        last_seen=1000.0,
    )


def _make_registry(*devices: RokuDeviceInfo, default_serial: str = None) -> RokuDeviceRegistry:
    """Build a registry with the given devices, stubbing save() to avoid disk I/O."""
    registry = RokuDeviceRegistry()
    registry.save = MagicMock()  # No disk I/O in tests
    for d in devices:
        registry.devices[d.serial_number] = d
    if default_serial:
        registry.default_serial = default_serial
    elif devices:
        registry.default_serial = devices[0].serial_number
    return registry


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def single_device_registry():
    dev = _make_device()
    return _make_registry(dev, default_serial="TEST001")


@pytest.fixture
def two_device_registry():
    dev1 = _make_device(serial="SER001", ip="192.168.1.10", name="Living Room Roku", friendly="Living Room")
    dev2 = _make_device(serial="SER002", ip="192.168.1.20", name="Bedroom Roku", friendly="Bedroom")
    return _make_registry(dev1, dev2, default_serial="SER001")


# ---------------------------------------------------------------------------
# Initialization tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_roku_agent_initialization(single_device_registry):
    """Agent initialises with a registry and creates a service for the default device."""
    agent = RokuAgent(
        ai_client=DummyAIClient(),
        device_registry=single_device_registry,
    )
    assert agent.device_registry is single_device_registry
    assert agent.roku_service is not None
    assert agent.function_registry is not None
    assert agent.command_processor is not None
    # Service cache should have one entry for the default device
    assert "TEST001" in agent._services
    await agent.close()


@pytest.mark.asyncio
async def test_multi_device_init(two_device_registry):
    """Agent with two devices in registry bootstraps the default and can reach both."""
    agent = RokuAgent(
        ai_client=DummyAIClient(),
        device_registry=two_device_registry,
    )
    # Default device service is created eagerly
    assert "SER001" in agent._services

    # Second device service is created lazily via get_service
    svc2 = agent.get_service("SER002")
    assert svc2 is not None
    assert "SER002" in agent._services
    assert svc2.device_ip == "192.168.1.20"

    await agent.close()


# ---------------------------------------------------------------------------
# Backwards-compat property
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_roku_service_backwards_compat(single_device_registry):
    """The roku_service property returns the default device's service."""
    agent = RokuAgent(
        ai_client=DummyAIClient(),
        device_registry=single_device_registry,
    )
    svc = agent.roku_service
    assert svc is not None
    assert svc.device_ip == "192.168.1.100"
    await agent.close()


# ---------------------------------------------------------------------------
# Service methods still reachable
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_roku_service_methods_exist(single_device_registry):
    """Key service methods are still accessible via the backwards-compat property."""
    agent = RokuAgent(
        ai_client=DummyAIClient(),
        device_registry=single_device_registry,
    )
    svc = agent.roku_service
    assert hasattr(svc, "get_device_info")
    assert hasattr(svc, "list_apps")
    assert hasattr(svc, "launch_app_by_name")
    assert hasattr(svc, "play")
    assert hasattr(svc, "pause")
    assert hasattr(svc, "volume_up")
    assert hasattr(svc, "home")
    await agent.close()


# ---------------------------------------------------------------------------
# Capabilities
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_roku_capabilities(single_device_registry):
    """Agent exposes the expected base capabilities."""
    agent = RokuAgent(
        ai_client=DummyAIClient(),
        device_registry=single_device_registry,
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
async def test_new_capabilities_present(single_device_registry):
    """The four new device management capabilities are registered."""
    agent = RokuAgent(
        ai_client=DummyAIClient(),
        device_registry=single_device_registry,
    )
    caps = agent.capabilities
    assert "roku_list_devices" in caps
    assert "roku_name_device" in caps
    assert "roku_set_default" in caps
    assert "roku_discover_devices" in caps
    await agent.close()


# ---------------------------------------------------------------------------
# Function registry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_function_registry_mapping(single_device_registry):
    """Function registry maps all expected functions including new device management ones."""
    agent = RokuAgent(
        ai_client=DummyAIClient(),
        device_registry=single_device_registry,
    )
    registry = agent.function_registry
    # Standard functions
    assert registry.get_function("play") is not None
    assert registry.get_function("pause") is not None
    assert registry.get_function("home") is not None
    assert registry.get_function("volume_up") is not None
    assert registry.get_function("launch_app_by_name") is not None
    # Device management
    assert registry.get_function("list_devices") is not None
    assert registry.get_function("name_device") is not None
    assert registry.get_function("set_default_device") is not None
    assert registry.get_function("discover_devices") is not None
    # Invalid
    assert registry.get_function("invalid_function") is None
    await agent.close()


# ---------------------------------------------------------------------------
# execute_on_device routing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_on_device_routing(single_device_registry):
    """execute_on_device calls the correct service method and returns the result."""
    agent = RokuAgent(
        ai_client=DummyAIClient(),
        device_registry=single_device_registry,
    )
    # Mock the service method
    mock_result = {"success": True, "message": "Pressed key: Home"}
    svc = agent._services["TEST001"]
    svc.home = AsyncMock(return_value=mock_result)

    result = await agent.execute_on_device("TEST001", "home")
    assert result == mock_result
    svc.home.assert_awaited_once()
    await agent.close()


@pytest.mark.asyncio
async def test_execute_on_device_default_when_serial_empty(single_device_registry):
    """Empty serial resolves to the default device."""
    agent = RokuAgent(
        ai_client=DummyAIClient(),
        device_registry=single_device_registry,
    )
    mock_result = {"success": True, "message": "Pressed key: Play"}
    svc = agent._services["TEST001"]
    svc.play = AsyncMock(return_value=mock_result)

    result = await agent.execute_on_device("", "play")
    assert result["success"] is True
    svc.play.assert_awaited_once()
    await agent.close()


# ---------------------------------------------------------------------------
# execute_on_all broadcast
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_on_all_broadcast(two_device_registry):
    """execute_on_all calls the method on every online device."""
    agent = RokuAgent(
        ai_client=DummyAIClient(),
        device_registry=two_device_registry,
    )
    # Ensure both services exist
    agent.get_service("SER001")
    agent.get_service("SER002")

    svc1 = agent._services["SER001"]
    svc2 = agent._services["SER002"]
    svc1.home = AsyncMock(return_value={"success": True, "message": "Home on SER001"})
    svc2.home = AsyncMock(return_value={"success": True, "message": "Home on SER002"})

    results = await agent.execute_on_all("home")
    assert len(results) == 2
    assert all(r["success"] for r in results)
    svc1.home.assert_awaited_once()
    svc2.home.assert_awaited_once()
    await agent.close()


# ---------------------------------------------------------------------------
# Stale IP / offline recovery
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stale_ip_recovery(single_device_registry):
    """First call fails -> agent marks offline, re-discovers, retries with new IP."""
    agent = RokuAgent(
        ai_client=DummyAIClient(),
        device_registry=single_device_registry,
    )
    svc = agent._services["TEST001"]

    # First call raises ConnectionError
    svc.home = AsyncMock(side_effect=ConnectionError("Connection refused"))

    # Mock discover to mark the device back online with a new IP
    async def mock_discover(timeout=5.0):
        dev = single_device_registry.devices["TEST001"]
        dev.is_online = True
        dev.ip_address = "192.168.1.200"
        return []

    single_device_registry.discover = mock_discover

    # Patch RokuService so the newly-created service (after IP change) has a
    # mocked home() that succeeds, rather than hitting the real network.
    original_ensure = agent._ensure_service

    def patched_ensure(serial, ip):
        service = original_ensure(serial, ip)
        if ip == "192.168.1.200":
            service.home = AsyncMock(
                return_value={"success": True, "message": "Pressed key: Home"}
            )
        return service

    agent._ensure_service = patched_ensure

    result = await agent.execute_on_device("TEST001", "home")
    assert result["success"] is True
    # The service should have been recreated with the new IP
    assert agent._services["TEST001"].device_ip == "192.168.1.200"
    await agent.close()


# ---------------------------------------------------------------------------
# Capability request handling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_capability_request(single_device_registry, monkeypatch):
    """Capability requests are routed through the command processor."""
    agent = RokuAgent(
        ai_client=DummyAIClient(),
        device_registry=single_device_registry,
    )

    async def fake_process(cmd):
        return {
            "response": "Launched Netflix",
            "actions": [
                {"function": "launch_app_by_name", "result": {"success": True}}
            ],
            "iterations": 1,
        }

    monkeypatch.setattr(agent.command_processor, "process_command", fake_process)

    captured = {}

    async def fake_send(to, result, request_id, msg_id):
        captured["result"] = result
        captured["to"] = to
        captured["req"] = request_id

    monkeypatch.setattr(agent, "send_capability_response", fake_send)

    message = Message(
        from_agent="tester",
        to_agent="RokuAgent",
        message_type="capability_request",
        content={"capability": "roku_command", "data": {"prompt": "launch netflix"}},
        request_id="test-123",
    )

    await agent._handle_capability_request(message)

    assert captured["result"]["response"] == "Launched Netflix"
    assert captured["to"] == "tester"
    assert captured["req"] == "test-123"
    await agent.close()


# ---------------------------------------------------------------------------
# Power operations through service
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_roku_service_power_operations(single_device_registry, monkeypatch):
    """Power on/off via the backwards-compat service property still works."""
    agent = RokuAgent(
        ai_client=DummyAIClient(),
        device_registry=single_device_registry,
    )

    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()

    async def mock_post(url):
        return mock_response

    monkeypatch.setattr(agent.roku_service.client, "post", mock_post)

    result = await agent.roku_service.power_on()
    assert result["success"] is True
    assert "PowerOn" in result["message"]

    result = await agent.roku_service.power_off()
    assert result["success"] is True
    assert "PowerOff" in result["message"]

    await agent.close()


# ---------------------------------------------------------------------------
# Close cleans up all services
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_close_cleans_all_services(two_device_registry):
    """close() shuts down every cached service."""
    agent = RokuAgent(
        ai_client=DummyAIClient(),
        device_registry=two_device_registry,
    )
    # Materialise both services
    agent.get_service("SER001")
    agent.get_service("SER002")

    svc1 = agent._services["SER001"]
    svc2 = agent._services["SER002"]
    svc1.close = AsyncMock()
    svc2.close = AsyncMock()

    await agent.close()
    svc1.close.assert_awaited_once()
    svc2.close.assert_awaited_once()
    assert len(agent._services) == 0
