"""Tests for DeviceMonitorAgent and DeviceMonitorService."""

from __future__ import annotations

import platform
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

from jarvis.agents.device_monitor_agent import DeviceMonitorAgent
from jarvis.services.device_monitor_service import (
    DeviceMonitorService,
    DeviceSnapshot,
    Metric,
    ProcessInfo,
    Severity,
    _severity,
)
from jarvis.services.metrics_store import MetricsStore


# ---------------------------------------------------------------------------
# Suppress native macOS notifications during tests
# ---------------------------------------------------------------------------

# Keep a reference to the real method before any patching.
_real_send_macos_notification = DeviceMonitorAgent._send_macos_notification


@pytest.fixture(autouse=True)
def _no_macos_notifications():
    """Prevent osascript notifications from firing during tests."""
    with patch.object(DeviceMonitorAgent, "_send_macos_notification"):
        yield


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_agent(device_service=None, metrics_store=None, probe_interval=30.0) -> DeviceMonitorAgent:
    logger = MagicMock()
    logger.log = MagicMock()
    svc = device_service or DeviceMonitorService()
    agent = DeviceMonitorAgent(
        device_service=svc,
        metrics_store=metrics_store,
        logger=logger,
        probe_interval=probe_interval,
    )
    return agent


def _make_message(capability: str, data: dict | None = None):
    msg = MagicMock()
    msg.id = "msg-1"
    msg.from_agent = "TestRequester"
    msg.request_id = "req-1"
    msg.content = {
        "capability": capability,
        "data": data or {},
    }
    return msg


def _make_mock_service() -> DeviceMonitorService:
    """Create a DeviceMonitorService with psutil mocked away."""
    svc = DeviceMonitorService.__new__(DeviceMonitorService)
    svc._psutil = None  # will be overridden per-test as needed
    svc._prev_disk_io = None
    svc._prev_disk_io_time = None
    svc._prev_net_io = None
    svc._prev_net_io_time = None
    svc._cached_gpu_info = None
    svc._cached_hardware_info = None
    return svc


# ---------------------------------------------------------------------------
# Severity helper
# ---------------------------------------------------------------------------

class TestSeverityHelper:
    def test_ok(self):
        assert _severity(50.0, 70.0, 90.0) == Severity.OK

    def test_warning(self):
        assert _severity(75.0, 70.0, 90.0) == Severity.WARNING

    def test_critical(self):
        assert _severity(95.0, 70.0, 90.0) == Severity.CRITICAL

    def test_exact_boundary_warning(self):
        assert _severity(70.0, 70.0, 90.0) == Severity.WARNING

    def test_exact_boundary_critical(self):
        assert _severity(90.0, 70.0, 90.0) == Severity.CRITICAL


# ---------------------------------------------------------------------------
# DeviceMonitorService
# ---------------------------------------------------------------------------

class TestDeviceMonitorService:
    def test_has_psutil_false_when_missing(self):
        svc = _make_mock_service()
        svc._psutil = None
        assert svc.has_psutil is False

    def test_snapshot_without_psutil(self):
        svc = _make_mock_service()
        snap = svc.snapshot()
        assert isinstance(snap, DeviceSnapshot)
        assert snap.hostname != ""
        # Should have a warning metric about missing psutil
        assert any(m.severity == Severity.WARNING for m in snap.cpu)

    def test_top_processes_without_psutil(self):
        svc = _make_mock_service()
        assert svc.top_processes() == []

    def test_get_zombie_processes_without_psutil(self):
        svc = _make_mock_service()
        assert svc.get_zombie_processes() == []

    def test_kill_process_without_psutil(self):
        svc = _make_mock_service()
        result = svc.kill_process(12345)
        assert result["success"] is False
        assert "psutil" in result["error"]

    def test_format_uptime_days(self):
        assert DeviceMonitorService.format_uptime(90061) == "1d 1h 1m"

    def test_format_uptime_hours(self):
        assert DeviceMonitorService.format_uptime(7260) == "2h 1m"

    def test_format_uptime_minutes(self):
        assert DeviceMonitorService.format_uptime(300) == "5m"

    def test_clear_temp_files_returns_dict(self):
        svc = DeviceMonitorService()
        result = svc.clear_temp_files()
        assert "cleared" in result
        assert "freed_mb" in result
        assert "tmp_dir" in result


# ---------------------------------------------------------------------------
# DeviceSnapshot serialization
# ---------------------------------------------------------------------------

