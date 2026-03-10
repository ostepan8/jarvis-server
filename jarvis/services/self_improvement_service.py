"""Autonomous self-improvement orchestration service.

Discovers issues via SystemAnalyzer, prioritizes them, executes fixes
via ClaudeCodeRunner (worktree-per-task), runs tests, and merges
successful changes back to main.  Produces a NightReport summarizing
what was attempted, what succeeded, and what failed.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..logging import JarvisLogger
from ..services.todo_service import TodoService
from .system_analyzer import SystemAnalyzer, Discovery, DiscoveryType
from .claude_code_runner import ClaudeCodeRunner


# ---------------------------------------------------------------------------
# Priority mapping — lower number = higher priority
# ---------------------------------------------------------------------------

PRIORITY_ORDER: Dict[DiscoveryType, int] = {
    DiscoveryType.TEST_FAILURE: 0,
    DiscoveryType.LOG_ERROR: 1,
    DiscoveryType.MANUAL_TODO: 2,
    DiscoveryType.CODE_QUALITY: 3,
}

# Priority string ordering (for secondary sort within the same type)
_PRIORITY_STRING_ORDER: Dict[str, int] = {
    "urgent": 0,
    "high": 1,
    "medium": 2,
    "low": 3,
}


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class ImprovementTaskResult:
    """Outcome of a single improvement task."""

    task_title: str
    discovery_type: str
    success: bool
    files_changed: int
    test_passed: bool
    merged: bool
    error_message: str = ""
    duration_seconds: float = 0.0
    todo_id: Optional[str] = None


@dataclass
class NightReport:
    """Aggregated summary of one nightly improvement cycle."""

    started_at: str  # ISO timestamp
    completed_at: str  # ISO timestamp
    tasks_attempted: int
    tasks_succeeded: int
    tasks_failed: int
    total_files_changed: int
    total_duration_seconds: float
    results: list[ImprovementTaskResult] = field(default_factory=list)
    discoveries_count: int = 0
    skipped_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for JSON storage."""
        return {
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "tasks_attempted": self.tasks_attempted,
            "tasks_succeeded": self.tasks_succeeded,
            "tasks_failed": self.tasks_failed,
            "total_files_changed": self.total_files_changed,
            "total_duration_seconds": self.total_duration_seconds,
            "discoveries_count": self.discoveries_count,
            "skipped_count": self.skipped_count,
            "results": [
                {
                    "task_title": r.task_title,
                    "discovery_type": r.discovery_type,
                    "success": r.success,
                    "files_changed": r.files_changed,
                    "test_passed": r.test_passed,
                    "merged": r.merged,
                    "error_message": r.error_message,
                    "duration_seconds": r.duration_seconds,
                    "todo_id": r.todo_id,
                }
                for r in self.results
            ],
        }

    def to_summary_text(self) -> str:
        """Human-readable summary for morning report."""
        lines = [
            "Night improvement cycle completed.",
            f"Discovered {self.discoveries_count} issues, attempted {self.tasks_attempted} tasks.",
            f"Succeeded: {self.tasks_succeeded}, Failed: {self.tasks_failed}, Skipped: {self.skipped_count}.",
            f"Total files changed: {self.total_files_changed}.",
            f"Duration: {self.total_duration_seconds:.1f}s.",
        ]
        if self.results:
            lines.append("")
            lines.append("Results:")
            for r in self.results:
                status = "OK" if r.success else "FAIL"
                lines.append(f"  [{status}] {r.task_title} ({r.discovery_type})")
                if r.error_message:
                    lines.append(f"         Error: {r.error_message}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class SelfImprovementService:
    """Orchestrates the full autonomous improvement cycle.

    1. Discover issues (test failures, log errors, todos, code quality).
    2. Prioritize them.
    3. Execute each fix in an isolated worktree via Claude Code CLI.
    4. Run tests, merge successes, report results.
    """

    MAX_TASKS_PER_NIGHT: int = 5
    REPORT_DIR: Path = Path.home() / ".jarvis" / "night_reports"

    def __init__(
        self,
        project_root: str,
        todo_service: Optional[TodoService] = None,
        log_db_path: str = "jarvis_logs.db",
        logger: Optional[JarvisLogger] = None,
    ) -> None:
        self._project_root = project_root
        self._logger = logger or JarvisLogger()
        self._todo_service = todo_service
        self._analyzer = SystemAnalyzer(project_root, log_db_path, todo_service, logger)
        self._runner = ClaudeCodeRunner(project_root, logger=logger)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run_improvement_cycle(self) -> NightReport:
        """Main entry point — run one full improvement cycle."""
        started_at = datetime.now(timezone.utc).isoformat()
        cycle_start = time.monotonic()

        # Pre-flight: ensure the Claude CLI is available
        if not await self._runner.check_available():
            self._logger.log(
                "WARNING",
                "Self-improvement skipped",
                "Claude CLI is not available",
            )
            return NightReport(
                started_at=started_at,
                completed_at=datetime.now(timezone.utc).isoformat(),
                tasks_attempted=0,
                tasks_succeeded=0,
                tasks_failed=0,
                total_files_changed=0,
                total_duration_seconds=0.0,
            )

        # Step 1: Discover issues
        discoveries = await self._discover()
        discoveries_count = len(discoveries)

        # Step 2: Prioritize and cap
        prioritized = self._prioritize(discoveries)

        # Step 3: Execute each task
        results: list[ImprovementTaskResult] = []
        skipped = 0
        for discovery in prioritized:
            size = self._estimate_task_size(discovery)
            if size == "large":
                self._logger.log(
                    "INFO",
                    "Task skipped (too large)",
                    discovery.title,
                )
                skipped += 1
                continue

            result = await self._execute_task(discovery)
            results.append(result)

            # Update todo status if linked
            if discovery.todo_id and self._todo_service:
                await self._update_todo_status(discovery.todo_id, result.success)

        # Step 4: Build report
        completed_at = datetime.now(timezone.utc).isoformat()
        total_duration = time.monotonic() - cycle_start

        report = NightReport(
            started_at=started_at,
            completed_at=completed_at,
            tasks_attempted=len(results),
            tasks_succeeded=sum(1 for r in results if r.success),
            tasks_failed=sum(1 for r in results if not r.success),
            total_files_changed=sum(r.files_changed for r in results),
            total_duration_seconds=total_duration,
            results=results,
            discoveries_count=discoveries_count,
            skipped_count=skipped,
        )

        self._save_report(report)
        return report

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    async def _discover(self) -> list[Discovery]:
        """Run full system analysis and return discoveries."""
        return await self._analyzer.run_full_analysis()

    # ------------------------------------------------------------------
    # Prioritization
    # ------------------------------------------------------------------

    def _prioritize(self, discoveries: list[Discovery]) -> list[Discovery]:
        """Sort discoveries by type priority, then by urgency string.

        Returns at most MAX_TASKS_PER_NIGHT items.
        """
        if not discoveries:
            return []

        def sort_key(d: Discovery) -> tuple[int, int]:
            type_order = PRIORITY_ORDER.get(d.discovery_type, 99)
            string_order = _PRIORITY_STRING_ORDER.get(d.priority, 99)
            return (type_order, string_order)

        sorted_discoveries = sorted(discoveries, key=sort_key)
        return sorted_discoveries[: self.MAX_TASKS_PER_NIGHT]

    # ------------------------------------------------------------------
    # Size estimation
    # ------------------------------------------------------------------

    def _estimate_task_size(self, discovery: Discovery) -> str:
        """Estimate task complexity: 'small', 'medium', or 'large'.

        Only 'large' tasks are skipped by the cycle.
        """
        num_files = len(discovery.relevant_files)
        desc_len = len(discovery.description)

        if num_files <= 2 and desc_len < 300:
            return "small"
        if num_files <= 5 and desc_len < 500:
            return "medium"
        return "large"

    # ------------------------------------------------------------------
    # Task execution
    # ------------------------------------------------------------------

    async def _execute_task(self, discovery: Discovery) -> ImprovementTaskResult:
        """Execute a single improvement task in an isolated worktree.

        Creates a worktree, runs the fix, tests, merges on success,
        and always cleans up the worktree.
        """
        task_start = time.monotonic()
        worktree_path: Optional[str] = None
        branch_name: Optional[str] = None

        try:
            # Create an isolated worktree — returns (path, branch)
            worktree_path, branch_name = await self._runner.create_worktree(
                discovery.title
            )

            # Execute the fix inside the worktree
            exec_result = await self._runner.execute_task(
                discovery.description,
                discovery.relevant_files,
                worktree_path,
            )

            if not exec_result.success:
                return ImprovementTaskResult(
                    task_title=discovery.title,
                    discovery_type=str(discovery.discovery_type),
                    success=False,
                    files_changed=exec_result.files_changed,
                    test_passed=False,
                    merged=False,
                    error_message=exec_result.stderr or "Execution failed",
                    duration_seconds=time.monotonic() - task_start,
                    todo_id=discovery.todo_id,
                )

            # Run tests in the worktree
            test_result = await self._runner.run_tests(worktree_path)

            if not test_result.success:
                return ImprovementTaskResult(
                    task_title=discovery.title,
                    discovery_type=str(discovery.discovery_type),
                    success=False,
                    files_changed=exec_result.files_changed,
                    test_passed=False,
                    merged=False,
                    error_message=test_result.stderr or "Tests failed",
                    duration_seconds=time.monotonic() - task_start,
                    todo_id=discovery.todo_id,
                )

            # Merge to main
            merged = await self._runner.merge_to_main(worktree_path, branch_name)

            return ImprovementTaskResult(
                task_title=discovery.title,
                discovery_type=str(discovery.discovery_type),
                success=merged,
                files_changed=exec_result.files_changed,
                test_passed=True,
                merged=merged,
                error_message="" if merged else "Merge failed",
                duration_seconds=time.monotonic() - task_start,
                todo_id=discovery.todo_id,
            )

        except Exception as exc:
            return ImprovementTaskResult(
                task_title=discovery.title,
                discovery_type=str(discovery.discovery_type),
                success=False,
                files_changed=0,
                test_passed=False,
                merged=False,
                error_message=str(exc),
                duration_seconds=time.monotonic() - task_start,
                todo_id=discovery.todo_id,
            )
        finally:
            if worktree_path and branch_name:
                try:
                    await self._runner.cleanup_worktree(worktree_path, branch_name)
                except Exception as cleanup_err:
                    self._logger.log(
                        "WARNING",
                        "Worktree cleanup failed",
                        f"{worktree_path}: {cleanup_err}",
                    )

    # ------------------------------------------------------------------
    # Todo integration
    # ------------------------------------------------------------------

    async def _update_todo_status(self, todo_id: str, success: bool) -> None:
        """Update the linked todo item based on task outcome."""
        if not self._todo_service:
            return

        try:
            if success:
                self._todo_service.complete(todo_id)
            else:
                todo = self._todo_service.get(todo_id)
                if todo is None:
                    return
                tags = list(todo.tags)
                if "retry-night-agent" not in tags:
                    tags.append("retry-night-agent")
                self._todo_service.update(todo_id, tags=tags)
        except Exception as exc:
            self._logger.log(
                "WARNING",
                "Todo status update failed",
                f"{todo_id}: {exc}",
            )

    # ------------------------------------------------------------------
    # Report persistence
    # ------------------------------------------------------------------

    def _save_report(self, report: NightReport) -> str:
        """Persist report as JSON. Returns the file path."""
        self.REPORT_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        filepath = self.REPORT_DIR / f"{timestamp}.json"
        filepath.write_text(json.dumps(report.to_dict(), indent=2))
        return str(filepath)

    def get_latest_report(self) -> Optional[NightReport]:
        """Load the most recent night report, or None if none exist."""
        if not self.REPORT_DIR.exists():
            return None

        files = sorted(self.REPORT_DIR.glob("*.json"))
        if not files:
            return None

        data = json.loads(files[-1].read_text())
        results = [
            ImprovementTaskResult(
                task_title=r["task_title"],
                discovery_type=r["discovery_type"],
                success=r["success"],
                files_changed=r["files_changed"],
                test_passed=r["test_passed"],
                merged=r["merged"],
                error_message=r.get("error_message", ""),
                duration_seconds=r.get("duration_seconds", 0.0),
                todo_id=r.get("todo_id"),
            )
            for r in data.get("results", [])
        ]
        return NightReport(
            started_at=data["started_at"],
            completed_at=data["completed_at"],
            tasks_attempted=data["tasks_attempted"],
            tasks_succeeded=data["tasks_succeeded"],
            tasks_failed=data["tasks_failed"],
            total_files_changed=data["total_files_changed"],
            total_duration_seconds=data["total_duration_seconds"],
            results=results,
            discoveries_count=data.get("discoveries_count", 0),
            skipped_count=data.get("skipped_count", 0),
        )
