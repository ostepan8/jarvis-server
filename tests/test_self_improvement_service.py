"""Tests for SelfImprovementService — autonomous improvement orchestrator."""

from __future__ import annotations

import json
from enum import Enum
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from jarvis.services.self_improvement_service import (
    PRIORITY_ORDER,
    ImprovementTaskResult,
    NightReport,
    SelfImprovementService,
)


# ---------------------------------------------------------------------------
# Stub types for dependencies that may not exist yet
# ---------------------------------------------------------------------------


class FakeDiscoveryType(str, Enum):
    """Mirrors the real DiscoveryType enum from SystemAnalyzer."""

    TEST_FAILURE = "test_failure"
    LOG_ERROR = "log_error"
    MANUAL_TODO = "manual_todo"
    CODE_QUALITY = "code_quality"


class FakeDiscovery:
    """Minimal stub matching the Discovery dataclass contract."""

    def __init__(
        self,
        discovery_type,
        title,
        description,
        priority,
        relevant_files=None,
        source_detail="",
        todo_id=None,
    ):
        self.discovery_type = discovery_type
        self.title = title
        self.description = description
        self.priority = priority
        self.relevant_files = relevant_files or []
        self.source_detail = source_detail
        self.todo_id = todo_id


class FakeExecutionResult:
    """Minimal stub matching the ExecutionResult dataclass contract."""

    def __init__(
        self,
        success=True,
        stdout="",
        stderr="",
        exit_code=0,
        files_changed=0,
        duration_seconds=0.0,
        worktree_path=None,
        branch_name=None,
    ):
        self.success = success
        self.stdout = stdout
        self.stderr = stderr
        self.exit_code = exit_code
        self.files_changed = files_changed
        self.duration_seconds = duration_seconds
        self.worktree_path = worktree_path
        self.branch_name = branch_name


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_service(tmp_path: Path) -> SelfImprovementService:
    """Build a SelfImprovementService with all external deps mocked out."""
    with patch(
        "jarvis.services.self_improvement_service.SystemAnalyzer"
    ) as MockAnalyzer, patch(
        "jarvis.services.self_improvement_service.ClaudeCodeRunner"
    ) as MockRunner:
        mock_analyzer = MagicMock()
        mock_runner = MagicMock()
        MockAnalyzer.return_value = mock_analyzer
        MockRunner.return_value = mock_runner

        svc = SelfImprovementService(
            project_root=str(tmp_path),
            logger=MagicMock(),
        )

        # Replace report dir to avoid touching the real home directory
        svc.REPORT_DIR = tmp_path / "night_reports"

        # Expose mocks for further configuration by callers
        svc._analyzer = mock_analyzer
        svc._runner = mock_runner

    return svc


# ---------------------------------------------------------------------------
# TestPrioritization
# ---------------------------------------------------------------------------


class TestPrioritization:
    """Verify discovery prioritization logic."""

    def test_test_failures_come_first(self, tmp_path):
        """Test failures should be prioritized over log errors."""
        svc = _make_service(tmp_path)

        discoveries = [
            FakeDiscovery(
                FakeDiscoveryType.LOG_ERROR,
                "Log error",
                "Some log error",
                "high",
            ),
            FakeDiscovery(
                FakeDiscoveryType.TEST_FAILURE,
                "Test failure",
                "A test is broken",
                "medium",
            ),
            FakeDiscovery(
                FakeDiscoveryType.CODE_QUALITY,
                "Code smell",
                "Low quality code",
                "low",
            ),
        ]

        result = svc._prioritize(discoveries)
        assert result[0].title == "Test failure"
        assert result[1].title == "Log error"
        assert result[2].title == "Code smell"

    def test_same_type_sorted_by_urgency_string(self, tmp_path):
        """Within the same discovery type, sort by priority string."""
        svc = _make_service(tmp_path)

        discoveries = [
            FakeDiscovery(
                FakeDiscoveryType.TEST_FAILURE,
                "Low-priority failure",
                "desc",
                "low",
            ),
            FakeDiscovery(
                FakeDiscoveryType.TEST_FAILURE,
                "Urgent failure",
                "desc",
                "urgent",
            ),
            FakeDiscovery(
                FakeDiscoveryType.TEST_FAILURE,
                "High failure",
                "desc",
                "high",
            ),
        ]

        result = svc._prioritize(discoveries)
        assert result[0].title == "Urgent failure"
        assert result[1].title == "High failure"
        assert result[2].title == "Low-priority failure"

    def test_caps_at_max_tasks(self, tmp_path):
        """Should not return more than MAX_TASKS_PER_NIGHT."""
        svc = _make_service(tmp_path)

        discoveries = [
            FakeDiscovery(
                FakeDiscoveryType.TEST_FAILURE,
                f"Task {i}",
                "desc",
                "medium",
            )
            for i in range(10)
        ]

        result = svc._prioritize(discoveries)
        assert len(result) == svc.MAX_TASKS_PER_NIGHT

    def test_empty_list(self, tmp_path):
        """Empty discoveries should return empty."""
        svc = _make_service(tmp_path)
        assert svc._prioritize([]) == []