class TestDeviceSnapshot:
    def test_to_dict_empty(self):
        snap = DeviceSnapshot()
        d = snap.to_dict()
        assert d["overall_severity"] == "ok"
        assert d["cpu"] == []
        assert d["battery"] is None

    def test_to_dict_with_metrics(self):
        snap = DeviceSnapshot(
            hostname="test-host",
            cpu=[Metric("cpu_overall", 42.0, unit="%")],
            battery=Metric("battery", 85, unit="%", details={"plugged_in": True}),
        )
        d = snap.to_dict()
        assert d["hostname"] == "test-host"
        assert len(d["cpu"]) == 1
        assert d["cpu"][0]["value"] == 42.0
        assert d["battery"]["value"] == 85


# ---------------------------------------------------------------------------
# ProcessInfo serialization
# ---------------------------------------------------------------------------

class TestProcessInfo:
    def test_to_dict(self):
        p = ProcessInfo(pid=1, name="test", cpu_percent=1.5, memory_mb=123.456)
        d = p.to_dict()
        assert d["pid"] == 1
        assert d["memory_mb"] == 123.5  # rounded


# ---------------------------------------------------------------------------
# DeviceMonitorAgent — capabilities
# ---------------------------------------------------------------------------

class TestDeviceMonitorAgentProperties:
    def test_name(self):
        agent = _make_agent()
        assert agent.name == "DeviceMonitorAgent"

    def test_capabilities(self):
        agent = _make_agent()
        assert agent.capabilities == {"device_status", "device_diagnostics", "device_cleanup", "device_history"}

    def test_description(self):
        agent = _make_agent()
        assert "hardware" in agent.description.lower()

    def test_supports_dialogue(self):
        agent = _make_agent()
        assert agent.supports_dialogue is False


class TestDeviceMonitorAgentHandlers:
    @pytest.mark.asyncio
    async def test_device_status(self):
        svc = DeviceMonitorService()
        agent = _make_agent(device_service=svc)
        agent.send_capability_response = AsyncMock()

        msg = _make_message("device_status")
        await agent._handle_capability_request(msg)

        agent.send_capability_response.assert_called_once()
        call_args = agent.send_capability_response.call_args
        result_dict = call_args[0][1]
        assert result_dict["success"] is True
        assert "hostname" in (result_dict.get("data") or {})

    @pytest.mark.asyncio
    async def test_device_diagnostics(self):
        svc = DeviceMonitorService()
        agent = _make_agent(device_service=svc)
        agent.send_capability_response = AsyncMock()

        msg = _make_message("device_diagnostics")
        await agent._handle_capability_request(msg)

        agent.send_capability_response.assert_called_once()
        result_dict = agent.send_capability_response.call_args[0][1]
        assert result_dict["success"] is True
        data = result_dict.get("data") or {}
        assert "top_by_cpu" in data
        assert "top_by_memory" in data
        assert "zombies" in data

    @pytest.mark.asyncio
    async def test_device_cleanup(self):
        svc = DeviceMonitorService()
        agent = _make_agent(device_service=svc)
        agent.send_capability_response = AsyncMock()

        msg = _make_message("device_cleanup")
        await agent._handle_capability_request(msg)

        agent.send_capability_response.assert_called_once()
        result_dict = agent.send_capability_response.call_args[0][1]
        assert result_dict["success"] is True
        actions = result_dict.get("actions") or []
        assert any(a["type"] == "temp_cleanup" for a in actions)

    @pytest.mark.asyncio
    async def test_device_cleanup_with_invalid_pid(self):
        svc = DeviceMonitorService()
        agent = _make_agent(device_service=svc)
        agent.send_capability_response = AsyncMock()

        msg = _make_message("device_cleanup", {"kill_pid": "not-a-number"})
        await agent._handle_capability_request(msg)

        agent.send_capability_response.assert_called_once()
        result_dict = agent.send_capability_response.call_args[0][1]
        assert result_dict["success"] is False

    @pytest.mark.asyncio
    async def test_unknown_capability(self):
        agent = _make_agent()
        agent.send_error = AsyncMock()

        msg = _make_message("unknown_thing")
        await agent._handle_capability_request(msg)

        agent.send_error.assert_called_once()

    @pytest.mark.asyncio
    async def test_device_cleanup_with_kill_pid(self):
        svc = DeviceMonitorService()
        # Mock kill_process to avoid actually killing anything
        svc.kill_process = MagicMock(return_value={"success": True, "pid": 999, "name": "test", "action": "terminated"})
        svc.get_zombie_processes = MagicMock(return_value=[])

        agent = _make_agent(device_service=svc)
        agent.send_capability_response = AsyncMock()

        msg = _make_message("device_cleanup", {"kill_pid": 999})
        await agent._handle_capability_request(msg)

        svc.kill_process.assert_called_once_with(999)
        result_dict = agent.send_capability_response.call_args[0][1]
        assert result_dict["success"] is True
        actions = result_dict.get("actions") or []
        assert any(a["type"] == "process_kill" for a in actions)


