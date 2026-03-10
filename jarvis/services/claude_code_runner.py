"""Claude Code CLI runner for autonomous code modifications in git worktrees.

Wraps the Claude Code CLI as an async subprocess, providing safe execution
inside isolated git worktrees with denied-path enforcement and file-change
limits.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path
from typing import Optional

from ..core.errors import SafetyViolationError, WorktreeError
from ..logging import JarvisLogger


@dataclass
class ExecutionResult:
    """Result of a subprocess execution."""

    success: bool
    stdout: str
    stderr: str
    exit_code: int
    worktree_path: Optional[str] = None
    branch_name: Optional[str] = None
    files_changed: int = 0
    duration_seconds: float = 0.0


class ClaudeCodeRunner:
    """Runs Claude Code CLI tasks inside isolated git worktrees.

    Provides safety rails including denied-path checking, file-change limits,
    and timeout enforcement for every subprocess call.
    """

    MAX_CHANGED_FILES = 10
    MAX_EXECUTION_TIMEOUT = 300  # 5 minutes per task
    DENIED_PATH_PATTERNS = [
        "*.env",
        "*.pem",
        "*.key",
        "credentials*",
        "jarvis/core/system.py",
        "jarvis/agents/factory.py",
        "jarvis/core/config.py",
        "jarvis/agents/nlu_agent/__init__.py",
    ]

    def __init__(
        self,
        project_root: str,
        claude_binary: str = "claude",
        logger: Optional[JarvisLogger] = None,
    ) -> None:
        self.project_root = project_root
        self.claude_binary = claude_binary
        self.logger = logger

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def check_available(self) -> bool:
        """Return True if the Claude Code CLI is installed and runnable."""
        try:
            result = await self._run_subprocess(
                [self.claude_binary, "--version"], timeout=10
            )
            return result.exit_code == 0
        except Exception:
            return False

    async def create_worktree(self, task_name: str) -> tuple[str, str]:
        """Create an isolated git worktree for *task_name*.

        Returns:
            A ``(worktree_path, branch_name)`` tuple.

        Raises:
            WorktreeError: If the git command fails.
        """
        worktree_path = str(
            Path(self.project_root) / ".claude" / "worktrees" / f"night-{task_name}"
        )
        branch_name = f"worktree-night-{task_name}"

        if self.logger:
            self.logger.log(
                "INFO",
                "Creating worktree",
                f"{worktree_path} on branch {branch_name}",
            )

        result = await self._run_subprocess(
            ["git", "worktree", "add", worktree_path, "-b", branch_name],
            cwd=self.project_root,
            timeout=30,
        )

        if result.exit_code != 0:
            raise WorktreeError(
                f"Failed to create worktree: {result.stderr}",
                details={
                    "worktree_path": worktree_path,
                    "branch_name": branch_name,
                    "exit_code": result.exit_code,
                },
            )

        return worktree_path, branch_name

    async def execute_task(
        self,
        task_description: str,
        relevant_files: list[str],
        worktree_path: str,
    ) -> ExecutionResult:
        """Run a Claude Code task inside *worktree_path*.

        Raises:
            SafetyViolationError: If denied paths are touched or too many
                files are changed.
        """
        prompt = self._build_prompt(task_description, relevant_files)

        if self.logger:
            self.logger.log("INFO", "Executing Claude Code task", worktree_path)

        result = await self._run_subprocess(
            [
                self.claude_binary,
                "--print",
                "-p",
                prompt,
                "--max-turns",
                "25",
                "--verbose",
            ],
            cwd=worktree_path,
            timeout=self.MAX_EXECUTION_TIMEOUT,
        )

        # Determine which files were changed.
        diff_result = await self._run_subprocess(
            ["git", "diff", "--name-only", "HEAD"],
            cwd=worktree_path,
            timeout=15,
        )
        changed_files = [
            f for f in diff_result.stdout.strip().splitlines() if f.strip()
        ]

        # Also check staged but not-yet-committed changes.
        staged_result = await self._run_subprocess(
            ["git", "diff", "--name-only", "--cached", "HEAD"],
            cwd=worktree_path,
            timeout=15,
        )
        staged_files = [
            f for f in staged_result.stdout.strip().splitlines() if f.strip()
        ]
        all_changed = list(set(changed_files + staged_files))

        # Safety checks.
        if self._check_denied_paths(all_changed):
            raise SafetyViolationError(
                "Claude Code modified a denied file",
                details={"changed_files": all_changed},
            )

        if len(all_changed) > self.MAX_CHANGED_FILES:
            raise SafetyViolationError(
                f"Too many files changed ({len(all_changed)} > {self.MAX_CHANGED_FILES})",
                details={"changed_files": all_changed},
            )

        result.worktree_path = worktree_path
        result.files_changed = len(all_changed)
        return result

    async def run_tests(
        self,
        worktree_path: str,
        test_files: list[str] | None = None,
    ) -> ExecutionResult:
        """Run pytest inside *worktree_path*.

        If *test_files* are given they are appended to the pytest command,
        otherwise the full suite is executed.
        """
        cmd: list[str] = ["pytest", "-x", "--timeout=30", "-q"]
        if test_files:
            cmd.extend(test_files)

        if self.logger:
            self.logger.log("INFO", "Running tests", f"{worktree_path}: {' '.join(cmd)}")

        return await self._run_subprocess(
            cmd, cwd=worktree_path, timeout=self.MAX_EXECUTION_TIMEOUT
        )

    async def merge_to_main(self, worktree_path: str, branch_name: str) -> bool:
        """Merge *branch_name* into the current branch from *project_root*.

        Returns ``True`` on success. On merge conflict the merge is aborted
        and ``False`` is returned.
        """
        if self.logger:
            self.logger.log("INFO", "Merging branch", f"{branch_name} into main")

        result = await self._run_subprocess(
            ["git", "merge", branch_name, "--no-edit"],
            cwd=self.project_root,
            timeout=30,
        )

        if result.exit_code != 0:
            if self.logger:
                self.logger.log(
                    "WARNING",
                    "Merge conflict detected, aborting",
                    result.stderr,
                )
            await self._run_subprocess(
                ["git", "merge", "--abort"],
                cwd=self.project_root,
                timeout=15,
            )
            return False

        return True

    async def cleanup_worktree(
        self, worktree_path: str, branch_name: str
    ) -> None:
        """Remove the worktree directory and delete the local branch.

        Errors are logged but never raised so cleanup is best-effort.
        """
        remove_result = await self._run_subprocess(
            ["git", "worktree", "remove", "--force", worktree_path],
            cwd=self.project_root,
            timeout=15,
        )
        if remove_result.exit_code != 0 and self.logger:
            self.logger.log(
                "WARNING", "Worktree removal failed", remove_result.stderr
            )

        branch_result = await self._run_subprocess(
            ["git", "branch", "-D", branch_name],
            cwd=self.project_root,
            timeout=15,
        )
        if branch_result.exit_code != 0 and self.logger:
            self.logger.log(
                "WARNING", "Branch deletion failed", branch_result.stderr
            )

    # ------------------------------------------------------------------
    # Prompt construction
    # ------------------------------------------------------------------

    def _build_prompt(
        self, task_description: str, relevant_files: list[str]
    ) -> str:
        """Build the structured prompt sent to Claude Code."""
        if relevant_files:
            files_section = "\n".join(f"- {f}" for f in relevant_files)
        else:
            files_section = "No specific files identified. Explore as needed."

        return (
            "You are an autonomous code improvement agent for the Jarvis Server project.\n"
            "\n"
            "YOUR TASK:\n"
            f"{task_description}\n"
            "\n"
            "IMPORTANT CONSTRAINTS:\n"
            "- Make the MINIMUM changes necessary to fix the issue\n"
            "- NEVER modify these files: jarvis/core/system.py, jarvis/agents/factory.py, "
            "jarvis/core/config.py, jarvis/agents/nlu_agent/__init__.py\n"
            "- NEVER delete existing tests\n"
            "- NEVER modify .env files or files containing secrets\n"
            "- Maximum 10 files may be changed\n"
            "\n"
            "PROJECT CONVENTIONS:\n"
            "- All agents return AgentResponse (from jarvis.agents.response)\n"
            "- Use pytest + pytest-asyncio for tests\n"
            "- Async everywhere for handlers and network calls\n"
            "- Test files go in tests/test_{feature}.py\n"
            "\n"
            "RELEVANT FILES TO EXAMINE:\n"
            f"{files_section}\n"
            "\n"
            "INSTRUCTIONS:\n"
            "1. Read the relevant files to understand the issue\n"
            "2. Make the fix with minimal changes\n"
            "3. Add or update tests if appropriate\n"
            "4. Commit with format: type(scope): imperative description\n"
            "5. Do NOT push -- merge happens externally\n"
            "\n"
            "SELF-IMPROVEMENT API (if Jarvis server is running on localhost:8000):\n"
            "- POST /self-improvement/tests/run — run pytest: {\"test_files\": [...]}\n"
            "- GET /self-improvement/tests/{run_id} — poll for results\n"
            "- GET /self-improvement/context/{file_path} — read a project file\n"
            "- GET /self-improvement/discoveries — see discovered issues\n"
            "Use curl to call these. ALWAYS run tests after changes.\n"
        )

    # ------------------------------------------------------------------
    # Safety helpers
    # ------------------------------------------------------------------

    def _check_denied_paths(self, changed_files: list[str]) -> bool:
        """Return ``True`` if any *changed_files* match a denied pattern."""
        for filepath in changed_files:
            for pattern in self.DENIED_PATH_PATTERNS:
                if fnmatch(filepath, pattern):
                    return True
        return False

    # ------------------------------------------------------------------
    # Subprocess helper
    # ------------------------------------------------------------------

    async def _run_subprocess(
        self,
        cmd: list[str],
        cwd: str | None = None,
        timeout: int | None = None,
    ) -> ExecutionResult:
        """Execute *cmd* asynchronously and return an `ExecutionResult`."""
        start = time.monotonic()
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
            )

            if timeout is not None:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=timeout
                )
            else:
                stdout, stderr = await process.communicate()

            duration = time.monotonic() - start
            return ExecutionResult(
                success=process.returncode == 0,
                stdout=stdout.decode(errors="replace"),
                stderr=stderr.decode(errors="replace"),
                exit_code=process.returncode or 0,
                duration_seconds=round(duration, 2),
            )
        except asyncio.TimeoutError:
            # Kill the process on timeout.
            try:
                process.kill()  # type: ignore[possibly-undefined]
                await process.wait()  # type: ignore[possibly-undefined]
            except Exception:
                pass
            duration = time.monotonic() - start
            return ExecutionResult(
                success=False,
                stdout="",
                stderr=f"Process timed out after {timeout}s",
                exit_code=-1,
                duration_seconds=round(duration, 2),
            )