# ---------------------------------------------------------------------------
# TestTaskSizeEstimation
# ---------------------------------------------------------------------------


class TestTaskSizeEstimation:
    """Verify task size heuristic."""

    def test_small_task(self, tmp_path):
        """Few files + short description = small."""
        svc = _make_service(tmp_path)
        d = FakeDiscovery(
            FakeDiscoveryType.TEST_FAILURE,
            "Fix one test",
            "Short description",
            "medium",
            relevant_files=["a.py"],
        )
        assert svc._estimate_task_size(d) == "small"

    def test_small_boundary_two_files(self, tmp_path):
        """Exactly 2 files and < 300 chars is still small."""
        svc = _make_service(tmp_path)
        d = FakeDiscovery(
            FakeDiscoveryType.TEST_FAILURE,
            "Fix",
            "x" * 299,
            "medium",
            relevant_files=["a.py", "b.py"],
        )
        assert svc._estimate_task_size(d) == "small"

    def test_medium_task(self, tmp_path):
        """More files or longer description = medium."""
        svc = _make_service(tmp_path)
        d = FakeDiscovery(
            FakeDiscoveryType.CODE_QUALITY,
            "Refactor module",
            "x" * 400,
            "medium",
            relevant_files=["a.py", "b.py", "c.py"],
        )
        assert svc._estimate_task_size(d) == "medium"

    def test_medium_boundary_five_files(self, tmp_path):
        """Exactly 5 files and < 500 chars is medium."""
        svc = _make_service(tmp_path)
        d = FakeDiscovery(
            FakeDiscoveryType.CODE_QUALITY,
            "Refactor",
            "x" * 499,
            "medium",
            relevant_files=["a.py", "b.py", "c.py", "d.py", "e.py"],
        )
        assert svc._estimate_task_size(d) == "medium"

    def test_large_task(self, tmp_path):
        """Many files or very long description = large."""
        svc = _make_service(tmp_path)
        d = FakeDiscovery(
            FakeDiscoveryType.CODE_QUALITY,
            "Major overhaul",
            "x" * 600,
            "medium",
            relevant_files=[f"{i}.py" for i in range(8)],
        )
        assert svc._estimate_task_size(d) == "large"

    def test_large_by_file_count_alone(self, tmp_path):
        """6+ files makes it large even with short description."""
        svc = _make_service(tmp_path)
        d = FakeDiscovery(
            FakeDiscoveryType.CODE_QUALITY,
            "Fix",
            "short",
            "medium",
            relevant_files=[f"{i}.py" for i in range(6)],
        )
        assert svc._estimate_task_size(d) == "large"

    def test_large_by_description_alone(self, tmp_path):
        """500+ chars makes it large even with few files."""
        svc = _make_service(tmp_path)
        d = FakeDiscovery(
            FakeDiscoveryType.CODE_QUALITY,
            "Fix",
            "x" * 500,
            "medium",
            relevant_files=["a.py"],
        )
        assert svc._estimate_task_size(d) == "large"


# ---------------------------------------------------------------------------
# TestReportPersistence
# ---------------------------------------------------------------------------