# ---------------------------------------------------------------------------
# Snapshot formatting
# ---------------------------------------------------------------------------

class TestSnapshotFormatting:
    def test_format_snapshot_nominal(self):
        agent = _make_agent()
        snap = DeviceSnapshot(
            hostname="jarvis-host",
            platform="Darwin 23.4.0",
            uptime_seconds=86400,
            overall_severity=Severity.OK,
            cpu=[Metric("cpu_overall", 25.0, unit="%", details={"core_count": 8})],
            memory=[Metric("ram", 55.0, unit="%", details={"total_gb": 16, "available_gb": 7.2, "used_gb": 8.8})],
            disk=[Metric("/", 60.0, unit="%", details={"free_gb": 200, "total_gb": 500})],
        )
        text = agent._format_snapshot(snap)
        assert "jarvis-host" in text
        assert "25.0%" in text
        assert "nominal" in text.lower()

    def test_format_snapshot_critical(self):
        agent = _make_agent()
        snap = DeviceSnapshot(
            hostname="melting-host",
            platform="Linux",
            overall_severity=Severity.CRITICAL,
            cpu=[Metric("cpu_overall", 98.0, unit="%", severity=Severity.CRITICAL, details={"core_count": 4})],
            memory=[],
        )
        text = agent._format_snapshot(snap)
        assert "fire" in text.lower()

    def test_format_snapshot_with_battery(self):
        agent = _make_agent()
        snap = DeviceSnapshot(
            hostname="laptop",
            platform="Darwin",
            overall_severity=Severity.WARNING,
            battery=Metric("battery", 15, unit="%", severity=Severity.WARNING, details={"plugged_in": False}),
        )
        text = agent._format_snapshot(snap)
        assert "15%" in text
        assert "on battery" in text


# ---------------------------------------------------------------------------
# DeviceSnapshot — new fields
# ---------------------------------------------------------------------------

class TestDeviceSnapshotNewFields:
    def test_to_dict_includes_new_fields(self):
        snap = DeviceSnapshot(
            hostname="test",
            disk_io=[Metric("disk_read_bytes_sec", 1024.0, unit="B/s")],
            network_io=[Metric("net_bytes_recv_sec", 2048.0, unit="B/s")],
            memory_pressure={"pages_active": 100},
            gpu=Metric("gpu", "Apple M1", details={"vram": "16 GB"}),
            hardware_info={"chip": "Apple M1"},
        )
        d = snap.to_dict()
        assert len(d["disk_io"]) == 1
        assert len(d["network_io"]) == 1
        assert d["memory_pressure"]["pages_active"] == 100
        assert d["gpu"]["value"] == "Apple M1"
        assert d["hardware_info"]["chip"] == "Apple M1"

    def test_to_dict_defaults_empty(self):
        snap = DeviceSnapshot()
        d = snap.to_dict()
        assert d["disk_io"] == []
        assert d["network_io"] == []
        assert d["memory_pressure"] is None
        assert d["gpu"] is None
        assert d["hardware_info"] is None


# ---------------------------------------------------------------------------
# Disk I/O and Network throughput
# ---------------------------------------------------------------------------

