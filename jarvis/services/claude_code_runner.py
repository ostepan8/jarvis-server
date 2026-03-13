"""Claude Code CLI runner for autonomous code modifications in git worktrees.

Wraps the Claude Code CLI as an async subprocess, providing safe execution
inside isolated git worktrees with denied-path enforcement and file-change
limits.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import re
import time
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path
from typing import Optional

from ..core.errors import SafetyViolationError, WorktreeError
from ..logging import JarvisLogger

INIT_MD_PATH = ".claude/INIT.md"
_MAX_LOG_ENTRIES = 20
_MAX_DIFF_STAT_COMMITS = 5


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

    @staticmethod
    def _slugify(name: str, max_length: int = 60) -> str:
        """Convert an arbitrary string into a git-safe, unique branch name slug.

        Appends a short hash suffix so that different inputs which share a
        long common prefix (e.g. multiple test failures from the same file)
        still produce distinct slugs.
        """
        suffix = hashlib.sha1(name.encode()).hexdigest()[:8]
        slug = name.lower()
        slug = re.sub(r"[^a-z0-9]+", "-", slug)
        slug = slug.strip("-")
        # Reserve room for the dash + 8-char hash suffix
        cap = max_length - 9
        if len(slug) > cap:
            slug = slug[:cap].rstrip("-")
        return f"{slug}-{suffix}" if slug else f"unnamed-{suffix}"

    async def create_worktree(self, task_name: str) -> tuple[str, str]:
        """Create an isolated git worktree for *task_name*.

        Returns:
            A ``(worktree_path, branch_name)`` tuple.

        Raises:
            WorktreeError: If the git command fails.
        """
        safe_name = self._slugify(task_name)
        worktree_path = str(
            Path(self.project_root) / ".claude" / "worktrees" / f"night-{safe_name}"
        )
        branch_name = f"worktree-night-{safe_name}"

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
        discovery_type: str = "",
        confidence: str = "medium",
    ) -> ExecutionResult:
        """Run a Claude Code task inside *worktree_path*.

        Raises:
            SafetyViolationError: If denied paths are touched or too many
                files are changed.
        """
        prompt = self._build_prompt(
            task_description, relevant_files,
            discovery_type=discovery_type, confidence=confidence,
        )

        if self.logger:
            self.logger.log("INFO", "Executing Claude Code task", worktree_path)

        result = await self._run_subprocess(
            [
                self.claude_binary,
                "-p",
                "--dangerously-skip-permissions",
                "--max-turns",
                "25",
                "--verbose",
                prompt,
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
        cmd: list[str] = ["pytest", "-x", "-q"]
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

        # Keep the implementation briefing current after every merge.
        await self.update_init_md()
        return True

    async def check_gh_available(self) -> bool:
        """Return True if the GitHub CLI is authenticated and runnable."""
        try:
            result = await self._run_subprocess(
                ["gh", "auth", "status"], timeout=10
            )
            return result.exit_code == 0
        except Exception:
            return False

    async def push_branch(
        self, worktree_path: str, branch_name: str
    ) -> ExecutionResult:
        """Push *branch_name* to origin from *worktree_path*."""
        if self.logger:
            self.logger.log("INFO", "Pushing branch", branch_name)

        return await self._run_subprocess(
            ["git", "push", "-u", "origin", branch_name],
            cwd=worktree_path,
            timeout=60,
        )

    async def create_pull_request(
        self,
        worktree_path: str,
        branch_name: str,
        title: str,
        body: str,
        base_branch: str = "main",
    ) -> ExecutionResult:
        """Create a GitHub pull request via ``gh pr create``.

        On success, ``stdout`` contains the PR URL.
        """
        if self.logger:
            self.logger.log("INFO", "Creating pull request", title)

        return await self._run_subprocess(
            [
                "gh", "pr", "create",
                "--title", title,
                "--body", body,
                "--base", base_branch,
                "--head", branch_name,
            ],
            cwd=worktree_path,
            timeout=30,
        )

    async def cleanup_worktree(
        self, worktree_path: str, branch_name: str, keep_branch: bool = False
    ) -> None:
        """Remove the worktree directory and optionally delete the local branch.

        When *keep_branch* is True the branch is preserved for an open PR.
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

        if not keep_branch:
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
    # INIT.md — implementation briefing for future sessions
    # ------------------------------------------------------------------

    async def update_init_md(self) -> None:
        """Regenerate ``.claude/INIT.md`` from current git state.

        Called after every successful merge so that future Claude sessions
        inherit context about what has been built, changed, and is in
        progress.  The file is kept concise — recent history plus active
        worktrees — so it stays useful without becoming noise.
        """
        sections: list[str] = [
            "# INIT.md — Implementation Briefing",
            "",
            "*Auto-generated after each merge. Do not edit by hand.*",
            "",
        ]

        # --- Recent commits (what happened) ---
        log_result = await self._run_subprocess(
            [
                "git", "log", f"--max-count={_MAX_LOG_ENTRIES}",
                "--format=%h %s (%ar)",
            ],
            cwd=self.project_root,
            timeout=10,
        )
        if log_result.success and log_result.stdout.strip():
            sections.append("## Recent Commits")
            sections.append("")
            for line in log_result.stdout.strip().splitlines():
                sections.append(f"- {line}")
            sections.append("")

        # --- Files changed recently (what's fresh) ---
        stat_result = await self._run_subprocess(
            [
                "git", "diff", "--stat",
                f"HEAD~{_MAX_DIFF_STAT_COMMITS}..HEAD",
            ],
            cwd=self.project_root,
            timeout=10,
        )
        if stat_result.success and stat_result.stdout.strip():
            sections.append("## Recently Changed Files")
            sections.append("")
            sections.append("```")
            sections.append(stat_result.stdout.strip())
            sections.append("```")
            sections.append("")

        # --- Active worktrees (what's in flight) ---
        wt_result = await self._run_subprocess(
            ["git", "worktree", "list", "--porcelain"],
            cwd=self.project_root,
            timeout=10,
        )
        if wt_result.success and wt_result.stdout.strip():
            worktrees: list[str] = []
            current_path = ""
            current_branch = ""
            for line in wt_result.stdout.strip().splitlines():
                if line.startswith("worktree "):
                    current_path = line.removeprefix("worktree ").strip()
                elif line.startswith("branch "):
                    current_branch = line.removeprefix("branch ").strip()
                    current_branch = current_branch.removeprefix("refs/heads/")
                elif line == "":
                    if current_path and current_branch and current_branch != "main":
                        worktrees.append(
                            f"- `{current_branch}` → `{current_path}`"
                        )
                    current_path = ""
                    current_branch = ""
            # Flush last entry (porcelain output may not end with blank line)
            if current_path and current_branch and current_branch != "main":
                worktrees.append(f"- `{current_branch}` → `{current_path}`")

            if worktrees:
                sections.append("## Active Worktrees")
                sections.append("")
                sections.extend(worktrees)
                sections.append("")

        init_path = Path(self.project_root) / INIT_MD_PATH
        init_path.parent.mkdir(parents=True, exist_ok=True)
        init_path.write_text("\n".join(sections) + "\n")

        if self.logger:
            self.logger.log("INFO", "Updated INIT.md", str(init_path))

    # ------------------------------------------------------------------
    # Prompt construction
    # ------------------------------------------------------------------

    def _build_prompt(
        self,
        task_description: str,
        relevant_files: list[str],
        discovery_type: str = "",
        confidence: str = "medium",
    ) -> str:
        """Build the structured prompt sent to Claude Code.

        Includes discovery-type-specific instructions when *discovery_type*
        is provided, and communicates the *confidence* level so the agent
        can calibrate the scope of its changes.
        """
        if relevant_files:
            files_section = "\n".join(f"- {f}" for f in relevant_files)
        else:
            files_section = "No specific files identified. Explore as needed."

        # Discovery-type-specific guidance
        type_instructions = self._type_specific_instructions(discovery_type)

        # Inject INIT.md context so spawned sessions know what's been built
        init_context = ""
        init_path = Path(self.project_root) / INIT_MD_PATH
        if init_path.exists():
            try:
                init_context = init_path.read_text().strip()
            except OSError:
                pass

        return (
            "You are an autonomous code improvement agent for the Jarvis Server project.\n"
            "\n"
            + (
                "IMPLEMENTATION CONTEXT (from .claude/INIT.md):\n"
                f"{init_context}\n\n"
                if init_context else ""
            )
            + f"FIX CONFIDENCE: {confidence}\n"
            "\n"
            "YOUR TASK:\n"
            f"{task_description}\n"
            "\n"
            + (f"TYPE-SPECIFIC GUIDANCE:\n{type_instructions}\n\n" if type_instructions else "")
            + "IMPORTANT CONSTRAINTS:\n"
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

    @staticmethod
    def _type_specific_instructions(discovery_type: str) -> str:
        """Return targeted fix instructions based on discovery type."""
        instructions = {
            "unused_import": (
                "Remove the unused import(s). Do not add any other changes."
            ),
            "exception_antipattern": (
                "Replace the bare except / swallowed exception with proper error handling. "
                "Log or re-raise as appropriate. Do not silence errors with pass."
            ),
            "test_failure": (
                "Fix the failing test(s). If the test output is included above, "
                "use it to diagnose the root cause. Prefer fixing the source code "
                "over modifying the test, unless the test expectation is wrong."
            ),
            "log_error": (
                "Investigate the stack trace details included above. "
                "Fix the root cause of the error, not just the symptom."
            ),
            "complexity_hotspot": (
                "Refactor the complex function into smaller, well-named helpers. "
                "Preserve all existing behavior and tests."
            ),
            "missing_tests": (
                "Create a test file for the untested module. Cover the main "
                "public API methods with at least happy-path and one error case."
            ),
        }
        return instructions.get(discovery_type, "")

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
        """Execute *cmd* asynchronously and return an `ExecutionResult`.

        The ``CLAUDECODE`` environment variable is stripped so the Claude
        CLI can be launched from within an existing Claude Code session
        (e.g. the night-agent pipeline running inside the IDE).
        """
        env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
        start = time.monotonic()
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env=env,
            )

            if timeout is not None:
                try:
                    stdout, stderr = await asyncio.wait_for(
                        process.communicate(), timeout=timeout
                    )
                except asyncio.CancelledError:
                    process.terminate()
                    try:
                        await asyncio.wait_for(process.wait(), timeout=5.0)
                    except asyncio.TimeoutError:
                        process.kill()
                        await process.wait()
                    raise
            else:
                try:
                    stdout, stderr = await process.communicate()
                except asyncio.CancelledError:
                    process.terminate()
                    try:
                        await asyncio.wait_for(process.wait(), timeout=5.0)
                    except asyncio.TimeoutError:
                        process.kill()
                        await process.wait()
                    raise

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