class TestReportPersistence:
    """Verify report save/load round-trip."""

    def test_save_and_load_report(self, tmp_path):
        """Save a report, then load it back and verify contents."""
        svc = _make_service(tmp_path)

        report = NightReport(
            started_at="2026-03-09T00:00:00+00:00",
            completed_at="2026-03-09T01:00:00+00:00",
            tasks_attempted=2,
            tasks_succeeded=1,
            tasks_failed=1,
            total_files_changed=5,
            total_duration_seconds=120.0,
            discoveries_count=3,
            skipped_count=1,
            results=[
                ImprovementTaskResult(
                    task_title="Fix test",
                    discovery_type="test_failure",
                    success=True,
                    files_changed=2,
                    test_passed=True,
                    merged=True,
                    duration_seconds=40.0,
                ),
                ImprovementTaskResult(
                    task_title="Fix log error",
                    discovery_type="log_error",
                    success=False,
                    files_changed=3,
                    test_passed=False,
                    merged=False,
                    error_message="Tests failed",
                    duration_seconds=80.0,
                    todo_id="abc123",
                ),
            ],
        )

        filepath = svc._save_report(report)
        assert Path(filepath).exists()

        loaded = svc.get_latest_report()
        assert loaded is not None
        assert loaded.tasks_attempted == 2
        assert loaded.tasks_succeeded == 1
        assert loaded.tasks_failed == 1
        assert loaded.total_files_changed == 5
        assert loaded.discoveries_count == 3
        assert loaded.skipped_count == 1
        assert len(loaded.results) == 2
        assert loaded.results[0].task_title == "Fix test"
        assert loaded.results[0].success is True
        assert loaded.results[1].error_message == "Tests failed"
        assert loaded.results[1].todo_id == "abc123"

    def test_get_latest_report_empty_dir(self, tmp_path):
        """No reports dir should return None."""
        svc = _make_service(tmp_path)
        svc.REPORT_DIR = tmp_path / "nonexistent"
        assert svc.get_latest_report() is None

    def test_get_latest_report_empty_existing_dir(self, tmp_path):
        """Empty reports dir should return None."""
        svc = _make_service(tmp_path)
        svc.REPORT_DIR.mkdir(parents=True, exist_ok=True)
        assert svc.get_latest_report() is None

    def test_get_latest_returns_most_recent(self, tmp_path):
        """With multiple reports, should return the newest."""
        svc = _make_service(tmp_path)
        svc.REPORT_DIR.mkdir(parents=True, exist_ok=True)

        # Write two reports with different timestamps
        old_report = NightReport(
            started_at="2026-03-08T00:00:00",
            completed_at="2026-03-08T01:00:00",
            tasks_attempted=1,
            tasks_succeeded=1,
            tasks_failed=0,
            total_files_changed=1,
            total_duration_seconds=30.0,
        )
        (svc.REPORT_DIR / "20260308T000000Z.json").write_text(
            json.dumps(old_report.to_dict(), indent=2)
        )

        new_report = NightReport(
            started_at="2026-03-09T00:00:00",
            completed_at="2026-03-09T01:00:00",
            tasks_attempted=3,
            tasks_succeeded=2,
            tasks_failed=1,
            total_files_changed=7,
            total_duration_seconds=200.0,
        )
        (svc.REPORT_DIR / "20260309T000000Z.json").write_text(
            json.dumps(new_report.to_dict(), indent=2)
        )

        loaded = svc.get_latest_report()
        assert loaded is not None
        assert loaded.tasks_attempted == 3
        assert loaded.total_files_changed == 7


# ---------------------------------------------------------------------------
# TestNightReport
# ---------------------------------------------------------------------------