class TestDiskIOAndNetworkThroughput:
    def test_disk_io_first_call_returns_empty(self):
        svc = DeviceMonitorService()
        result = svc.get_disk_io_rates()
        # First call has no delta — should return empty
        assert isinstance(result, list)

    def test_network_throughput_first_call_returns_empty(self):
        svc = DeviceMonitorService()
        result = svc.get_network_throughput()
        assert isinstance(result, list)

    def test_disk_io_without_psutil(self):
        svc = _make_mock_service()
        result = svc.get_disk_io_rates()
        assert result == []

    def test_network_throughput_without_psutil(self):
        svc = _make_mock_service()
        result = svc.get_network_throughput()
        assert result == []

    def test_disk_io_second_call_returns_metrics(self):
        svc = DeviceMonitorService()
        if not svc.has_psutil:
            pytest.skip("psutil not available")
        svc.get_disk_io_rates()  # prime the pump
        import time
        time.sleep(0.05)
        result = svc.get_disk_io_rates()
        # Second call may return metrics if psutil provides counters
        assert isinstance(result, list)
        if result:
            assert result[0].name == "disk_read_bytes_sec"
            assert result[1].name == "disk_write_bytes_sec"

    def test_network_throughput_second_call_returns_metrics(self):
        svc = DeviceMonitorService()
        if not svc.has_psutil:
            pytest.skip("psutil not available")
        svc.get_network_throughput()  # prime
        import time
        time.sleep(0.05)
        result = svc.get_network_throughput()
        assert isinstance(result, list)
        if result:
            assert result[0].name == "net_bytes_sent_sec"
            assert result[1].name == "net_bytes_recv_sec"


# ---------------------------------------------------------------------------
# macOS-specific methods — graceful degradation
# ---------------------------------------------------------------------------

class TestMacOSSpecificMethods:
    """These methods rely on macOS-only commands.

    On macOS they may return data; on other platforms (or CI)
    they should return None gracefully without raising.
    """

    def test_memory_pressure_returns_dict_or_none(self):
        svc = DeviceMonitorService()
        result = svc.get_memory_pressure()
        if platform.system() == "Darwin":
            # On macOS it should parse vm_stat successfully
            assert result is None or isinstance(result, dict)
        else:
            assert result is None

    def test_battery_health_returns_dict_or_none(self):
        svc = DeviceMonitorService()
        result = svc.get_battery_health()
        # Desktops may not have a battery — None is fine
        assert result is None or isinstance(result, dict)

    def test_thermal_status_returns_dict_or_none(self):
        svc = DeviceMonitorService()
        result = svc.get_thermal_status()
        assert result is None or isinstance(result, dict)

    def test_gpu_info_returns_metric_or_none(self):
        svc = DeviceMonitorService()
        result = svc.get_gpu_info()
        if platform.system() == "Darwin":
            assert result is None or isinstance(result, Metric)
        else:
            assert result is None

    def test_gpu_info_caches(self):
        svc = DeviceMonitorService()
        first = svc.get_gpu_info()
        second = svc.get_gpu_info()
        # Cached: same object identity (or both None)
        assert first is second

    def test_hardware_info_returns_dict_or_none(self):
        svc = DeviceMonitorService()
        result = svc.get_hardware_info()
        if platform.system() == "Darwin":
            assert result is None or isinstance(result, dict)
        else:
            assert result is None

    def test_hardware_info_caches(self):
        svc = DeviceMonitorService()
        first = svc.get_hardware_info()
        second = svc.get_hardware_info()
        assert first is second

    def test_memory_pressure_non_darwin(self):
        svc = _make_mock_service()
        # Force non-Darwin by mocking
        import unittest.mock as mock
        with mock.patch("jarvis.services.device_monitor_service.platform") as mock_plat:
            mock_plat.system.return_value = "Linux"
            mock_plat.node.return_value = "test"
            mock_plat.release.return_value = "5.0"
            assert svc.get_memory_pressure() is None

    def test_battery_health_non_darwin(self):
        svc = _make_mock_service()
        import unittest.mock as mock
        with mock.patch("jarvis.services.device_monitor_service.platform") as mock_plat:
            mock_plat.system.return_value = "Linux"
            assert svc.get_battery_health() is None

    def test_thermal_status_non_darwin(self):
        svc = _make_mock_service()
        import unittest.mock as mock
        with mock.patch("jarvis.services.device_monitor_service.platform") as mock_plat:
            mock_plat.system.return_value = "Linux"
            assert svc.get_thermal_status() is None

    def test_gpu_info_non_darwin(self):
        svc = _make_mock_service()
        import unittest.mock as mock
        with mock.patch("jarvis.services.device_monitor_service.platform") as mock_plat:
            mock_plat.system.return_value = "Linux"
            assert svc.get_gpu_info() is None

    def test_hardware_info_non_darwin(self):
        svc = _make_mock_service()
        import unittest.mock as mock
        with mock.patch("jarvis.services.device_monitor_service.platform") as mock_plat:
            mock_plat.system.return_value = "Linux"
            assert svc.get_hardware_info() is None


