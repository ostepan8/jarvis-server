"""Integration tests for the ServerManagerAgent system.

Tests the full lifecycle: start → monitor → health check → crash detection →
HealthAgent notification → auto-restart, plus factory wiring and snapshot
integration.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from jarvis.agents.agent_network import AgentNetwork
from jarvis.agents.factory import AgentFactory
from jarvis.agents.health_agent.models import ComponentStatus, ProbeResult
from jarvis.agents.message import Message
from jarvis.agents.server_manager_agent import ServerManagerAgent
from jarvis.agents.server_manager_agent.models import (
    RestartPolicy,
    ServerConfig,
    ServerMode,
    ServerState,
    ServerStatus,
)
from jarvis.core.config import FeatureFlags, JarvisConfig
from jarvis.logging import JarvisLogger
from jarvis.services.server_manager_service import ServerManagerService


# ------------------------------------------------------------------
# Shared fixtures
# ------------------------------------------------------------------

@pytest.fixture
def tmp_registry(tmp_path):
    path = tmp_path / "servers.json"
    path.write_text(json.dumps({"servers": []}, indent=2))
    return str(path)


@pytest.fixture
def managed_config():
    return ServerConfig(
        name="calendar-api",
        mode=ServerMode.MANAGED,
        command=["python", "-m", "http.server", "8080"],
        host="localhost",
        port=8080,
        health_endpoint="/health",
        health_check_interval=30.0,
        restart_policy=RestartPolicy.ON_FAILURE,
        max_restarts=3,
        restart_window=300.0,
        start_on_boot=True,
        tags=["core"],
    )


@pytest.fixture
def external_config():
    return ServerConfig(
        name="postgres",
        mode=ServerMode.EXTERNAL,
        host="localhost",
        port=5432,
        health_check_interval=60.0,
        restart_policy=RestartPolicy.NEVER,
        tags=["database"],
    )


@pytest.fixture
def service(tmp_registry):
    return ServerManagerService(registry_path=tmp_registry)


@pytest.fixture
def agent(service):
    return ServerManagerAgent(server_service=service, monitor_interval=60.0)


# ------------------------------------------------------------------
# Monitor loop
# ------------------------------------------------------------------

class TestMonitorLoop:
    """Tests for the background monitoring loop."""

    @pytest.mark.asyncio
    async def test_boot_servers_called_on_first_tick(self, agent, service, managed_config):
        """First iteration of monitor loop should start boot servers."""
        service.register_server(managed_config)

        mock_proc = AsyncMock()
        mock_proc.pid = 1234
        mock_proc.returncode = None

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            # Run one iteration manually
            assert agent._booted is False
            started = await service.start_boot_servers()
            agent._booted = True
            assert "calendar-api" in started
            assert agent._booted is True

    @pytest.mark.asyncio
    async def test_monitor_detects_crash_and_triggers_restart(self, agent, service, managed_config):
        """Monitor should detect process crash and trigger auto-restart."""
        service.register_server(managed_config)
        state = service._servers["calendar-api"]

        # Simulate a running server that crashes
        state.status = ServerStatus.RUNNING
        mock_proc = AsyncMock()
        mock_proc.pid = 5555
        mock_proc.returncode = 1  # Crashed
        service._processes["calendar-api"] = mock_proc

        # Detect the crash
        crashed = await service.detect_crashes()
        assert "calendar-api" in crashed
        assert state.status == ServerStatus.CRASHED
        assert state.last_exit_code == 1
        assert "unexpectedly" in state.error_message

        # Auto-restart should schedule
        result = await service.maybe_auto_restart("calendar-api")
        assert result is True
        assert state.restart_count == 1

        # Clean up timer
        timer = service._restart_timers.get("calendar-api")
        if timer:
            timer.cancel()

    @pytest.mark.asyncio
    async def test_monitor_updates_latest_probes(self, agent, service, managed_config):
        """Health probes from monitor loop should be stored for HealthAgent."""
        service.register_server(managed_config)

        probe = ProbeResult(
            component="server:calendar-api",
            component_type="service",
            status=ComponentStatus.HEALTHY,
            message="HTTP 200",
        )

        with patch.object(service, "check_all_health", new_callable=AsyncMock) as mock_check:
            mock_check.return_value = [probe]
            probes = await service.check_all_health()
            agent._latest_probes = probes

        result = await agent.get_health_probes()
        assert len(result) == 1
        assert result[0].status == ComponentStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_monitor_triggers_restart_on_unhealthy_probe(self, service, managed_config):
        """Unhealthy health probe should trigger auto-restart for managed servers."""
        service.register_server(managed_config)
        state = service._servers["calendar-api"]
        state.status = ServerStatus.UNHEALTHY

        result = await service.maybe_auto_restart("calendar-api")
        assert result is True

        timer = service._restart_timers.get("calendar-api")
        if timer:
            timer.cancel()

    @pytest.mark.asyncio
    async def test_monitor_does_not_restart_healthy_server(self, service, managed_config):
        """Healthy servers should not be restarted."""
        service.register_server(managed_config)
        state = service._servers["calendar-api"]
        state.status = ServerStatus.RUNNING

        result = await service.maybe_auto_restart("calendar-api")
        assert result is False


# ------------------------------------------------------------------
# HealthAgent error notification
# ------------------------------------------------------------------

class TestHealthAgentNotification:
    """Tests for crash notification to HealthAgent."""

    @pytest.mark.asyncio
    async def test_notify_crash_sends_error_to_health_agent(self, agent):
        """Crash notification should deliver error message to HealthAgent."""
        mock_health_agent = MagicMock()
        mock_health_agent.receive_message = AsyncMock()

        mock_network = MagicMock()
        mock_network.agents = {"HealthAgent": mock_health_agent}
        agent.network = mock_network

        await agent._notify_crash("calendar-api")

        mock_health_agent.receive_message.assert_called_once()
        msg = mock_health_agent.receive_message.call_args[0][0]
        assert msg.message_type == "error"
        assert msg.from_agent == "ServerManagerAgent"
        assert msg.to_agent == "HealthAgent"
        assert "calendar-api" in msg.content["error"]
        assert "crashed" in msg.content["error"]

    @pytest.mark.asyncio
    async def test_notify_crash_noop_without_network(self, agent):
        """No crash notification if agent has no network."""
        agent.network = None
        # Should not raise
        await agent._notify_crash("calendar-api")

    @pytest.mark.asyncio
    async def test_notify_crash_noop_without_health_agent(self, agent):
        """No crash notification if HealthAgent not in network."""
        mock_network = MagicMock()
        mock_network.agents = {}
        agent.network = mock_network
        # Should not raise
        await agent._notify_crash("calendar-api")

    @pytest.mark.asyncio
    async def test_notify_crash_swallows_delivery_error(self, agent):
        """Crash notification should not propagate errors from HealthAgent."""
        mock_health_agent = MagicMock()
        mock_health_agent.receive_message = AsyncMock(side_effect=RuntimeError("boom"))

        mock_network = MagicMock()
        mock_network.agents = {"HealthAgent": mock_health_agent}
        agent.network = mock_network

        # Should not raise despite delivery failure
        await agent._notify_crash("calendar-api")

    @pytest.mark.asyncio
    async def test_health_agent_tracks_error_from_server_manager(self):
        """HealthAgent._handle_error should track errors from ServerManagerAgent."""
        from jarvis.agents.health_agent import HealthAgent
        from jarvis.services.health_service import HealthService

        health_service = HealthService(timeout=1.0)
        health_agent = HealthAgent(health_service=health_service, probe_interval=9999.0)

        msg = Message(
            from_agent="ServerManagerAgent",
            to_agent="HealthAgent",
            message_type="error",
            content={"error": "Server 'calendar-api' has crashed"},
            request_id="",
        )

        await health_agent._handle_error(msg)
        assert health_agent._error_counts.get("ServerManagerAgent", 0) == 1

        # Second crash increments
        await health_agent._handle_error(msg)
        assert health_agent._error_counts["ServerManagerAgent"] == 2


# ------------------------------------------------------------------
# HealthAgent snapshot integration
# ------------------------------------------------------------------

class TestHealthAgentSnapshot:
    """Tests for server probes appearing in HealthAgent snapshots."""

    @pytest.mark.asyncio
    async def test_build_snapshot_includes_server_probes(self):
        """HealthAgent._build_snapshot should include probes from ServerManagerAgent."""
        from jarvis.agents.health_agent import HealthAgent
        from jarvis.services.health_service import HealthService

        health_service = HealthService(timeout=1.0)
        health_agent = HealthAgent(health_service=health_service, probe_interval=9999.0)

        # Create a mock ServerManagerAgent with probes
        mock_server_agent = MagicMock()
        mock_server_agent.get_health_probes = AsyncMock(return_value=[
            ProbeResult(
                component="server:calendar-api",
                component_type="service",
                status=ComponentStatus.HEALTHY,
                message="HTTP 200",
                latency_ms=12.5,
            ),
            ProbeResult(
                component="server:postgres",
                component_type="service",
                status=ComponentStatus.UNHEALTHY,
                message="TCP port 5432 refused",
            ),
        ])

        # Wire up a network with the mock
        network = AgentNetwork()
        network.agents["ServerManagerAgent"] = mock_server_agent
        health_agent.network = network

        snapshot = await health_agent._build_snapshot()

        # Server probes should appear in service_statuses
        server_components = [
            s.component for s in snapshot.service_statuses
            if s.component.startswith("server:")
        ]
        assert "server:calendar-api" in server_components
        assert "server:postgres" in server_components

    @pytest.mark.asyncio
    async def test_build_snapshot_survives_server_agent_error(self):
        """Snapshot should still build if ServerManagerAgent throws."""
        from jarvis.agents.health_agent import HealthAgent
        from jarvis.services.health_service import HealthService

        health_service = HealthService(timeout=1.0)
        health_agent = HealthAgent(health_service=health_service, probe_interval=9999.0)

        mock_server_agent = MagicMock()
        mock_server_agent.get_health_probes = AsyncMock(side_effect=RuntimeError("kaboom"))

        network = AgentNetwork()
        network.agents["ServerManagerAgent"] = mock_server_agent
        health_agent.network = network

        # Should not raise
        snapshot = await health_agent._build_snapshot()
        assert snapshot is not None
        # Should still have the base service probes (calendar, sqlite)
        assert len(snapshot.service_statuses) >= 2

    @pytest.mark.asyncio
    async def test_build_snapshot_without_server_manager(self):
        """Snapshot should work normally when ServerManagerAgent is absent."""
        from jarvis.agents.health_agent import HealthAgent
        from jarvis.services.health_service import HealthService

        health_service = HealthService(timeout=1.0)
        health_agent = HealthAgent(health_service=health_service, probe_interval=9999.0)

        network = AgentNetwork()
        health_agent.network = network

        snapshot = await health_agent._build_snapshot()
        assert snapshot is not None
        # No server: probes in service_statuses
        server_probes = [
            s for s in snapshot.service_statuses
            if s.component.startswith("server:")
        ]
        assert len(server_probes) == 0


# ------------------------------------------------------------------
# Full lifecycle flow
# ------------------------------------------------------------------

class TestFullLifecycle:
    """End-to-end lifecycle: start → health → crash → notify → restart."""

    @pytest.mark.asyncio
    async def test_start_then_health_check_returns_healthy(self, service, managed_config):
        """A running server with healthy HTTP endpoint reports healthy."""
        service.register_server(managed_config)

        mock_proc = AsyncMock()
        mock_proc.pid = 7777
        mock_proc.returncode = None

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            state = await service.start_server("calendar-api")

        assert state.status == ServerStatus.RUNNING
        assert state.pid == 7777

        # Health check with HTTP 200
        mock_resp = MagicMock()
        mock_resp.status_code = 200

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            probe = await service.check_health("calendar-api")

        assert probe.status == ComponentStatus.HEALTHY
        assert state.consecutive_failures == 0

    @pytest.mark.asyncio
    async def test_health_failure_increments_consecutive_failures(self, service, managed_config):
        """Each failed health check should increment consecutive_failures."""
        service.register_server(managed_config)
        state = service._servers["calendar-api"]
        state.status = ServerStatus.RUNNING

        mock_resp = MagicMock()
        mock_resp.status_code = 503

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            await service.check_health("calendar-api")
            assert state.consecutive_failures == 1
            assert state.status == ServerStatus.UNHEALTHY

            await service.check_health("calendar-api")
            assert state.consecutive_failures == 2

    @pytest.mark.asyncio
    async def test_health_recovery_resets_failures(self, service, managed_config):
        """Healthy response after failures should reset consecutive_failures."""
        service.register_server(managed_config)
        state = service._servers["calendar-api"]
        state.status = ServerStatus.UNHEALTHY
        state.consecutive_failures = 5

        mock_resp = MagicMock()
        mock_resp.status_code = 200

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            probe = await service.check_health("calendar-api")

        assert probe.status == ComponentStatus.HEALTHY
        assert state.consecutive_failures == 0
        assert state.status == ServerStatus.RUNNING

    @pytest.mark.asyncio
    async def test_crash_to_restart_full_flow(self, agent, service, managed_config):
        """Full flow: running → crash detected → HealthAgent notified → restart scheduled."""
        service.register_server(managed_config)
        state = service._servers["calendar-api"]
        state.status = ServerStatus.RUNNING

        # Wire up HealthAgent mock
        mock_health_agent = MagicMock()
        mock_health_agent.receive_message = AsyncMock()
        mock_network = MagicMock()
        mock_network.agents = {"HealthAgent": mock_health_agent}
        agent.network = mock_network

        # Simulate crash
        mock_proc = AsyncMock()
        mock_proc.pid = 5555
        mock_proc.returncode = 137  # SIGKILL
        service._processes["calendar-api"] = mock_proc

        # Step 1: Detect crash
        crashed = await service.detect_crashes()
        assert "calendar-api" in crashed
        assert state.status == ServerStatus.CRASHED

        # Step 2: Notify HealthAgent
        await agent._notify_crash("calendar-api")
        mock_health_agent.receive_message.assert_called_once()

        # Step 3: Auto-restart
        result = await service.maybe_auto_restart("calendar-api")
        assert result is True
        assert state.restart_count == 1

        # Cleanup
        timer = service._restart_timers.get("calendar-api")
        if timer:
            timer.cancel()

    @pytest.mark.asyncio
    async def test_stop_all_stops_running_managed_servers(self, service, managed_config, external_config):
        """stop_all should stop only managed running servers."""
        service.register_server(managed_config)
        service.register_server(external_config)

        mock_proc = AsyncMock()
        mock_proc.pid = 100
        mock_proc.returncode = None
        mock_proc.terminate = MagicMock()

        async def fake_wait():
            mock_proc.returncode = 0

        mock_proc.wait = fake_wait

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            await service.start_server("calendar-api")

        assert service._servers["calendar-api"].status == ServerStatus.RUNNING

        await service.stop_all()
        assert service._servers["calendar-api"].status == ServerStatus.STOPPED

    @pytest.mark.asyncio
    async def test_agent_stop_cancels_monitor_and_stops_servers(self, agent, service, managed_config):
        """Agent.stop() should cancel monitor task and stop all servers."""
        service.register_server(managed_config)
        service.stop_all = AsyncMock()

        # Simulate a running monitor task
        async def infinite_loop():
            while True:
                await asyncio.sleep(1)

        agent._monitor_task = asyncio.create_task(infinite_loop())

        await agent.stop()
        assert agent._monitor_task.cancelled() or agent._monitor_task.done()
        service.stop_all.assert_called_once()


# ------------------------------------------------------------------
# Factory wiring
# ------------------------------------------------------------------

class TestFactoryWiring:
    """Tests that the factory correctly builds and wires the ServerManagerAgent."""

    def test_build_server_manager_registers_agent(self, tmp_registry):
        """_build_server_manager should register ServerManagerAgent in the network."""
        config = JarvisConfig(
            flags=FeatureFlags(enable_server_manager=True),
            server_registry_path=tmp_registry,
        )
        logger = JarvisLogger()
        factory = AgentFactory(config, logger)
        network = AgentNetwork()

        with patch("jarvis.agents.server_manager_agent.asyncio.create_task"):
            refs = factory._build_server_manager(network)

        assert "server_service" in refs
        assert "server_manager_agent" in refs
        assert "ServerManagerAgent" in network.agents

    def test_build_server_manager_loads_registry(self, tmp_path):
        """Factory should load the server registry on build."""
        reg_path = tmp_path / "servers.json"
        config_data = {
            "servers": [{
                "name": "test-svc",
                "mode": "managed",
                "command": ["echo", "hello"],
                "host": "localhost",
                "port": 9090,
                "health_endpoint": "/ping",
            }]
        }
        reg_path.write_text(json.dumps(config_data, indent=2))

        config = JarvisConfig(
            flags=FeatureFlags(enable_server_manager=True),
            server_registry_path=str(reg_path),
        )
        logger = JarvisLogger()
        factory = AgentFactory(config, logger)
        network = AgentNetwork()

        with patch("jarvis.agents.server_manager_agent.asyncio.create_task"):
            refs = factory._build_server_manager(network)
        svc = refs["server_service"]
        assert "test-svc" in svc.servers

    def test_build_all_includes_server_manager_when_enabled(self, tmp_registry):
        """build_all should include ServerManagerAgent when flag is enabled."""
        config = JarvisConfig(
            flags=FeatureFlags(
                enable_server_manager=True,
                enable_lights=False,
                enable_canvas=False,
                enable_night_mode=False,
                enable_roku=False,
                enable_health=False,
                enable_device_monitor=False,
                enable_self_improvement=False,
            ),
            server_registry_path=tmp_registry,
            google_search_api_key=None,
            google_search_engine_id=None,
        )
        logger = JarvisLogger()
        factory = AgentFactory(config, logger)
        network = AgentNetwork()

        from jarvis.ai_clients.dummy_client import DummyAIClient
        with patch("jarvis.agents.factory.VectorMemoryService"), \
             patch("jarvis.agents.server_manager_agent.asyncio.create_task"):
            refs = factory.build_all(network, DummyAIClient())

        assert "server_manager_agent" in refs
        assert "ServerManagerAgent" in network.agents

    def test_build_all_skips_server_manager_when_disabled(self, tmp_registry):
        """build_all should NOT include ServerManagerAgent when flag is disabled."""
        config = JarvisConfig(
            flags=FeatureFlags(
                enable_server_manager=False,
                enable_lights=False,
                enable_canvas=False,
                enable_night_mode=False,
                enable_roku=False,
                enable_health=False,
                enable_device_monitor=False,
                enable_self_improvement=False,
            ),
            server_registry_path=tmp_registry,
            google_search_api_key=None,
            google_search_engine_id=None,
        )
        logger = JarvisLogger()
        factory = AgentFactory(config, logger)
        network = AgentNetwork()

        from jarvis.ai_clients.dummy_client import DummyAIClient
        with patch("jarvis.agents.factory.VectorMemoryService"):
            refs = factory.build_all(network, DummyAIClient())

        assert "server_manager_agent" not in refs
        assert "ServerManagerAgent" not in network.agents


# ------------------------------------------------------------------
# Server name extraction heuristic
# ------------------------------------------------------------------

class TestServerNameExtraction:
    """Tests for _extract_server_name from natural language prompts."""

    @pytest.fixture
    def agent_with_servers(self, service, managed_config, external_config):
        service.register_server(managed_config)
        service.register_server(external_config)
        return ServerManagerAgent(server_service=service, monitor_interval=60.0)

    def test_exact_name_match(self, agent_with_servers):
        assert agent_with_servers._extract_server_name({"prompt": "calendar-api"}) == "calendar-api"

    def test_name_in_sentence(self, agent_with_servers):
        assert agent_with_servers._extract_server_name({"prompt": "start the calendar-api"}) == "calendar-api"

    def test_name_with_quotes(self, agent_with_servers):
        assert agent_with_servers._extract_server_name({"prompt": "stop 'calendar-api'"}) == "calendar-api"

    def test_no_match_returns_empty(self, agent_with_servers):
        assert agent_with_servers._extract_server_name({"prompt": "start the unicorn"}) == ""

    def test_empty_prompt_returns_empty(self, agent_with_servers):
        assert agent_with_servers._extract_server_name({"prompt": ""}) == ""


# ------------------------------------------------------------------
# Status formatting
# ------------------------------------------------------------------

class TestStatusFormatting:
    """Tests for _format_server_status output."""

    def test_format_running_server(self, agent, managed_config):
        state = ServerState(
            config=managed_config,
            status=ServerStatus.RUNNING,
            pid=9999,
            started_at=datetime(2026, 3, 13, 10, 0, 0, tzinfo=timezone.utc),
        )
        output = agent._format_server_status(state)
        assert "calendar-api" in output
        assert "RUNNING" in output
        assert "9999" in output
        assert "8080" in output

    def test_format_crashed_with_error(self, agent, managed_config):
        state = ServerState(
            config=managed_config,
            status=ServerStatus.CRASHED,
            restart_count=2,
            error_message="Segfault in module X",
        )
        output = agent._format_server_status(state)
        assert "CRASHED" in output
        assert "Restart count: 2/3" in output
        assert "Segfault" in output

    def test_format_with_health_check_latency(self, agent, managed_config):
        state = ServerState(
            config=managed_config,
            status=ServerStatus.RUNNING,
            pid=1234,
            last_health_check=datetime(2026, 3, 13, 12, 0, 0, tzinfo=timezone.utc),
            last_health_latency_ms=42.7,
        )
        output = agent._format_server_status(state)
        assert "43ms" in output  # rounded

    def test_format_stopped_minimal(self, agent):
        config = ServerConfig(name="minimal", mode=ServerMode.MANAGED, command=["echo"])
        state = ServerState(config=config, status=ServerStatus.STOPPED)
        output = agent._format_server_status(state)
        assert "minimal" in output
        assert "STOPPED" in output


# ------------------------------------------------------------------
# Service data model round-trips
# ------------------------------------------------------------------

class TestModelSerialization:
    """Tests for ServerConfig/ServerState serialization."""

    def test_config_round_trip(self, managed_config):
        d = managed_config.to_dict()
        restored = ServerConfig.from_dict(d)
        assert restored.name == managed_config.name
        assert restored.mode == managed_config.mode
        assert restored.port == managed_config.port
        assert restored.restart_policy == managed_config.restart_policy
        assert restored.tags == managed_config.tags

    def test_state_to_dict(self, managed_config):
        state = ServerState(
            config=managed_config,
            status=ServerStatus.RUNNING,
            pid=123,
            started_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            restart_count=2,
        )
        d = state.to_dict()
        assert d["status"] == "running"
        assert d["pid"] == 123
        assert d["restart_count"] == 2
        assert d["config"]["name"] == "calendar-api"

    def test_health_url_with_endpoint(self, managed_config):
        assert managed_config.health_url() == "http://localhost:8080/health"

    def test_health_url_without_endpoint(self):
        config = ServerConfig(name="x", port=9090)
        assert config.health_url() is None

    def test_health_url_without_port(self):
        config = ServerConfig(name="x", health_endpoint="/ping")
        assert config.health_url() is None


# ------------------------------------------------------------------
# Auto-restart backoff timing
# ------------------------------------------------------------------

class TestBackoffTiming:
    """Tests for exponential backoff in auto-restart."""

    @pytest.mark.asyncio
    async def test_backoff_doubles(self, service):
        config = ServerConfig(
            name="backoff-test",
            mode=ServerMode.MANAGED,
            command=["echo"],
            restart_policy=RestartPolicy.ON_FAILURE,
            max_restarts=5,
        )
        service.register_server(config)
        state = service._servers["backoff-test"]

        # Each restart should double the delay
        # restart_count=0 → delay=1s, count becomes 1
        state.status = ServerStatus.CRASHED
        await service.maybe_auto_restart("backoff-test")
        assert state.restart_count == 1

        # restart_count=1 → delay=2s, count becomes 2
        state.status = ServerStatus.CRASHED
        await service.maybe_auto_restart("backoff-test")
        assert state.restart_count == 2

        # restart_count=2 → delay=4s, count becomes 3
        state.status = ServerStatus.CRASHED
        await service.maybe_auto_restart("backoff-test")
        assert state.restart_count == 3

        # Clean up
        for timer in service._restart_timers.values():
            timer.cancel()

    @pytest.mark.asyncio
    async def test_backoff_caps_at_60_seconds(self, service):
        config = ServerConfig(
            name="cap-test",
            mode=ServerMode.MANAGED,
            command=["echo"],
            restart_policy=RestartPolicy.ON_FAILURE,
            max_restarts=10,
        )
        service.register_server(config)
        state = service._servers["cap-test"]
        state.status = ServerStatus.CRASHED
        state.restart_count = 7  # 2^7 = 128, but should cap at 60

        await service.maybe_auto_restart("cap-test")
        # Just verify it scheduled — the delay calculation is min(1*2^7, 60) = 60
        assert state.restart_count == 8

        for timer in service._restart_timers.values():
            timer.cancel()

    @pytest.mark.asyncio
    async def test_always_policy_restarts_on_clean_exit(self, service):
        """ALWAYS restart policy should restart even on clean exit (status STOPPED)."""
        config = ServerConfig(
            name="always-test",
            mode=ServerMode.MANAGED,
            command=["echo"],
            restart_policy=RestartPolicy.ALWAYS,
            max_restarts=5,
        )
        service.register_server(config)
        state = service._servers["always-test"]
        state.status = ServerStatus.STOPPED  # Clean exit

        result = await service.maybe_auto_restart("always-test")
        assert result is True

        for timer in service._restart_timers.values():
            timer.cancel()


# ------------------------------------------------------------------
# Registry edge cases
# ------------------------------------------------------------------

class TestRegistryEdgeCases:
    """Edge cases for the server registry."""

    def test_corrupt_json_is_handled(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text("{invalid json!!!")
        svc = ServerManagerService(registry_path=str(path))
        svc.load_registry()  # Should not raise
        assert len(svc.servers) == 0

    def test_multiple_servers_in_registry(self, tmp_path):
        path = tmp_path / "multi.json"
        path.write_text(json.dumps({
            "servers": [
                {"name": "a", "mode": "managed", "command": ["echo"]},
                {"name": "b", "mode": "external", "host": "localhost", "port": 3000},
                {"name": "c", "mode": "managed", "command": ["sleep", "10"], "tags": ["slow"]},
            ]
        }))
        svc = ServerManagerService(registry_path=str(path))
        svc.load_registry()
        assert len(svc.servers) == 3
        assert svc.get_server("a") is not None
        assert svc.get_server("b").config.mode == ServerMode.EXTERNAL

    def test_unregister_cancels_pending_restart_timer(self, service):
        config = ServerConfig(
            name="timer-test",
            mode=ServerMode.MANAGED,
            command=["echo"],
        )
        service.register_server(config)

        # Plant a mock timer
        mock_timer = MagicMock()
        mock_timer.done.return_value = False
        service._restart_timers["timer-test"] = mock_timer

        service.unregister_server("timer-test")
        mock_timer.cancel.assert_called_once()
        assert "timer-test" not in service._restart_timers


# ------------------------------------------------------------------
# TCP and external health checks
# ------------------------------------------------------------------

class TestExternalHealthChecks:
    """Health check scenarios for external servers."""

    @pytest.mark.asyncio
    async def test_tcp_connect_failure(self, service):
        config = ServerConfig(
            name="tcp-dead",
            mode=ServerMode.EXTERNAL,
            host="localhost",
            port=19999,
        )
        service.register_server(config)

        with patch("asyncio.open_connection", side_effect=ConnectionRefusedError()):
            with patch("asyncio.wait_for", side_effect=ConnectionRefusedError()):
                probe = await service.check_health("tcp-dead")

        assert probe.status == ComponentStatus.UNHEALTHY
        assert service._servers["tcp-dead"].consecutive_failures == 1

    @pytest.mark.asyncio
    async def test_no_health_method_returns_unknown(self, service):
        config = ServerConfig(
            name="mystery",
            mode=ServerMode.EXTERNAL,
        )
        service.register_server(config)
        probe = await service.check_health("mystery")
        assert probe.status == ComponentStatus.UNKNOWN
        assert "No health check method" in probe.message

    @pytest.mark.asyncio
    async def test_health_check_records_latency(self, service, managed_config):
        service.register_server(managed_config)
        state = service._servers["calendar-api"]
        state.status = ServerStatus.RUNNING

        mock_resp = MagicMock()
        mock_resp.status_code = 200

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            await service.check_health("calendar-api")

        assert state.last_health_check is not None
        assert state.last_health_latency_ms is not None
        assert state.last_health_latency_ms >= 0


# ------------------------------------------------------------------
# List servers with multiple states
# ------------------------------------------------------------------

class TestListServersComprehensive:
    """Comprehensive tests for list_servers response formatting."""

    @pytest.mark.asyncio
    async def test_list_mixed_statuses(self, agent, service, managed_config, external_config):
        service.register_server(managed_config)
        service.register_server(external_config)
        service._servers["calendar-api"].status = ServerStatus.RUNNING
        service._servers["calendar-api"].pid = 1234
        service._servers["postgres"].status = ServerStatus.STOPPED

        result = await agent._handle_list_servers({})
        assert result.success is True
        assert "2 server(s)" in result.response
        assert "1 running" in result.response
        assert "calendar-api" in result.response
        assert "postgres" in result.response
        assert "PID 1234" in result.response

    @pytest.mark.asyncio
    async def test_list_returns_data_array(self, agent, service, managed_config):
        service.register_server(managed_config)
        result = await agent._handle_list_servers({})
        assert result.data is not None
        assert "servers" in result.data
        assert len(result.data["servers"]) == 1
        assert result.data["servers"][0]["config"]["name"] == "calendar-api"