class TestNightReport:
    """Verify NightReport serialization helpers."""

    def test_to_dict(self):
        """Verify to_dict serialization."""
        report = NightReport(
            started_at="2026-03-09T00:00:00",
            completed_at="2026-03-09T01:00:00",
            tasks_attempted=2,
            tasks_succeeded=1,
            tasks_failed=1,
            total_files_changed=3,
            total_duration_seconds=120.0,
        )
        d = report.to_dict()
        assert d["tasks_attempted"] == 2
        assert d["tasks_succeeded"] == 1
        assert d["tasks_failed"] == 1
        assert d["total_files_changed"] == 3
        assert d["total_duration_seconds"] == 120.0
        assert isinstance(d["results"], list)
        assert len(d["results"]) == 0

    def test_to_dict_with_results(self):
        """Verify to_dict includes result entries."""
        report = NightReport(
            started_at="2026-03-09T00:00:00",
            completed_at="2026-03-09T01:00:00",
            tasks_attempted=1,
            tasks_succeeded=1,
            tasks_failed=0,
            total_files_changed=2,
            total_duration_seconds=60.0,
            results=[
                ImprovementTaskResult(
                    task_title="Fix thing",
                    discovery_type="test_failure",
                    success=True,
                    files_changed=2,
                    test_passed=True,
                    merged=True,
                    todo_id="t1",
                ),
            ],
        )
        d = report.to_dict()
        assert len(d["results"]) == 1
        assert d["results"][0]["task_title"] == "Fix thing"
        assert d["results"][0]["todo_id"] == "t1"

    def test_to_summary_text(self):
        """Verify human-readable summary."""
        report = NightReport(
            started_at="2026-03-09T00:00:00",
            completed_at="2026-03-09T01:00:00",
            tasks_attempted=1,
            tasks_succeeded=1,
            tasks_failed=0,
            total_files_changed=2,
            total_duration_seconds=60.0,
            discoveries_count=3,
            skipped_count=2,
        )
        text = report.to_summary_text()
        assert "Succeeded: 1" in text
        assert "Failed: 0" in text
        assert "Skipped: 2" in text
        assert "Discovered 3 issues" in text
        assert "60.0s" in text

    def test_to_summary_text_with_results(self):
        """Verify summary includes result lines and error details."""
        report = NightReport(
            started_at="2026-03-09T00:00:00",
            completed_at="2026-03-09T01:00:00",
            tasks_attempted=2,
            tasks_succeeded=1,
            tasks_failed=1,
            total_files_changed=4,
            total_duration_seconds=90.0,
            results=[
                ImprovementTaskResult(
                    task_title="Good fix",
                    discovery_type="test_failure",
                    success=True,
                    files_changed=2,
                    test_passed=True,
                    merged=True,
                ),
                ImprovementTaskResult(
                    task_title="Bad fix",
                    discovery_type="log_error",
                    success=False,
                    files_changed=2,
                    test_passed=False,
                    merged=False,
                    error_message="Tests exploded",
                ),
            ],
        )
        text = report.to_summary_text()
        assert "[OK] Good fix" in text
        assert "[FAIL] Bad fix" in text
        assert "Tests exploded" in text


# ---------------------------------------------------------------------------
# TestExecuteTask
# ---------------------------------------------------------------------------