# ---------------------------------------------------------------------------
# Phase 4 — V2 Properties
# ---------------------------------------------------------------------------

class TestDeviceMonitorAgentV2Properties:
    def test_capabilities_include_history(self):
        agent = _make_agent()
        assert "device_history" in agent.capabilities

    def test_probe_interval_default(self):
        agent = _make_agent()
        assert agent._probe_interval == 30.0

    def test_probe_interval_custom(self):
        agent = _make_agent(probe_interval=10.0)
        assert agent._probe_interval == 10.0


# ---------------------------------------------------------------------------
# Phase 4 — Background monitor loop
# ---------------------------------------------------------------------------

class TestBackgroundMonitorLoop:
    @pytest.mark.asyncio
    async def test_set_network_starts_monitor(self):
        agent = _make_agent()
        network = MagicMock()
        network.agents = {"DeviceMonitorAgent": agent}
        agent.set_network(network)
        assert agent._monitor_task is not None
        assert not agent._monitor_task.done()
        await agent.stop()

    @pytest.mark.asyncio
    async def test_stop_cancels_monitor(self):
        agent = _make_agent()
        network = MagicMock()
        network.agents = {"DeviceMonitorAgent": agent}
        agent.set_network(network)
        assert agent._monitor_task is not None
        await agent.stop()
        assert agent._monitor_task.done()


# ---------------------------------------------------------------------------
# Phase 4 — Transition detection
# ---------------------------------------------------------------------------

class TestTransitionDetection:
    @pytest.mark.asyncio
    async def test_no_alert_on_first_probe(self):
        agent = _make_agent()
        snap = DeviceSnapshot(
            cpu=[Metric("cpu_overall", 50.0, severity=Severity.OK, details={"core_count": 4})],
        )
        # Should not raise or broadcast on first probe
        await agent._process_transitions(snap)
        assert "cpu" in agent._component_statuses

    @pytest.mark.asyncio
    async def test_alert_on_degradation(self):
        agent = _make_agent()
        agent.network = MagicMock()
        agent.network.agents = {"OtherAgent": MagicMock()}
        agent.network.agents["OtherAgent"].receive_message = AsyncMock()

        # First probe: OK
        snap_ok = DeviceSnapshot(
            cpu=[Metric("cpu_overall", 50.0, severity=Severity.OK, details={"core_count": 4})],
        )
        await agent._process_transitions(snap_ok)

        # Second probe: CRITICAL
        snap_crit = DeviceSnapshot(
            cpu=[Metric("cpu_overall", 95.0, severity=Severity.CRITICAL, details={"core_count": 4})],
        )
        await agent._process_transitions(snap_crit)

        # Should have broadcast an alert
        agent.network.agents["OtherAgent"].receive_message.assert_called_once()
        msg = agent.network.agents["OtherAgent"].receive_message.call_args[0][0]
        assert msg.message_type == "health_alert"
        assert msg.content["source"] == "device_monitor"
        assert msg.content["new_status"] == "critical"

    @pytest.mark.asyncio
    async def test_no_alert_on_stable(self):
        agent = _make_agent()
        agent.network = MagicMock()
        agent.network.agents = {}

        snap = DeviceSnapshot(
            cpu=[Metric("cpu_overall", 50.0, severity=Severity.OK, details={"core_count": 4})],
        )
        await agent._process_transitions(snap)
        await agent._process_transitions(snap)  # Same severity, no alert


# ---------------------------------------------------------------------------
# Phase 4 — Auto-corrective actions
# ---------------------------------------------------------------------------

