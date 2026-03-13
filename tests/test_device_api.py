"""Tests for device monitoring API router."""
from __future__ import annotations

import sys
import types
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from httpx import ASGITransport


# ---------------------------------------------------------------------------
# Module-level stubs — device_monitor_agent and device_monitor_service may
# live on a different worktree branch and not be importable here.  We inject
# lightweight stand-ins so that the router module can import without error.
# ---------------------------------------------------------------------------

def _ensure_device_modules():
    """Inject stub modules for device_monitor_agent/service if not importable."""
    svc_mod_name = "jarvis.services.device_monitor_service"
    agent_mod_name = "jarvis.agents.device_monitor_agent"

    if svc_mod_name not in sys.modules:
        svc_mod = types.ModuleType(svc_mod_name)

        class Severity:
            OK = "ok"
            WARNING = "warning"
            CRITICAL = "critical"
            def __init__(self, v="ok"):
                self.value = v

        class Metric:
            def __init__(self, name="", value=0, unit="", severity=None, details=None):
                self.name = name
                self.value = value
                self.unit = unit
                self.severity = severity or SimpleNamespace(value="ok")
                self.details = details or {}

        class DeviceSnapshot:
            def __init__(self, **kwargs):
                self.hostname = kwargs.get("hostname", "")
                self.platform = kwargs.get("platform", "")
                self.uptime_seconds = kwargs.get("uptime_seconds", 0.0)
                self.cpu = kwargs.get("cpu", [])
                self.memory = kwargs.get("memory", [])
                self.disk = kwargs.get("disk", [])
                self.battery = kwargs.get("battery", None)
                self.thermals = kwargs.get("thermals", [])
                self.network = kwargs.get("network", [])
                self.overall_severity = kwargs.get(
                    "overall_severity", SimpleNamespace(value="ok")
                )

            def to_dict(self):
                def _m(m):
                    return {
                        "name": m.name, "value": m.value, "unit": m.unit,
                        "severity": m.severity.value, "details": m.details,
                    }
                return {
                    "hostname": self.hostname,
                    "platform": self.platform,
                    "uptime_seconds": self.uptime_seconds,
                    "cpu": [_m(c) for c in self.cpu],
                    "memory": [_m(m) for m in self.memory],
                    "disk": [_m(d) for d in self.disk],
                    "battery": _m(self.battery) if self.battery else None,
                    "thermals": [_m(t) for t in self.thermals],
                    "network": [_m(n) for n in self.network],
                    "overall_severity": self.overall_severity.value,
                }

        class DeviceMonitorService:
            pass

        svc_mod.Severity = Severity
        svc_mod.Metric = Metric
        svc_mod.DeviceSnapshot = DeviceSnapshot
        svc_mod.DeviceMonitorService = DeviceMonitorService
        sys.modules[svc_mod_name] = svc_mod

    if agent_mod_name not in sys.modules:
        agent_mod = types.ModuleType(agent_mod_name)

        class DeviceMonitorAgent:
            pass

        agent_mod.DeviceMonitorAgent = DeviceMonitorAgent
        sys.modules[agent_mod_name] = agent_mod


_ensure_device_modules()

# Now safe to import the router
from server.routers.device import router  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_test_app():
    """Create a minimal FastAPI app with the device router."""
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(router, prefix="/device")
    return app


def _make_snapshot(**overrides):
    """Build a DeviceSnapshot-like object for testing."""
    svc_mod = sys.modules["jarvis.services.device_monitor_service"]
    defaults = dict(
        hostname="test-host",
        platform="Darwin 23.4.0",
        uptime_seconds=86400.0,
        overall_severity=SimpleNamespace(value="ok"),
        cpu=[svc_mod.Metric("cpu_overall", 25.0, unit="%",
                            details={"core_count": 8})],
        memory=[svc_mod.Metric("ram", 55.0, unit="%",
                               details={"total_gb": 32, "available_gb": 14.4})],
        disk=[svc_mod.Metric("/", 60.0, unit="%",
                             details={"total_gb": 500, "free_gb": 200,
                                      "fstype": "apfs"})],
    )
    defaults.update(overrides)
    return svc_mod.DeviceSnapshot(**defaults)


def _app_without_agent():
    """App + httpx transport where the agent is absent."""
    app = _make_test_app()
    mock_system = MagicMock()
    mock_system.network.agents = {}

    from server.dependencies import get_jarvis
    app.dependency_overrides[get_jarvis] = lambda: mock_system

    transport = ASGITransport(app=app)
    return transport


def _app_with_agent():
    """App + httpx transport with a mock DeviceMonitorAgent."""
    agent_cls = sys.modules["jarvis.agents.device_monitor_agent"].DeviceMonitorAgent
    agent = MagicMock(spec=agent_cls)

    snap = _make_snapshot()
    agent.device_service = MagicMock()
    agent.device_service.snapshot.return_value = snap

    app = _make_test_app()
    mock_system = MagicMock()
    mock_system.network.agents = {"DeviceMonitorAgent": agent}

    from server.dependencies import get_jarvis
    app.dependency_overrides[get_jarvis] = lambda: mock_system

    transport = ASGITransport(app=app)
    return transport, agent, snap


# ---------------------------------------------------------------------------
# Tests — agent not available
# ---------------------------------------------------------------------------