class TestExecuteTask:
    """Verify the _execute_task pipeline."""

    @pytest.mark.asyncio
    async def test_successful_execution(self, tmp_path):
        """Happy path: create worktree, execute, test, merge, cleanup."""
        svc = _make_service(tmp_path)
        svc._runner.create_worktree = AsyncMock(
            return_value=("/tmp/wt-fix-test", "branch-fix-test")
        )
        svc._runner.execute_task = AsyncMock(
            return_value=FakeExecutionResult(success=True, files_changed=2)
        )
        svc._runner.run_tests = AsyncMock(
            return_value=FakeExecutionResult(success=True)
        )
        svc._runner.merge_to_main = AsyncMock(return_value=True)
        svc._runner.cleanup_worktree = AsyncMock()

        discovery = FakeDiscovery(
            FakeDiscoveryType.TEST_FAILURE,
            "Fix broken test",
            "The test_foo is failing",
            "high",
            relevant_files=["tests/test_foo.py"],
        )

        result = await svc._execute_task(discovery)
        assert result.success is True
        assert result.test_passed is True
        assert result.merged is True
        assert result.files_changed == 2
        assert result.error_message == ""
        svc._runner.cleanup_worktree.assert_awaited_once_with(
            "/tmp/wt-fix-test", "branch-fix-test"
        )

    @pytest.mark.asyncio
    async def test_execution_failure(self, tmp_path):
        """When execution itself fails, return failed result."""
        svc = _make_service(tmp_path)
        svc._runner.create_worktree = AsyncMock(
            return_value=("/tmp/wt-fail", "branch-fail")
        )
        svc._runner.execute_task = AsyncMock(
            return_value=FakeExecutionResult(
                success=False, stderr="Syntax error", files_changed=0
            )
        )
        svc._runner.cleanup_worktree = AsyncMock()

        discovery = FakeDiscovery(
            FakeDiscoveryType.LOG_ERROR,
            "Fix log error",
            "Some error",
            "medium",
        )

        result = await svc._execute_task(discovery)
        assert result.success is False
        assert result.test_passed is False
        assert result.merged is False
        assert "Syntax error" in result.error_message
        svc._runner.cleanup_worktree.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_test_failure_prevents_merge(self, tmp_path):
        """When tests fail, should not attempt merge."""
        svc = _make_service(tmp_path)
        svc._runner.create_worktree = AsyncMock(
            return_value=("/tmp/wt-test-fail", "branch-test-fail")
        )
        svc._runner.execute_task = AsyncMock(
            return_value=FakeExecutionResult(success=True, files_changed=1)
        )
        svc._runner.run_tests = AsyncMock(
            return_value=FakeExecutionResult(
                success=False, stderr="2 tests failed"
            )
        )
        svc._runner.merge_to_main = AsyncMock()
        svc._runner.cleanup_worktree = AsyncMock()

        discovery = FakeDiscovery(
            FakeDiscoveryType.TEST_FAILURE,
            "Fix test",
            "broken",
            "high",
        )

        result = await svc._execute_task(discovery)
        assert result.success is False
        assert result.test_passed is False
        assert result.merged is False
        svc._runner.merge_to_main.assert_not_awaited()
        svc._runner.cleanup_worktree.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_exception_returns_failed_result(self, tmp_path):
        """Unexpected exception should be caught and return a failed result."""
        svc = _make_service(tmp_path)
        svc._runner.create_worktree = AsyncMock(side_effect=RuntimeError("boom"))
        svc._runner.cleanup_worktree = AsyncMock()

        discovery = FakeDiscovery(
            FakeDiscoveryType.CODE_QUALITY,
            "Exploding task",
            "desc",
            "low",
        )

        result = await svc._execute_task(discovery)
        assert result.success is False
        assert "boom" in result.error_message

    @pytest.mark.asyncio
    async def test_cleanup_always_runs(self, tmp_path):
        """Worktree cleanup should run even if merge raises."""
        svc = _make_service(tmp_path)
        svc._runner.create_worktree = AsyncMock(
            return_value=("/tmp/wt-cleanup", "branch-cleanup")
        )
        svc._runner.execute_task = AsyncMock(
            return_value=FakeExecutionResult(success=True, files_changed=1)
        )
        svc._runner.run_tests = AsyncMock(
            return_value=FakeExecutionResult(success=True)
        )
        svc._runner.merge_to_main = AsyncMock(side_effect=RuntimeError("merge boom"))
        svc._runner.cleanup_worktree = AsyncMock()

        discovery = FakeDiscovery(
            FakeDiscoveryType.TEST_FAILURE,
            "Merge fail task",
            "desc",
            "high",
        )

        result = await svc._execute_task(discovery)
        assert result.success is False
        assert "merge boom" in result.error_message
        svc._runner.cleanup_worktree.assert_awaited_once_with(
            "/tmp/wt-cleanup", "branch-cleanup"
        )


# ---------------------------------------------------------------------------
# TestRunImprovementCycle
# ---------------------------------------------------------------------------


class TestRunImprovementCycle:
    """Verify the top-level orchestration loop."""

    @pytest.mark.asyncio
    async def test_cli_unavailable_returns_empty_report(self, tmp_path):
        """When Claude CLI is not available, return an empty report immediately."""
        svc = _make_service(tmp_path)
        svc._runner.check_available = AsyncMock(return_value=False)

        report = await svc.run_improvement_cycle()
        assert report.tasks_attempted == 0
        assert report.tasks_succeeded == 0

    @pytest.mark.asyncio
    async def test_full_cycle_with_discoveries(self, tmp_path):
        """End-to-end cycle: discover, prioritize, execute, report."""
        svc = _make_service(tmp_path)
        svc._runner.check_available = AsyncMock(return_value=True)

        discoveries = [
            FakeDiscovery(
                FakeDiscoveryType.TEST_FAILURE,
                "Fix test_foo",
                "test_foo fails",
                "high",
                relevant_files=["tests/test_foo.py"],
            ),
        ]
        svc._analyzer.run_full_analysis = AsyncMock(return_value=discoveries)

        svc._runner.create_worktree = AsyncMock(
            return_value=("/tmp/wt-fix", "branch-fix")
        )
        svc._runner.execute_task = AsyncMock(
            return_value=FakeExecutionResult(success=True, files_changed=1)
        )
        svc._runner.run_tests = AsyncMock(
            return_value=FakeExecutionResult(success=True)
        )
        svc._runner.merge_to_main = AsyncMock(return_value=True)
        svc._runner.cleanup_worktree = AsyncMock()

        report = await svc.run_improvement_cycle()
        assert report.tasks_attempted == 1
        assert report.tasks_succeeded == 1
        assert report.tasks_failed == 0
        assert report.discoveries_count == 1
        assert len(report.results) == 1
        assert report.results[0].success is True

    @pytest.mark.asyncio
    async def test_large_tasks_are_skipped(self, tmp_path):
        """Large tasks should be skipped, not executed."""
        svc = _make_service(tmp_path)
        svc._runner.check_available = AsyncMock(return_value=True)

        discoveries = [
            FakeDiscovery(
                FakeDiscoveryType.CODE_QUALITY,
                "Huge refactor",
                "x" * 600,
                "low",
                relevant_files=[f"{i}.py" for i in range(10)],
            ),
        ]
        svc._analyzer.run_full_analysis = AsyncMock(return_value=discoveries)

        report = await svc.run_improvement_cycle()
        assert report.tasks_attempted == 0
        assert report.skipped_count == 1

    @pytest.mark.asyncio
    async def test_report_is_saved_after_cycle(self, tmp_path):
        """A report file should exist after the cycle completes."""
        svc = _make_service(tmp_path)
        svc._runner.check_available = AsyncMock(return_value=True)
        svc._analyzer.run_full_analysis = AsyncMock(return_value=[])

        await svc.run_improvement_cycle()

        assert svc.REPORT_DIR.exists()
        files = list(svc.REPORT_DIR.glob("*.json"))
        assert len(files) == 1


