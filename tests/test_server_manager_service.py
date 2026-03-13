"""Tests for ServerManagerService."""

import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from jarvis.agents.server_manager_agent.models import (
    RestartPolicy,
    ServerConfig,
    ServerMode,
    ServerState,
    ServerStatus,
)
from jarvis.services.server_manager_service import ServerManagerService


@pytest.fixture
def tmp_registry(tmp_path):
    """Create a temporary registry file."""
    reg_path = tmp_path / "servers.json"
    reg_path.write_text(json.dumps({"servers": []}, indent=2))
    return str(reg_path)


@pytest.fixture
def sample_config():
    return ServerConfig(
        name="test-api",
        mode=ServerMode.MANAGED,
        command=["python", "-m", "http.server", "9999"],
        host="localhost",
        port=9999,
        health_endpoint="/health",
        health_check_interval=30.0,
        restart_policy=RestartPolicy.ON_FAILURE,
        max_restarts=3,
        start_on_boot=True,
        tags=["core"],
    )


@pytest.fixture
def external_config():
    return ServerConfig(
        name="external-db",
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


# ------------------------------------------------------------------
# Registry tests
# ------------------------------------------------------------------

class TestRegistry:
    def test_load_empty_registry(self, service):
        service.load_registry()
        assert len(service.servers) == 0

    def test_load_missing_file_creates_it(self, tmp_path):
        path = str(tmp_path / "nonexistent" / "servers.json")
        svc = ServerManagerService(registry_path=path)
        svc.load_registry()
        assert Path(path).exists()
        assert len(svc.servers) == 0

    def test_load_populated_registry(self, tmp_registry, sample_config):
        Path(tmp_registry).write_text(json.dumps({
            "servers": [sample_config.to_dict()]
        }))
        svc = ServerManagerService(registry_path=tmp_registry)
        svc.load_registry()
        assert "test-api" in svc.servers
        state = svc.get_server("test-api")
        assert state.config.port == 9999

    def test_register_and_unregister(self, service, sample_config):
        service.register_server(sample_config)
        assert "test-api" in service.servers

        removed = service.unregister_server("test-api")
        assert removed is True
        assert "test-api" not in service.servers

    def test_unregister_unknown(self, service):
        assert service.unregister_server("ghost") is False

    def test_get_servers_by_tag(self, service, sample_config, external_config):
        service.register_server(sample_config)
        service.register_server(external_config)
        core_servers = service.get_servers_by_tag("core")
        assert len(core_servers) == 1
        assert core_servers[0].config.name == "test-api"

    def test_registry_persists_to_disk(self, tmp_registry, sample_config):
        svc = ServerManagerService(registry_path=tmp_registry)
        svc.register_server(sample_config)
        data = json.loads(Path(tmp_registry).read_text())
        assert len(data["servers"]) == 1
        assert data["servers"][0]["name"] == "test-api"


# ------------------------------------------------------------------
# Lifecycle tests
# ------------------------------------------------------------------

class TestLifecycle:
    @pytest.mark.asyncio
    async def test_start_managed_server(self, service, sample_config):
        service.register_server(sample_config)

        mock_proc = AsyncMock()
        mock_proc.pid = 12345
        mock_proc.returncode = None

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            state = await service.start_server("test-api")

        assert state.status == ServerStatus.RUNNING
        assert state.pid == 12345
        assert state.started_at is not None

    @pytest.mark.asyncio
    async def test_start_external_raises(self, service, external_config):
        service.register_server(external_config)
        with pytest.raises(ValueError, match="external"):
            await service.start_server("external-db")

    @pytest.mark.asyncio
    async def test_start_unknown_raises(self, service):
        with pytest.raises(KeyError, match="Unknown"):
            await service.start_server("ghost")

    @pytest.mark.asyncio
    async def test_start_no_command_raises(self, service):
        config = ServerConfig(name="empty", mode=ServerMode.MANAGED, command=[])
        service.register_server(config)
        with pytest.raises(ValueError, match="no command"):
            await service.start_server("empty")

    @pytest.mark.asyncio
    async def test_stop_graceful(self, service, sample_config):
        service.register_server(sample_config)

        mock_proc = AsyncMock()
        mock_proc.pid = 12345
        mock_proc.returncode = None
        mock_proc.terminate = MagicMock()

        async def fake_wait():
            mock_proc.returncode = 0

        mock_proc.wait = fake_wait

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            await service.start_server("test-api")

        state = await service.stop_server("test-api")
        assert state.status == ServerStatus.STOPPED
        assert state.pid is None
        mock_proc.terminate.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_force_kill_on_timeout(self, service, sample_config):
        service.register_server(sample_config)

        mock_proc = AsyncMock()
        mock_proc.pid = 12345
        mock_proc.returncode = None
        mock_proc.terminate = MagicMock()
        mock_proc.kill = MagicMock()

        call_count = 0

        async def slow_wait():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                await asyncio.sleep(999)  # Will be cancelled by timeout
            else:
                mock_proc.returncode = -9

        mock_proc.wait = slow_wait

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            await service.start_server("test-api")

        state = await service.stop_server("test-api", timeout=0.01)
        assert state.status == ServerStatus.STOPPED
        mock_proc.kill.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_external_raises(self, service, external_config):
        service.register_server(external_config)
        with pytest.raises(ValueError, match="external"):
            await service.stop_server("external-db")

    @pytest.mark.asyncio
    async def test_restart(self, service, sample_config):
        service.register_server(sample_config)

        mock_proc = AsyncMock()
        mock_proc.pid = 100
        mock_proc.returncode = None
        mock_proc.terminate = MagicMock()

        async def fake_wait():
            mock_proc.returncode = 0

        mock_proc.wait = fake_wait

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            state = await service.restart_server("test-api")

        assert state.status == ServerStatus.RUNNING

    @pytest.mark.asyncio
    async def test_start_already_running_is_noop(self, service, sample_config):
        service.register_server(sample_config)
        mock_proc = AsyncMock()
        mock_proc.pid = 100
        mock_proc.returncode = None

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            await service.start_server("test-api")
            state = await service.start_server("test-api")

        assert state.status == ServerStatus.RUNNING


# ------------------------------------------------------------------
# Health check tests
# ------------------------------------------------------------------

class TestHealthChecks:
    @pytest.mark.asyncio
    async def test_http_healthy(self, service, sample_config):
        service.register_server(sample_config)
        service._servers["test-api"].status = ServerStatus.RUNNING

        mock_resp = MagicMock()
        mock_resp.status_code = 200

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await service.check_health("test-api")

        assert result.status.value == "healthy"
        assert "HTTP 200" in result.message

    @pytest.mark.asyncio
    async def test_http_unhealthy(self, service, sample_config):
        service.register_server(sample_config)
        service._servers["test-api"].status = ServerStatus.RUNNING

        mock_resp = MagicMock()
        mock_resp.status_code = 500

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await service.check_health("test-api")

        assert result.status.value == "unhealthy"

    @pytest.mark.asyncio
    async def test_http_connection_error(self, service, sample_config):
        service.register_server(sample_config)
        service._servers["test-api"].status = ServerStatus.RUNNING

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=ConnectionError("refused"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await service.check_health("test-api")

        assert result.status.value == "unhealthy"

    @pytest.mark.asyncio
    async def test_tcp_fallback(self, service):
        """Server with port but no health_endpoint uses TCP check."""
        config = ServerConfig(
            name="tcp-only",
            mode=ServerMode.EXTERNAL,
            host="localhost",
            port=9999,
        )
        service.register_server(config)

        with patch("asyncio.open_connection") as mock_conn:
            mock_writer = AsyncMock()
            mock_conn.return_value = (AsyncMock(), mock_writer)

            result = await service.check_health("tcp-only")

        assert result.status.value == "healthy"
        assert "TCP" in result.message

    @pytest.mark.asyncio
    async def test_pid_alive_fallback(self, service):
        """Managed server with no port falls back to PID check."""
        config = ServerConfig(
            name="no-port",
            mode=ServerMode.MANAGED,
            command=["sleep", "100"],
        )
        service.register_server(config)

        mock_proc = AsyncMock()
        mock_proc.pid = 999
        mock_proc.returncode = None
        service._processes["no-port"] = mock_proc
        service._servers["no-port"].status = ServerStatus.RUNNING

        result = await service.check_health("no-port")
        assert result.status.value == "healthy"
        assert "PID" in result.message

    @pytest.mark.asyncio
    async def test_pid_dead_returns_unhealthy(self, service):
        config = ServerConfig(
            name="dead",
            mode=ServerMode.MANAGED,
            command=["sleep", "100"],
        )
        service.register_server(config)

        mock_proc = AsyncMock()
        mock_proc.pid = 999
        mock_proc.returncode = 1
        service._processes["dead"] = mock_proc
        service._servers["dead"].status = ServerStatus.RUNNING

        result = await service.check_health("dead")
        assert result.status.value == "unhealthy"

    @pytest.mark.asyncio
    async def test_unknown_server(self, service):
        result = await service.check_health("ghost")
        assert result.status.value == "unknown"

    @pytest.mark.asyncio
    async def test_check_all_health(self, service, sample_config, external_config):
        service.register_server(sample_config)
        service.register_server(external_config)

        with patch.object(service, "check_health", new_callable=AsyncMock) as mock_check:
            from jarvis.agents.health_agent.models import ProbeResult, ComponentStatus
            mock_check.return_value = ProbeResult(
                component="test",
                component_type="service",
                status=ComponentStatus.HEALTHY,
                message="ok",
            )
            results = await service.check_all_health()

        assert len(results) == 2


# ------------------------------------------------------------------
# Auto-restart tests
# ------------------------------------------------------------------

class TestAutoRestart:
    @pytest.mark.asyncio
    async def test_on_failure_restarts_crashed(self, service, sample_config):
        service.register_server(sample_config)
        service._servers["test-api"].status = ServerStatus.CRASHED

        result = await service.maybe_auto_restart("test-api")
        assert result is True
        assert service._servers["test-api"].restart_count == 1

        # Cancel the timer to avoid background task warnings
        timer = service._restart_timers.get("test-api")
        if timer:
            timer.cancel()

    @pytest.mark.asyncio
    async def test_never_policy_does_not_restart(self, service):
        config = ServerConfig(
            name="no-restart",
            mode=ServerMode.MANAGED,
            command=["echo"],
            restart_policy=RestartPolicy.NEVER,
        )
        service.register_server(config)
        service._servers["no-restart"].status = ServerStatus.CRASHED

        result = await service.maybe_auto_restart("no-restart")
        assert result is False

    @pytest.mark.asyncio
    async def test_max_restarts_exceeded(self, service, sample_config):
        service.register_server(sample_config)
        service._servers["test-api"].status = ServerStatus.CRASHED
        service._servers["test-api"].restart_count = 3  # max_restarts=3

        result = await service.maybe_auto_restart("test-api")
        assert result is False

    @pytest.mark.asyncio
    async def test_external_not_restarted(self, service, external_config):
        service.register_server(external_config)
        result = await service.maybe_auto_restart("external-db")
        assert result is False

    @pytest.mark.asyncio
    async def test_restart_window_resets_counter(self, service, sample_config):
        service.register_server(sample_config)
        state = service._servers["test-api"]
        state.status = ServerStatus.CRASHED
        state.restart_count = 2
        # Pretend it started long ago (beyond restart_window)
        state.started_at = datetime(2020, 1, 1, tzinfo=timezone.utc)

        result = await service.maybe_auto_restart("test-api")
        assert result is True
        # Counter should have been reset to 0 then incremented to 1
        assert state.restart_count == 1

        timer = service._restart_timers.get("test-api")
        if timer:
            timer.cancel()


# ------------------------------------------------------------------
# Boot servers test
# ------------------------------------------------------------------

class TestBootServers:
    @pytest.mark.asyncio
    async def test_start_boot_servers(self, service, sample_config, external_config):
        service.register_server(sample_config)  # start_on_boot=True, MANAGED
        service.register_server(external_config)  # EXTERNAL, should be skipped

        mock_proc = AsyncMock()
        mock_proc.pid = 100
        mock_proc.returncode = None

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            started = await service.start_boot_servers()

        assert started == ["test-api"]
        assert "external-db" not in started


# ------------------------------------------------------------------
# Crash detection tests
# ------------------------------------------------------------------

class TestCrashDetection:
    @pytest.mark.asyncio
    async def test_detect_crash(self, service, sample_config):
        service.register_server(sample_config)
        service._servers["test-api"].status = ServerStatus.RUNNING

        mock_proc = AsyncMock()
        mock_proc.returncode = 1
        service._processes["test-api"] = mock_proc

        crashed = await service.detect_crashes()
        assert "test-api" in crashed
        assert service._servers["test-api"].status == ServerStatus.CRASHED