class TestDeviceRouterWithoutAgent:
    """Verify endpoints return 503 when DeviceMonitorAgent is not available."""

    @pytest.mark.asyncio
    async def test_root_without_agent(self):
        transport = _app_without_agent()
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.get("/device/")
            assert resp.status_code == 503

    @pytest.mark.asyncio
    async def test_snapshot_without_agent(self):
        transport = _app_without_agent()
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.get("/device/snapshot")
            assert resp.status_code == 503

    @pytest.mark.asyncio
    async def test_diagnostics_without_agent(self):
        transport = _app_without_agent()
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.get("/device/diagnostics")
            assert resp.status_code == 503

    @pytest.mark.asyncio
    async def test_battery_without_agent(self):
        transport = _app_without_agent()
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.get("/device/battery")
            assert resp.status_code == 503

    @pytest.mark.asyncio
    async def test_thermals_without_agent(self):
        transport = _app_without_agent()
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.get("/device/thermals")
            assert resp.status_code == 503

    @pytest.mark.asyncio
    async def test_history_without_agent(self):
        transport = _app_without_agent()
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.get("/device/history/cpu")
            assert resp.status_code == 503

    @pytest.mark.asyncio
    async def test_history_aggregated_without_agent(self):
        transport = _app_without_agent()
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.get("/device/history/cpu/aggregated")
            assert resp.status_code == 503


# ---------------------------------------------------------------------------
# Tests — agent available
# ---------------------------------------------------------------------------

class TestDeviceRouterWithAgent:
    """Verify endpoints return correct data when agent is available."""

    @pytest.mark.asyncio
    async def test_root_returns_summary(self):
        transport, agent, snap = _app_with_agent()
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.get("/device/")
            assert resp.status_code == 200
            data = resp.json()
            assert data["hostname"] == "test-host"
            assert data["platform"] == "Darwin 23.4.0"
            assert data["overall_severity"] == "ok"

    @pytest.mark.asyncio
    async def test_snapshot_returns_full_dict(self):
        transport, agent, snap = _app_with_agent()
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.get("/device/snapshot")
            assert resp.status_code == 200
            data = resp.json()
            assert data["hostname"] == "test-host"
            assert "cpu" in data
            assert "memory" in data
            assert "disk" in data

    @pytest.mark.asyncio
    async def test_history_returns_placeholder(self):
        transport, agent, snap = _app_with_agent()
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.get("/device/history/cpu?metric=cpu_overall&hours=12")
            assert resp.status_code == 200
            data = resp.json()
            assert data["component"] == "cpu"
            assert data["metric"] == "cpu_overall"
            assert data["hours"] == 12
            assert data["data"] == []

    @pytest.mark.asyncio
    async def test_history_aggregated_returns_placeholder(self):
        transport, agent, snap = _app_with_agent()
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.get("/device/history/memory/aggregated?hours=6")
            assert resp.status_code == 200
            data = resp.json()
            assert data["component"] == "memory"
            assert data["hours"] == 6
            assert data["data"] == []

    @pytest.mark.asyncio
    async def test_diagnostics_returns_agent_response(self):
        from jarvis.agents.response import AgentResponse

        transport, agent, snap = _app_with_agent()
        mock_result = AgentResponse.success_response(
            response="All systems nominal.",
            data={"hostname": "test-host"},
            metadata={"agent": "device_monitor"},
        )
        agent._handle_device_diagnostics = AsyncMock(return_value=mock_result)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.get("/device/diagnostics")
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is True
            agent._handle_device_diagnostics.assert_called_once_with({})

    @pytest.mark.asyncio
    async def test_battery_no_battery(self):
        transport, agent, snap = _app_with_agent()
        # snap.battery is None by default
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.get("/device/battery")
            assert resp.status_code == 200
            data = resp.json()
            assert data["available"] is False

    @pytest.mark.asyncio
    async def test_battery_with_battery(self):
        svc_mod = sys.modules["jarvis.services.device_monitor_service"]
        transport, agent, snap = _app_with_agent()
        snap.battery = svc_mod.Metric(
            "battery", 72, unit="%",
            severity=SimpleNamespace(value="ok"),
            details={"plugged_in": True, "secs_left": None},
        )
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.get("/device/battery")
            assert resp.status_code == 200
            data = resp.json()
            assert data["available"] is True
            assert data["percent"] == 72
            assert data["plugged_in"] is True

    @pytest.mark.asyncio
    async def test_thermals_none_detected(self):
        transport, agent, snap = _app_with_agent()
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.get("/device/thermals")
            assert resp.status_code == 200
            data = resp.json()
            assert data["available"] is False
            assert data["sensors"] == []

    @pytest.mark.asyncio
    async def test_thermals_with_data(self):
        svc_mod = sys.modules["jarvis.services.device_monitor_service"]
        transport, agent, snap = _app_with_agent()
        snap.thermals = [
            svc_mod.Metric(
                "CPU Die", 45.0, unit="C",
                severity=SimpleNamespace(value="ok"),
                details={"high": 80.0, "critical": 95.0},
            ),
        ]
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.get("/device/thermals")
            assert resp.status_code == 200
            data = resp.json()
            assert data["available"] is True
            assert len(data["sensors"]) == 1
            assert data["sensors"][0]["name"] == "CPU Die"
            assert data["sensors"][0]["temperature_c"] == 45.0