# ---------------------------------------------------------------------------
# TestTodoStatusUpdate
# ---------------------------------------------------------------------------


class TestTodoStatusUpdate:
    """Verify todo integration for linked tasks."""

    @pytest.mark.asyncio
    async def test_marks_done_on_success(self, tmp_path):
        """When task succeeds, todo should be marked complete."""
        from jarvis.services.todo_service import TodoService

        db_path = str(tmp_path / "todos.db")
        todo_svc = TodoService(db_path=db_path, logger=MagicMock())
        item = todo_svc.create("Night fix target", priority="high")

        svc = _make_service(tmp_path)
        svc._todo_service = todo_svc

        await svc._update_todo_status(item.id, success=True)

        refreshed = todo_svc.get(item.id)
        assert refreshed is not None
        assert refreshed.status.value == "done"

    @pytest.mark.asyncio
    async def test_adds_retry_tag_on_failure(self, tmp_path):
        """When task fails, todo should get retry-night-agent tag."""
        from jarvis.services.todo_service import TodoService

        db_path = str(tmp_path / "todos.db")
        todo_svc = TodoService(db_path=db_path, logger=MagicMock())
        item = todo_svc.create("Failing fix", priority="medium", tags=["night-agent"])

        svc = _make_service(tmp_path)
        svc._todo_service = todo_svc

        await svc._update_todo_status(item.id, success=False)

        refreshed = todo_svc.get(item.id)
        assert refreshed is not None
        assert "retry-night-agent" in refreshed.tags
        assert "night-agent" in refreshed.tags  # original tag preserved

    @pytest.mark.asyncio
    async def test_no_duplicate_retry_tag(self, tmp_path):
        """If retry tag already exists, don't add it again."""
        from jarvis.services.todo_service import TodoService

        db_path = str(tmp_path / "todos.db")
        todo_svc = TodoService(db_path=db_path, logger=MagicMock())
        item = todo_svc.create(
            "Already retried",
            priority="medium",
            tags=["retry-night-agent"],
        )

        svc = _make_service(tmp_path)
        svc._todo_service = todo_svc

        await svc._update_todo_status(item.id, success=False)

        refreshed = todo_svc.get(item.id)
        assert refreshed is not None
        assert refreshed.tags.count("retry-night-agent") == 1

    @pytest.mark.asyncio
    async def test_handles_missing_todo(self, tmp_path):
        """Nonexistent todo_id should not crash."""
        from jarvis.services.todo_service import TodoService

        db_path = str(tmp_path / "todos.db")
        todo_svc = TodoService(db_path=db_path, logger=MagicMock())

        svc = _make_service(tmp_path)
        svc._todo_service = todo_svc

        # Should not raise
        await svc._update_todo_status("nonexistent-id", success=True)
        await svc._update_todo_status("nonexistent-id", success=False)

    @pytest.mark.asyncio
    async def test_handles_no_todo_service(self, tmp_path):
        """When no TodoService is configured, update is a no-op."""
        svc = _make_service(tmp_path)
        svc._todo_service = None

        # Should not raise
        await svc._update_todo_status("any-id", success=True)