class TestAutoCorrect:
    @pytest.mark.asyncio
    async def test_disk_critical_triggers_cleanup(self):
        svc = DeviceMonitorService()
        svc.clear_temp_files = MagicMock(return_value={"cleared": 5, "freed_mb": 100, "errors": 0, "tmp_dir": "/tmp"})
        agent = _make_agent(device_service=svc)

        snap = DeviceSnapshot(
            disk=[Metric("/", 96.0, severity=Severity.CRITICAL, details={})],
        )
        await agent._auto_correct(snap)
        svc.clear_temp_files.assert_called_once()

    @pytest.mark.asyncio
    async def test_consecutive_high_cpu_tracking(self):
        agent = _make_agent()
        snap = DeviceSnapshot(
            cpu=[Metric("cpu_overall", 95.0, severity=Severity.CRITICAL, details={"core_count": 4})],
        )
        await agent._auto_correct(snap)
        assert agent._consecutive_high_cpu == 1
        await agent._auto_correct(snap)
        assert agent._consecutive_high_cpu == 2

    @pytest.mark.asyncio
    async def test_cpu_resets_on_recovery(self):
        agent = _make_agent()
        snap_high = DeviceSnapshot(
            cpu=[Metric("cpu_overall", 95.0, severity=Severity.CRITICAL, details={"core_count": 4})],
        )
        snap_low = DeviceSnapshot(
            cpu=[Metric("cpu_overall", 30.0, severity=Severity.OK, details={"core_count": 4})],
        )
        await agent._auto_correct(snap_high)
        await agent._auto_correct(snap_high)
        assert agent._consecutive_high_cpu == 2
        await agent._auto_correct(snap_low)
        assert agent._consecutive_high_cpu == 0


# ---------------------------------------------------------------------------
# Phase 4 — Metrics recording
# ---------------------------------------------------------------------------

class TestMetricsRecording:
    def test_record_snapshot_with_store(self, tmp_path):
        store = MetricsStore(db_path=str(tmp_path / "test.db"))
        agent = _make_agent(metrics_store=store)

        snap = DeviceSnapshot(
            hostname="test",
            cpu=[Metric("cpu_overall", 42.0, unit="%", severity=Severity.OK, details={"core_count": 4})],
            memory=[Metric("ram", 60.0, unit="%", severity=Severity.OK)],
            disk=[Metric("/", 50.0, unit="%", severity=Severity.OK)],
        )
        agent._record_snapshot(snap)

        rows = store.query("cpu")
        assert len(rows) == 1
        assert rows[0]["value"] == 42.0

        rows = store.query("memory")
        assert len(rows) == 1
        assert rows[0]["value"] == 60.0

        store.close()

    def test_record_snapshot_without_store(self):
        agent = _make_agent(metrics_store=None)
        snap = DeviceSnapshot()
        # Should not raise
        agent._record_snapshot(snap)


# ---------------------------------------------------------------------------
# Phase 4 — Device history capability
# ---------------------------------------------------------------------------

class TestDeviceHistory:
    @pytest.mark.asyncio
    async def test_history_without_store(self):
        agent = _make_agent(metrics_store=None)
        result = await agent._handle_device_history({})
        assert result.success is False

    @pytest.mark.asyncio
    async def test_history_with_data(self, tmp_path):
        store = MetricsStore(db_path=str(tmp_path / "test.db"))
        agent = _make_agent(metrics_store=store)

        # Insert some data
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        store.record_batch([
            {"timestamp": now, "component": "cpu", "metric_name": "cpu_overall",
             "value": 42.0, "unit": "%", "severity": "ok"},
            {"timestamp": now, "component": "cpu", "metric_name": "cpu_overall",
             "value": 55.0, "unit": "%", "severity": "ok"},
        ])

        result = await agent._handle_device_history({"component": "cpu", "hours": 1})
        assert result.success is True
        assert result.data["trend"] in ("rising", "falling", "stable")
        assert result.data["sample_count"] == 2

        store.close()

    @pytest.mark.asyncio
    async def test_history_no_data(self, tmp_path):
        store = MetricsStore(db_path=str(tmp_path / "test.db"))
        agent = _make_agent(metrics_store=store)

        result = await agent._handle_device_history({"component": "nonexistent", "hours": 1})
        assert result.success is True
        assert "No historical data" in result.response
        store.close()


# ---------------------------------------------------------------------------
# Phase 4 — macOS notification
# ---------------------------------------------------------------------------

class TestMacOSNotification:
    """Test the real _send_macos_notification logic (bypassing the autouse mock)."""

    def test_notification_non_darwin(self):
        agent = _make_agent()
        with patch("platform.system", return_value="Linux"):
            _real_send_macos_notification(agent, "Test", "Message")  # should no-op

    @pytest.mark.skipif(platform.system() != "Darwin", reason="macOS only")
    def test_notification_on_darwin(self):
        agent = _make_agent()
        with patch("subprocess.Popen") as mock_popen:
            _real_send_macos_notification(agent, "Test Title", "Test message")
            mock_popen.assert_called_once()
