"""Tests for the self-improvement HTTP API router.

Twenty-eight tests covering every endpoint, edge case, and the occasional
path-traversal attempt by hypothetical ne'er-do-wells.
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch  # noqa: F401

import httpx
import pytest
from httpx import ASGITransport
from fastapi import FastAPI


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@dataclass
class _FakeExecutionResult:
    success: bool = True
    stdout: str = "all passed"
    stderr: str = ""
    exit_code: int = 0
    duration_seconds: float = 0.42


def _project_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(autouse=True)
def _reset_state():
    """Ensure module-level state is pristine between tests."""
    from server.routers.self_improvement import _state

    _state.update(
        {
            "running": False,
            "discoveries": [],
            "test_runs": {},
            "submitted_tasks": [],
            "last_report": None,
            "cycle_error": None,
        }
    )
    yield


@pytest.fixture()
def mock_service():
    service = MagicMock()
    service._project_root = "/fake/project"
    service._runner = MagicMock()
    service._runner.run_tests = AsyncMock(return_value=_FakeExecutionResult())
    service._analyzer = MagicMock()
    service._analyzer.run_full_analysis = AsyncMock(return_value=[])
    service.get_latest_report = MagicMock(return_value=None)
    service.run_improvement_cycle = AsyncMock()
    service.REPORT_DIR = Path("/tmp/fake_reports_that_do_not_exist")
    service.MAX_TASKS_PER_NIGHT = 5
    return service


@pytest.fixture()
def app(mock_service):
    from server.routers.self_improvement import router

    app = FastAPI()
    app.include_router(router, prefix="/self-improvement")
    app.state.jarvis_system = None
    return app


@pytest.fixture()
def transport(app, mock_service):
    with patch(
        "server.routers.self_improvement._get_service", return_value=mock_service
    ):
        yield ASGITransport(app=app)


# ---------------------------------------------------------------------------
# GET /status
# ---------------------------------------------------------------------------


class TestStatus:
    @pytest.mark.asyncio
    async def test_status_returns_idle(self, transport):
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.get("/self-improvement/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["running"] is False
        assert data["discoveries_count"] == 0
        assert data["submitted_tasks_count"] == 0

    @pytest.mark.asyncio
    async def test_status_reflects_running(self, transport):
        from server.routers.self_improvement import _state

        _state["running"] = True
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.get("/self-improvement/status")
        assert resp.json()["running"] is True

    @pytest.mark.asyncio
    async def test_status_counts_discoveries(self, transport):
        from server.routers.self_improvement import _state

        _state["discoveries"] = [{"title": "a"}, {"title": "b"}]
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.get("/self-improvement/status")
        assert resp.json()["discoveries_count"] == 2


# ---------------------------------------------------------------------------
# POST /discover
# ---------------------------------------------------------------------------


class TestDiscover:
    @pytest.mark.asyncio
    async def test_discover_returns_results(self, transport, mock_service):
        from jarvis.services.system_analyzer import Discovery, DiscoveryType

        mock_service._analyzer.run_full_analysis = AsyncMock(
            return_value=[
                Discovery(
                    discovery_type=DiscoveryType.TEST_FAILURE,
                    title="broken test",
                    description="it broke",
                    priority="urgent",
                    relevant_files=["tests/test_x.py"],
                )
            ]
        )
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.post(
                "/self-improvement/discover", json={"lookback_hours": 12}
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert data["discoveries"][0]["title"] == "broken test"

    @pytest.mark.asyncio
    async def test_discover_filters_by_type(self, transport, mock_service):
        from jarvis.services.system_analyzer import Discovery, DiscoveryType

        mock_service._analyzer.run_full_analysis = AsyncMock(
            return_value=[
                Discovery(
                    discovery_type=DiscoveryType.TEST_FAILURE,
                    title="test issue",
                    description="d",
                    priority="high",
                ),
                Discovery(
                    discovery_type=DiscoveryType.CODE_QUALITY,
                    title="quality issue",
                    description="d",
                    priority="low",
                ),
            ]
        )
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.post(
                "/self-improvement/discover",
                json={"types": ["test_failure"]},
            )
        data = resp.json()
        assert data["count"] == 1
        assert data["discoveries"][0]["discovery_type"] == "test_failure"

    @pytest.mark.asyncio
    async def test_discover_caches_in_state(self, transport, mock_service):
        from server.routers.self_improvement import _state

        mock_service._analyzer.run_full_analysis = AsyncMock(return_value=[])
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            await c.post("/self-improvement/discover", json={})
        assert isinstance(_state["discoveries"], list)

    @pytest.mark.asyncio
    async def test_discover_empty(self, transport, mock_service):
        mock_service._analyzer.run_full_analysis = AsyncMock(return_value=[])
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.post("/self-improvement/discover", json={})
        assert resp.status_code == 200
        assert resp.json()["count"] == 0


# ---------------------------------------------------------------------------
# GET /discoveries
# ---------------------------------------------------------------------------


class TestDiscoveries:
    @pytest.mark.asyncio
    async def test_discoveries_empty(self, transport):
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.get("/self-improvement/discoveries")
        assert resp.status_code == 200
        assert resp.json()["count"] == 0

    @pytest.mark.asyncio
    async def test_discoveries_returns_cached(self, transport):
        from server.routers.self_improvement import _state

        _state["discoveries"] = [
            {"discovery_type": "test_failure", "title": "one"},
            {"discovery_type": "code_quality", "title": "two"},
        ]
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.get("/self-improvement/discoveries")
        assert resp.json()["count"] == 2

    @pytest.mark.asyncio
    async def test_discoveries_filters_by_type(self, transport):
        from server.routers.self_improvement import _state

        _state["discoveries"] = [
            {"discovery_type": "test_failure", "title": "one"},
            {"discovery_type": "code_quality", "title": "two"},
        ]
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.get("/self-improvement/discoveries?type=code_quality")
        data = resp.json()
        assert data["count"] == 1
        assert data["discoveries"][0]["title"] == "two"


# ---------------------------------------------------------------------------
# POST /cycle
# ---------------------------------------------------------------------------


class TestCycle:
    @pytest.mark.asyncio
    async def test_cycle_starts(self, transport, mock_service):
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.post("/self-improvement/cycle", json={})
        assert resp.status_code == 200
        assert resp.json()["status"] == "started"

    @pytest.mark.asyncio
    async def test_cycle_rejects_concurrent(self, transport):
        from server.routers.self_improvement import _state

        _state["running"] = True
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.post("/self-improvement/cycle", json={})
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_cycle_accepts_parameters(self, transport, mock_service):
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.post(
                "/self-improvement/cycle",
                json={"max_tasks": 3, "dry_run": True},
            )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# POST /tasks  &  GET /tasks
# ---------------------------------------------------------------------------


class TestTasks:
    @pytest.mark.asyncio
    async def test_submit_task(self, transport):
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.post(
                "/self-improvement/tasks",
                json={
                    "title": "Add logging",
                    "description": "More logs please",
                    "priority": "high",
                    "relevant_files": ["jarvis/core/system.py"],
                },
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "Add logging"
        assert data["status"] == "pending"
        assert "id" in data

    @pytest.mark.asyncio
    async def test_submit_task_defaults(self, transport):
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.post(
                "/self-improvement/tasks",
                json={"title": "Quick fix", "description": "Do the thing"},
            )
        data = resp.json()
        assert data["priority"] == "medium"
        assert data["relevant_files"] == []

    @pytest.mark.asyncio
    async def test_list_tasks_empty(self, transport):
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.get("/self-improvement/tasks")
        assert resp.json()["count"] == 0

    @pytest.mark.asyncio
    async def test_list_tasks_after_submit(self, transport):
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            await c.post(
                "/self-improvement/tasks",
                json={"title": "A", "description": "B"},
            )
            await c.post(
                "/self-improvement/tasks",
                json={"title": "C", "description": "D"},
            )
            resp = await c.get("/self-improvement/tasks")
        assert resp.json()["count"] == 2


# ---------------------------------------------------------------------------
# POST /tests/run  &  GET /tests/{run_id}
# ---------------------------------------------------------------------------


class TestTestRuns:
    @pytest.mark.asyncio
    async def test_start_test_run(self, transport, mock_service):
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.post("/self-improvement/tests/run", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert "run_id" in data
        assert data["status"] == "pending"

    @pytest.mark.asyncio
    async def test_get_unknown_run_404(self, transport):
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.get(f"/self-improvement/tests/{uuid.uuid4()}")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_get_existing_run(self, transport):
        from server.routers.self_improvement import _state

        run_id = "test-run-123"
        _state["test_runs"][run_id] = {
            "run_id": run_id,
            "status": "completed",
            "success": True,
        }
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.get(f"/self-improvement/tests/{run_id}")
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    @pytest.mark.asyncio
    async def test_start_run_with_params(self, transport, mock_service):
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.post(
                "/self-improvement/tests/run",
                json={
                    "test_files": ["tests/test_foo.py"],
                    "working_directory": "/tmp",
                    "timeout": 60,
                },
            )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# GET /reports/latest  &  GET /reports
# ---------------------------------------------------------------------------


class TestReports:
    @pytest.mark.asyncio
    async def test_latest_report_none(self, transport, mock_service):
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.get("/self-improvement/reports/latest")
        assert resp.status_code == 200
        assert resp.json()["report"] is None

    @pytest.mark.asyncio
    async def test_latest_report_exists(self, transport, mock_service):
        from jarvis.services.self_improvement_service import NightReport

        report = NightReport(
            started_at="2026-01-01T00:00:00Z",
            completed_at="2026-01-01T00:05:00Z",
            tasks_attempted=2,
            tasks_succeeded=1,
            tasks_failed=1,
            total_files_changed=4,
            total_duration_seconds=300.0,
        )
        mock_service.get_latest_report.return_value = report
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.get("/self-improvement/reports/latest")
        data = resp.json()
        assert data["report"]["tasks_attempted"] == 2

    @pytest.mark.asyncio
    async def test_list_reports_empty_dir(self, transport, mock_service):
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.get("/self-improvement/reports")
        assert resp.status_code == 200
        assert resp.json()["count"] == 0

    @pytest.mark.asyncio
    async def test_list_reports_with_limit(self, transport, mock_service):
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.get("/self-improvement/reports?limit=5")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# GET /context/{file_path}
# ---------------------------------------------------------------------------


class TestContext:
    @pytest.mark.asyncio
    async def test_read_existing_file(self, transport):
        # Read this very test file — it certainly exists
        this_file = os.path.relpath(__file__, _project_root())
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.get(f"/self-improvement/context/{this_file}")
        assert resp.status_code == 200
        data = resp.json()
        assert "content" in data
        assert data["size"] > 0

    @pytest.mark.asyncio
    async def test_path_traversal_blocked(self):
        """Test traversal protection directly — httpx normalises '..' in URLs,
        so we call the endpoint function with a raw traversal path."""
        from fastapi import HTTPException
        from server.routers.self_improvement import get_context

        with pytest.raises(HTTPException) as exc_info:
            await get_context("../../etc/passwd")
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_path_traversal_via_http_is_safe(self, transport):
        """When httpx normalises the '..' away, the resulting path simply
        doesn't exist — so we get 404, not a leak."""
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.get("/self-improvement/context/../../etc/passwd")
        # httpx collapses '..' so the server sees 'etc/passwd' — not a real file
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_nonexistent_file_404(self, transport):
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.get(
                "/self-improvement/context/this_file_does_not_exist_at_all.txt"
            )
        assert resp.status_code == 404
