"""Tests for HealthService and ReportWriter."""
from __future__ import annotations

import os
import asyncio
import pytest
from datetime import datetime, timedelta

from jarvis.services.health_service import HealthService
from jarvis.agents.health_agent.models import (
    ComponentStatus,
    ProbeResult,
    IncidentRecord,
    IncidentSeverity,
    SystemHealthSnapshot,
    DependencyNode,
)
from jarvis.agents.health_agent.report_writer import ReportWriter


class TestHealthServiceHTTP:
    """Test HTTP probe methods."""

    @pytest.mark.asyncio
    async def test_probe_unreachable_service(self):
        service = HealthService(timeout=1.0)
        result = await service.probe_http_service("test", "http://127.0.0.1:19999")
        assert result.status == ComponentStatus.UNHEALTHY
        assert result.component == "test"

    @pytest.mark.asyncio
    async def test_probe_calendar_api_default(self):
        service = HealthService(timeout=1.0)
        result = await service.probe_calendar_api()
        # Will fail since no calendar API is running in tests
        assert result.component == "CalendarAPI"
        assert result.status in (ComponentStatus.UNHEALTHY, ComponentStatus.UNKNOWN)


class TestHealthServiceSQLite:
    """Test SQLite probe."""

    @pytest.mark.asyncio
    async def test_sqlite_exists(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        with open(db_path, "w") as f:
            f.write("test")
        service = HealthService()
        result = await service.probe_sqlite(db_path)
        assert result.status == ComponentStatus.HEALTHY
        assert result.component == "SQLite"

    @pytest.mark.asyncio
    async def test_sqlite_missing(self, tmp_path):
        service = HealthService()
        result = await service.probe_sqlite(str(tmp_path / "nonexistent.db"))
        assert result.status == ComponentStatus.DEGRADED


class TestHealthServiceResources:
    """Test resource probes."""

    def test_cpu_usage(self):
        service = HealthService()
        result = service.get_cpu_usage()
        # Should return a result regardless of psutil availability
        assert result.component == "CPU"
        assert result.status in ComponentStatus

    def test_memory_usage(self):
        service = HealthService()
        result = service.get_memory_usage()
        assert result.component == "Memory"
        assert result.status in ComponentStatus

    def test_disk_usage(self):
        service = HealthService()
        result = service.get_disk_usage()
        assert result.component == "Disk"
        assert result.status in ComponentStatus

    @pytest.mark.asyncio
    async def test_event_loop_lag(self):
        service = HealthService()
        result = await service.get_event_loop_lag()
        assert result.component == "EventLoop"
        assert result.latency_ms is not None
        assert result.latency_ms >= 0


class TestReportWriter:
    """Test ReportWriter file operations."""

    def test_write_status_file(self, tmp_path):
        writer = ReportWriter(str(tmp_path))
        snapshot = SystemHealthSnapshot(
            overall_status=ComponentStatus.HEALTHY,
            summary="All good",
            agent_statuses=[ProbeResult("TestAgent", "agent", ComponentStatus.HEALTHY, message="OK")],
        )
        path = writer.write_status_file(snapshot)
        assert os.path.exists(path)
        content = open(path).read()
        assert "System Health Status" in content
        assert "HEALTHY" in content

    def test_write_incident_report(self, tmp_path):
        writer = ReportWriter(str(tmp_path))
        incident = IncidentRecord(
            component="TestService",
            severity=IncidentSeverity.ERROR,
            title="TestService is down",
            description="Connection refused",
        )
        path = writer.write_incident_report(incident)
        assert os.path.exists(path)
        content = open(path).read()
        assert "TestService is down" in content

    def test_write_dependency_map(self, tmp_path):
        writer = ReportWriter(str(tmp_path))
        nodes = [
            DependencyNode("AgentA", "agent", depends_on=["ServiceB"]),
            DependencyNode("ServiceB", "service"),
        ]
        path = writer.write_dependency_map(nodes)
        assert os.path.exists(path)
        content = open(path).read()
        assert "mermaid" in content
        assert "AgentA" in content

    def test_read_report(self, tmp_path):
        writer = ReportWriter(str(tmp_path))
        (tmp_path / "test.md").write_text("# Test")
        content = writer.read_report("test.md")
        assert content == "# Test"

    def test_read_nonexistent(self, tmp_path):
        writer = ReportWriter(str(tmp_path))
        assert writer.read_report("nonexistent.md") is None

    def test_list_reports(self, tmp_path):
        writer = ReportWriter(str(tmp_path))
        (tmp_path / "a.md").write_text("A")
        (tmp_path / "b.md").write_text("B")
        reports = writer.list_reports()
        assert len(reports) == 2

    def test_list_reports_category(self, tmp_path):
        writer = ReportWriter(str(tmp_path))
        (tmp_path / "incidents").mkdir(exist_ok=True)
        (tmp_path / "incidents" / "inc.md").write_text("Incident")
        reports = writer.list_reports("incidents")
        assert len(reports) == 1

    def test_cleanup_old_reports(self, tmp_path):
        writer = ReportWriter(str(tmp_path))
        incidents_dir = tmp_path / "incidents"
        incidents_dir.mkdir(exist_ok=True)
        # Create old file
        old_file = incidents_dir / "2020-01-01_test.md"
        old_file.write_text("old")
        # Create recent file
        today = datetime.now().strftime("%Y-%m-%d")
        new_file = incidents_dir / f"{today}_test.md"
        new_file.write_text("new")

        removed = writer.cleanup_old_reports(retention_days=30)
        assert removed == 1
        assert not old_file.exists()
        assert new_file.exists()


class TestModels:
    """Test data model methods."""

    def test_probe_result_to_dict(self):
        pr = ProbeResult("Test", "agent", ComponentStatus.HEALTHY, latency_ms=5.123, message="OK")
        d = pr.to_dict()
        assert d["component"] == "Test"
        assert d["status"] == "healthy"
        assert d["latency_ms"] == 5.12

    def test_incident_is_active(self):
        inc = IncidentRecord(component="Test")
        assert inc.is_active
        inc.resolved_at = datetime.now()
        assert not inc.is_active

    def test_incident_to_dict(self):
        inc = IncidentRecord(
            component="Test",
            severity=IncidentSeverity.ERROR,
            title="Test down",
        )
        d = inc.to_dict()
        assert d["component"] == "Test"
        assert d["severity"] == "error"
        assert d["is_active"] is True

    def test_snapshot_to_dict(self):
        snap = SystemHealthSnapshot(
            overall_status=ComponentStatus.HEALTHY,
            summary="OK",
        )
        d = snap.to_dict()
        assert d["overall_status"] == "healthy"
        assert d["summary"] == "OK"

    def test_dependency_node_to_dict(self):
        node = DependencyNode("Test", "agent", depends_on=["A"])
        d = node.to_dict()
        assert d["name"] == "Test"
        assert "A" in d["depends_on"]
