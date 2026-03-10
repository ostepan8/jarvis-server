"""Autonomous self-improvement orchestration service.

Discovers issues via SystemAnalyzer, prioritizes them, executes fixes
via ClaudeCodeRunner (worktree-per-task), runs tests, and merges
successful changes back to main.  Produces a NightReport summarizing
what was attempted, what succeeded, and what failed.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, ClassVar, Dict, Optional

NightProgressCallback = Optional[Callable[[str, str, dict], None]]

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
    pr_url: Optional[str] = None
    branch_name: Optional[str] = None


@dataclass
class NightCycleState:
    """Persistent state for resumable night improvement cycles."""

    cycle_id: str
    started_at: str
    status: str  # "in_progress" | "paused"
    discoveries: list[dict]
    completed_results: list[dict]
    current_task_index: int
    skipped_count: int

    STATE_FILE: ClassVar[Path] = Path.home() / ".jarvis" / "night_state.json"
    STALE_HOURS: ClassVar[int] = 24

    def save(self) -> None:
        """Atomic write to disk."""
        self.STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.STATE_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps({
            "cycle_id": self.cycle_id,
            "started_at": self.started_at,
            "status": self.status,
            "discoveries": self.discoveries,
            "completed_results": self.completed_results,
            "current_task_index": self.current_task_index,
            "skipped_count": self.skipped_count,
        }, indent=2))
        os.replace(str(tmp), str(self.STATE_FILE))

    @classmethod
    def load(cls) -> Optional["NightCycleState"]:
        """Load from disk. Returns None if missing, corrupt, or stale."""
        if not cls.STATE_FILE.exists():
            return None
        try:
            data = json.loads(cls.STATE_FILE.read_text())
            state = cls(
                cycle_id=data["cycle_id"],
                started_at=data["started_at"],
                status=data["status"],
                discoveries=data["discoveries"],
                completed_results=data["completed_results"],
                current_task_index=data["current_task_index"],
                skipped_count=data["skipped_count"],
            )
            if state.is_stale():
                cls.clear()
                return None
            return state
        except (json.JSONDecodeError, KeyError):
            return None

    @classmethod
    def clear(cls) -> None:
        """Remove state file."""
        if cls.STATE_FILE.exists():
            cls.STATE_FILE.unlink()

    def is_stale(self) -> bool:
        """True if started_at is older than STALE_HOURS."""
        try:
            started = datetime.fromisoformat(self.started_at)
            age = datetime.now(timezone.utc) - started
            return age.total_seconds() > self.STALE_HOURS * 3600
        except (ValueError, TypeError):
            return True


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
                    "pr_url": r.pr_url,
                    "branch_name": r.branch_name,
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
                if r.pr_url:
                    lines.append(f"         PR: {r.pr_url}")
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
        use_prs: bool = True,
    ) -> None:
        self._project_root = project_root
        self._logger = logger or JarvisLogger()
        self._todo_service = todo_service
        self._use_prs = use_prs
        self._analyzer = SystemAnalyzer(project_root, log_db_path, todo_service, logger)
        self._runner = ClaudeCodeRunner(project_root, logger=logger)

    @staticmethod
    def _emit(callback: NightProgressCallback, event: str, message: str, data: dict | None = None) -> None:
        """Fire a progress callback if one is registered."""
        if callback:
            callback(event, message, data or {})

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def discover(self) -> list[Discovery]:
        """Run full system analysis and return discoveries."""
        return await self._discover()

    def get_analyzer(self) -> SystemAnalyzer:
        """Return the underlying SystemAnalyzer instance."""
        return self._analyzer

    async def run_improvement_cycle(self, progress_callback: NightProgressCallback = None) -> NightReport:
        """Main entry point — run one full improvement cycle."""

        # Check for a paused cycle that can be resumed
        state = NightCycleState.load()
        if state and state.status == "paused":
            return await self._resume_cycle(state, progress_callback)

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

        # Create and persist initial state
        cycle_id = started_at
        state = NightCycleState(
            cycle_id=cycle_id,
            started_at=started_at,
            status="in_progress",
            discoveries=[d.to_dict() for d in prioritized],
            completed_results=[],
            current_task_index=0,
            skipped_count=0,
        )
        state.save()

        self._emit(progress_callback, "cycle_start", "Scanning for issues...", {"cycle_id": cycle_id})
        self._emit(progress_callback, "discovery_complete",
            f"Discovered {discoveries_count} issues, executing {len(prioritized)}.", {
                "count": discoveries_count, "executing": len(prioritized)
            })

        # Step 3: Execute each task
        results: list[ImprovementTaskResult] = []
        skipped = 0
        for i, discovery in enumerate(prioritized):
            size = self._estimate_task_size(discovery)
            if size == "large":
                self._logger.log(
                    "INFO",
                    "Task skipped (too large)",
                    discovery.title,
                )
                skipped += 1
                state.skipped_count = skipped
                state.current_task_index = i + 1
                state.save()
                self._emit(progress_callback, "task_skip", f"Skipped: {discovery.title}", {"title": discovery.title})
                continue

            self._emit(progress_callback, "task_start", f"Working on: {discovery.title}", {
                "index": i, "total": len(prioritized), "title": discovery.title
            })
            state.current_task_index = i
            state.save()

            result = await self._execute_task(discovery)
            results.append(result)

            state.completed_results.append({
                "task_title": result.task_title,
                "discovery_type": result.discovery_type,
                "success": result.success,
                "files_changed": result.files_changed,
                "test_passed": result.test_passed,
                "merged": result.merged,
                "error_message": result.error_message,
                "duration_seconds": result.duration_seconds,
                "todo_id": result.todo_id,
                "pr_url": result.pr_url,
                "branch_name": result.branch_name,
            })
            state.current_task_index = i + 1
            state.save()

            if result.success:
                self._emit(progress_callback, "task_success", "Done.", {
                    "title": result.task_title, "pr_url": result.pr_url
                })
            else:
                self._emit(progress_callback, "task_failure", f"Failed: {result.error_message}", {
                    "title": result.task_title, "error": result.error_message
                })

            # Update todo status if linked
            if discovery.todo_id and self._todo_service:
                await self._update_todo_status(discovery.todo_id, result.success)

        # Step 4: Build report
        completed_at = datetime.now(timezone.utc).isoformat()
        total_duration = time.monotonic() - cycle_start
        succeeded = sum(1 for r in results if r.success)

        report = NightReport(
            started_at=started_at,
            completed_at=completed_at,
            tasks_attempted=len(results),
            tasks_succeeded=succeeded,
            tasks_failed=sum(1 for r in results if not r.success),
            total_files_changed=sum(r.files_changed for r in results),
            total_duration_seconds=total_duration,
            results=results,
            discoveries_count=discoveries_count,
            skipped_count=skipped,
        )

        self._save_report(report)
        NightCycleState.clear()
        self._emit(progress_callback, "cycle_complete",
            f"Cycle complete: {succeeded}/{len(results)} succeeded", {
                "attempted": len(results), "succeeded": succeeded
            })
        return report

    def pause_cycle(self, progress_callback: NightProgressCallback = None) -> None:
        """Save current cycle state as paused. Called on cancellation."""
        state = NightCycleState.load()
        if state and state.status == "in_progress":
            state.status = "paused"
            state.save()
            remaining = len(state.discoveries) - state.current_task_index
            self._emit(progress_callback, "cycle_paused",
                f"Pausing — {remaining} tasks remaining", {
                    "completed": state.current_task_index, "remaining": remaining
                })

    async def _resume_cycle(self, state: NightCycleState, progress_callback: NightProgressCallback = None) -> NightReport:
        """Resume a paused improvement cycle from saved state."""
        from .system_analyzer import Discovery as DiscoveryCls

        cycle_start = time.monotonic()
        discoveries = [DiscoveryCls.from_dict(d) for d in state.discoveries]
        completed_results = [
            ImprovementTaskResult(**r) for r in state.completed_results
        ]

        remaining = len(discoveries) - state.current_task_index
        self._emit(progress_callback, "cycle_resumed", f"Resuming — {remaining} tasks remaining", {
            "cycle_id": state.cycle_id, "from_task": state.current_task_index
        })

        # Update state to in_progress
        state.status = "in_progress"
        state.save()

        skipped = state.skipped_count
        results = list(completed_results)

        for i, discovery in enumerate(discoveries[state.current_task_index:], start=state.current_task_index):
            size = self._estimate_task_size(discovery)
            if size == "large":
                skipped += 1
                state.skipped_count = skipped
                state.current_task_index = i + 1
                state.save()
                self._emit(progress_callback, "task_skip", f"Skipped: {discovery.title}", {"title": discovery.title})
                continue

            total = len(discoveries)
            self._emit(progress_callback, "task_start", f"Working on: {discovery.title}", {
                "index": i, "total": total, "title": discovery.title
            })

            state.current_task_index = i
            state.save()

            result = await self._execute_task(discovery)
            results.append(result)

            state.completed_results.append({
                "task_title": result.task_title,
                "discovery_type": result.discovery_type,
                "success": result.success,
                "files_changed": result.files_changed,
                "test_passed": result.test_passed,
                "merged": result.merged,
                "error_message": result.error_message,
                "duration_seconds": result.duration_seconds,
                "todo_id": result.todo_id,
                "pr_url": result.pr_url,
                "branch_name": result.branch_name,
            })
            state.current_task_index = i + 1
            state.save()

            if result.success:
                self._emit(progress_callback, "task_success", "Done.", {
                    "title": result.task_title, "pr_url": result.pr_url
                })
            else:
                self._emit(progress_callback, "task_failure", f"Failed: {result.error_message}", {
                    "title": result.task_title, "error": result.error_message
                })

            if discovery.todo_id and self._todo_service:
                await self._update_todo_status(discovery.todo_id, result.success)

        completed_at = datetime.now(timezone.utc).isoformat()
        total_duration = time.monotonic() - cycle_start
        # Add duration from completed results that happened before pause
        total_duration += sum(r.duration_seconds for r in completed_results)

        succeeded = sum(1 for r in results if r.success)
        failed = sum(1 for r in results if not r.success)

        report = NightReport(
            started_at=state.started_at,
            completed_at=completed_at,
            tasks_attempted=len(results),
            tasks_succeeded=succeeded,
            tasks_failed=failed,
            total_files_changed=sum(r.files_changed for r in results),
            total_duration_seconds=total_duration,
            results=results,
            discoveries_count=len(discoveries),
            skipped_count=skipped,
        )

        self._save_report(report)
        NightCycleState.clear()

        self._emit(progress_callback, "cycle_complete",
            f"Cycle complete: {succeeded}/{len(results)} succeeded", {
                "attempted": len(results), "succeeded": succeeded
            })

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

        Creates a worktree, runs the fix, tests, then either pushes a PR
        (when ``use_prs`` is enabled) or merges directly to main.
        """
        task_start = time.monotonic()
        worktree_path: Optional[str] = None
        branch_name: Optional[str] = None
        keep_branch = False

        try:
            worktree_path, branch_name = await self._runner.create_worktree(
                discovery.title
            )

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
                    branch_name=branch_name,
                )

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
                    branch_name=branch_name,
                )

            # --- PR flow vs legacy merge ---
            if self._use_prs:
                return await self._finish_with_pr(
                    discovery, exec_result, worktree_path, branch_name, task_start
                )

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
                branch_name=branch_name,
            )

        except asyncio.CancelledError:
            raise
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
                branch_name=branch_name,
            )
        finally:
            # _finish_with_pr sets this when the branch has been pushed
            keep_branch = getattr(self, "_keep_branch_hint", False)
            self._keep_branch_hint = False
            if worktree_path and branch_name:
                try:
                    await self._runner.cleanup_worktree(
                        worktree_path, branch_name, keep_branch=keep_branch
                    )
                except Exception as cleanup_err:
                    self._logger.log(
                        "WARNING",
                        "Worktree cleanup failed",
                        f"{worktree_path}: {cleanup_err}",
                    )

    async def _finish_with_pr(
        self,
        discovery: Discovery,
        exec_result: Any,
        worktree_path: str,
        branch_name: str,
        task_start: float,
    ) -> ImprovementTaskResult:
        """Push the branch and create a pull request.

        Sets ``keep_branch`` on the enclosing ``_execute_task`` frame
        so the finally block preserves the branch for the open PR.
        """
        push_result = await self._runner.push_branch(worktree_path, branch_name)

        if not push_result.success:
            return ImprovementTaskResult(
                task_title=discovery.title,
                discovery_type=str(discovery.discovery_type),
                success=False,
                files_changed=exec_result.files_changed,
                test_passed=True,
                merged=False,
                error_message=push_result.stderr or "Push failed",
                duration_seconds=time.monotonic() - task_start,
                todo_id=discovery.todo_id,
                branch_name=branch_name,
            )

        title = self._build_pr_title(discovery)
        body = self._build_pr_body(
            discovery, exec_result.files_changed, test_passed=True
        )
        pr_result = await self._runner.create_pull_request(
            worktree_path, branch_name, title, body
        )

        pr_url = pr_result.stdout.strip() if pr_result.success else None

        # Whether or not the PR was created, the branch is on the remote
        # so we keep it locally too.
        # Mutate the keep_branch flag in the caller's finally block
        # by storing it on the instance temporarily.
        self._keep_branch_hint = True

        return ImprovementTaskResult(
            task_title=discovery.title,
            discovery_type=str(discovery.discovery_type),
            success=True,
            files_changed=exec_result.files_changed,
            test_passed=True,
            merged=False,
            error_message="" if pr_url else "PR creation failed (branch pushed)",
            duration_seconds=time.monotonic() - task_start,
            todo_id=discovery.todo_id,
            pr_url=pr_url,
            branch_name=branch_name,
        )

    # ------------------------------------------------------------------
    # PR helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_pr_title(discovery: Discovery) -> str:
        """Format a commit-style PR title, truncated to 72 chars."""
        prefix = "fix(night-agent): "
        max_title_len = 72 - len(prefix)
        title = discovery.title[:max_title_len]
        return f"{prefix}{title}"

    @staticmethod
    def _build_pr_body(
        discovery: Discovery, files_changed: int, test_passed: bool
    ) -> str:
        """Build structured markdown for the PR description."""
        files_section = ""
        if discovery.relevant_files:
            files_section = "\n".join(
                f"- `{f}`" for f in discovery.relevant_files
            )
        else:
            files_section = "_No specific files identified._"

        test_status = "All passing" if test_passed else "Some failures"

        return (
            "## Night Agent Auto-Fix\n"
            "\n"
            f"**Discovery type:** {discovery.discovery_type}\n"
            f"**Priority:** {discovery.priority}\n"
            f"**Files changed:** {files_changed}\n"
            f"**Tests:** {test_status}\n"
            "\n"
            "### Description\n"
            f"{discovery.description}\n"
            "\n"
            "### Relevant files\n"
            f"{files_section}\n"
            "\n"
            "---\n"
            "_Automatically generated by the Jarvis self-improvement agent._\n"
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
                pr_url=r.get("pr_url"),
                branch_name=r.get("branch_name"),
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
