"""Tests for ServerManagerAgent."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest

from jarvis.agents.server_manager_agent import ServerManagerAgent
from jarvis.agents.server_manager_agent.models import (
    ServerConfig,
    ServerMode,
    ServerState,
    ServerStatus,
    RestartPolicy,
)
from jarvis.agents.message import Message
from jarvis.agents.response import AgentResponse


@pytest.fixture
def mock_service():
    """Create a mock ServerManagerService."""
    service = MagicMock()
    service.servers = {}
    service.get_server = MagicMock(return_value=None)
    service.start_server = AsyncMock()
    service.stop_server = AsyncMock()
    service.restart_server = AsyncMock()
    service.start_boot_servers = AsyncMock(return_value=[])
    service.stop_all = AsyncMock()
    service.check_all_health = AsyncMock(return_value=[])
    service.detect_crashes = AsyncMock(return_value=[])
    service.maybe_auto_restart = AsyncMock(return_value=False)
    return service


@pytest.fixture
def agent(mock_service):
    return ServerManagerAgent(server_service=mock_service, monitor_interval=60.0)


@pytest.fixture
def sample_state():
    config = ServerConfig(
        name="test-api",
        mode=ServerMode.MANAGED,
        command=["python", "-m", "http.server"],
        host="localhost",
        port=8080,
        health_endpoint="/health",
    )
    return ServerState(
        config=config,
        status=ServerStatus.RUNNING,
        pid=12345,
    )


# ------------------------------------------------------------------
# Properties
# ------------------------------------------------------------------

class TestProperties:
    def test_name(self, agent):
        assert agent.name == "ServerManagerAgent"

    def test_capabilities(self, agent):
        caps = agent.capabilities
        assert "start_server" in caps
        assert "stop_server" in caps
        assert "restart_server" in caps
        assert "server_status" in caps
        assert "list_servers" in caps

    def test_description(self, agent):
        assert "server" in agent.description.lower()

    def test_supports_dialogue(self, agent):
        assert agent.supports_dialogue is False


# ------------------------------------------------------------------
# Capability handlers
# ------------------------------------------------------------------

class TestStartServer:
    @pytest.mark.asyncio
    async def test_start_success(self, agent, mock_service, sample_state):
        mock_service.start_server.return_value = sample_state
        result = await agent._handle_start_server({"prompt": "test-api"})
        assert result.success is True
        assert "test-api" in result.response
        assert "12345" in result.response
        mock_service.start_server.assert_called_once_with("test-api")

    @pytest.mark.asyncio
    async def test_start_unknown(self, agent, mock_service):
        mock_service.start_server.side_effect = KeyError("Unknown server: ghost")
        result = await agent._handle_start_server({"prompt": "ghost"})
        assert result.success is False
        assert "ghost" in result.response

    @pytest.mark.asyncio
    async def test_start_external_rejected(self, agent, mock_service):
        mock_service.start_server.side_effect = ValueError("Cannot start external server")
        result = await agent._handle_start_server({"prompt": "external-db"})
        assert result.success is False

    @pytest.mark.asyncio
    async def test_start_no_name(self, agent):
        result = await agent._handle_start_server({"prompt": ""})
        assert result.success is False


class TestStopServer:
    @pytest.mark.asyncio
    async def test_stop_success(self, agent, mock_service, sample_state):
        sample_state.status = ServerStatus.STOPPED
        sample_state.pid = None
        sample_state.last_exit_code = 0
        mock_service.stop_server.return_value = sample_state
        result = await agent._handle_stop_server({"prompt": "test-api"})
        assert result.success is True
        assert "stopped" in result.response.lower()

    @pytest.mark.asyncio
    async def test_stop_unknown(self, agent, mock_service):
        mock_service.stop_server.side_effect = KeyError("Unknown server: ghost")
        result = await agent._handle_stop_server({"prompt": "ghost"})
        assert result.success is False

    @pytest.mark.asyncio
    async def test_stop_no_name(self, agent):
        result = await agent._handle_stop_server({"prompt": ""})
        assert result.success is False


class TestRestartServer:
    @pytest.mark.asyncio
    async def test_restart_success(self, agent, mock_service, sample_state):
        mock_service.restart_server.return_value = sample_state
        result = await agent._handle_restart_server({"prompt": "test-api"})
        assert result.success is True
        assert "restarted" in result.response.lower()

    @pytest.mark.asyncio
    async def test_restart_no_name(self, agent):
        result = await agent._handle_restart_server({"prompt": ""})
        assert result.success is False


class TestServerStatus:
    @pytest.mark.asyncio
    async def test_status_found(self, agent, mock_service, sample_state):
        mock_service.get_server.return_value = sample_state
        result = await agent._handle_server_status({"prompt": "test-api"})
        assert result.success is True
        assert "RUNNING" in result.response

    @pytest.mark.asyncio
    async def test_status_not_found(self, agent, mock_service):
        mock_service.get_server.return_value = None
        result = await agent._handle_server_status({"prompt": "ghost"})
        assert result.success is False

    @pytest.mark.asyncio
    async def test_status_no_name(self, agent):
        result = await agent._handle_server_status({"prompt": ""})
        assert result.success is False


class TestListServers:
    @pytest.mark.asyncio
    async def test_list_empty(self, agent, mock_service):
        mock_service.servers = {}
        result = await agent._handle_list_servers({})
        assert result.success is True
        assert "empty" in result.response.lower()

    @pytest.mark.asyncio
    async def test_list_with_servers(self, agent, mock_service, sample_state):
        mock_service.servers = {"test-api": sample_state}
        result = await agent._handle_list_servers({})
        assert result.success is True
        assert "test-api" in result.response
        assert "1 server" in result.response


# ------------------------------------------------------------------
# Health integration
# ------------------------------------------------------------------

class TestHealthIntegration:
    @pytest.mark.asyncio
    async def test_get_health_probes_empty(self, agent):
        probes = await agent.get_health_probes()
        assert probes == []

    @pytest.mark.asyncio
    async def test_get_health_probes_returns_latest(self, agent):
        from jarvis.agents.health_agent.models import ProbeResult, ComponentStatus
        probe = ProbeResult(
            component="server:test-api",
            component_type="service",
            status=ComponentStatus.HEALTHY,
            message="HTTP 200",
        )
        agent._latest_probes = [probe]
        probes = await agent.get_health_probes()
        assert len(probes) == 1
        assert probes[0].component == "server:test-api"


# ------------------------------------------------------------------
# Message routing
# ------------------------------------------------------------------

class TestMessageRouting:
    @pytest.mark.asyncio
    async def test_capability_request_routes_correctly(self, agent, mock_service, sample_state):
        mock_service.servers = {"test-api": sample_state}

        # Mock network for send_capability_response
        mock_network = MagicMock()
        mock_network.send_message = AsyncMock()
        agent.network = mock_network

        message = Message(
            from_agent="Orchestrator",
            to_agent="ServerManagerAgent",
            message_type="capability_request",
            content={
                "capability": "list_servers",
                "data": {},
            },
            request_id="req-123",
        )
        await agent._handle_capability_request(message)
        mock_network.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_unknown_capability_sends_error(self, agent):
        mock_network = MagicMock()
        mock_network.send_message = AsyncMock()
        agent.network = mock_network

        message = Message(
            from_agent="Orchestrator",
            to_agent="ServerManagerAgent",
            message_type="capability_request",
            content={
                "capability": "fly_to_moon",
                "data": {},
            },
            request_id="req-456",
        )
        await agent._handle_capability_request(message)
        # Should have sent an error message
        call_args = mock_network.send_message.call_args[0][0]
        assert call_args.message_type == "error"
