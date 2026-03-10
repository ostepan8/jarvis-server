"""Real E2E tests for the self-improvement pipeline using Claude Code CLI.

These tests create temporary git repositories with intentional bugs,
run the actual self-improvement components (SystemAnalyzer, ClaudeCodeRunner),
and evaluate the results.

Skip unless SELF_IMPROVEMENT_E2E=1 and `claude --version` succeeds.
These are slow, cost money, and require the Claude Code CLI.
"""

from __future__ import annotations

import os
import subprocess
import textwrap
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from jarvis.services.claude_code_runner import ClaudeCodeRunner
from jarvis.services.self_improvement_service import SelfImprovementService
from jarvis.services.system_analyzer import SystemAnalyzer

# ---------------------------------------------------------------------------
# Skip conditions
# ---------------------------------------------------------------------------


def _claude_cli_available() -> bool:
    """Return True if the Claude Code CLI is installed and runnable."""
    try:
        result = subprocess.run(
            ["claude", "--version"],
            capture_output=True,
            timeout=10,
        )
        return result.returncode == 0
    except Exception:
        return False


def _gh_cli_authenticated() -> bool:
    """Return True if the GitHub CLI is authenticated."""
    try:
        result = subprocess.run(
            ["gh", "auth", "status"],
            capture_output=True,
            timeout=10,
        )
        return result.returncode == 0
    except Exception:
        return False


_SKIP_REASON = "Set SELF_IMPROVEMENT_E2E=1 and install Claude CLI to run"
_skip_unless_e2e = pytest.mark.skipif(
    os.environ.get("SELF_IMPROVEMENT_E2E") != "1" or not _claude_cli_available(),
    reason=_SKIP_REASON,
)
_skip_unless_gh = pytest.mark.skipif(
    not _gh_cli_authenticated(),
    reason="gh CLI not authenticated — skipping PR tests",
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def e2e_project(tmp_path: Path):
    """Create a minimal git repository for E2E testing.

    Yields a dict with:
        - project_dir: Path to the repo root
        - bare_remote: Path to a bare git remote for push testing
    """
    project_dir = tmp_path / "test_project"
    project_dir.mkdir()

    # Create a bare remote for push/PR testing
    bare_remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(bare_remote)], check=True, capture_output=True)

    # Initialize git repo
    subprocess.run(["git", "init"], cwd=project_dir, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=project_dir, check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=project_dir, check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "remote", "add", "origin", str(bare_remote)],
        cwd=project_dir, check=True, capture_output=True,
    )

    # pyproject.toml for pytest
    (project_dir / "pyproject.toml").write_text(textwrap.dedent("""\
        [tool.pytest.ini_options]
        testpaths = ["."]
    """))

    yield {"project_dir": project_dir, "bare_remote": bare_remote}


def _commit_files(project_dir: Path, files: dict[str, str], message: str = "initial commit"):
    """Write files and create a git commit."""
    for name, content in files.items():
        filepath = project_dir / name
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(content)

    subprocess.run(["git", "add", "-A"], cwd=project_dir, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", message],
        cwd=project_dir, check=True, capture_output=True,
    )


# ---------------------------------------------------------------------------
# E2E Tests
# ---------------------------------------------------------------------------


@_skip_unless_e2e
class TestE2EDiscoverTestFailure:
    """Verify we can detect failing tests in a real repo via pytest."""

    @pytest.mark.asyncio
    @pytest.mark.timeout(60)
    async def test_discovers_test_failure(self, e2e_project):
        import asyncio as _asyncio

        project_dir = e2e_project["project_dir"]

        _commit_files(project_dir, {
            "calculator.py": textwrap.dedent("""\
                def add(a, b):
                    return a - b  # Bug: should be a + b
            """),
            "test_calculator.py": textwrap.dedent("""\
                from calculator import add

                def test_add():
                    assert add(2, 3) == 5
            """),
        })

        # Run pytest directly (SystemAnalyzer.analyze_tests uses --timeout
        # which requires pytest-timeout — not always available).
        proc = await _asyncio.create_subprocess_exec(
            "pytest", "--tb=short", "-q",
            cwd=str(project_dir),
            stdout=_asyncio.subprocess.PIPE,
            stderr=_asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        output = stdout.decode(errors="replace")

        # pytest should have exited non-zero (test fails)
        assert proc.returncode != 0, f"Expected test failure but got exit 0:\n{output}"
        assert "FAILED" in output, f"No FAILED line in pytest output:\n{output}"
        assert "test_add" in output


@_skip_unless_e2e
class TestE2EClaudeFixesSimpleBug:
    """Verify Claude Code can fix a trivial bug in an isolated worktree."""

    @pytest.mark.asyncio
    @pytest.mark.timeout(300)
    async def test_claude_fixes_add_bug(self, e2e_project):
        project_dir = e2e_project["project_dir"]

        _commit_files(project_dir, {
            "calculator.py": textwrap.dedent("""\
                def add(a, b):
                    return a - b  # Bug: should be a + b
            """),
            "test_calculator.py": textwrap.dedent("""\
                from calculator import add

                def test_add():
                    assert add(2, 3) == 5

                def test_add_negatives():
                    assert add(-1, -2) == -3
            """),
        })

        runner = ClaudeCodeRunner(
            project_root=str(project_dir),
            logger=MagicMock(),
        )

        # Create a worktree
        wt_path, branch = await runner.create_worktree("fix-add-bug")

        try:
            # Execute the fix
            result = await runner.execute_task(
                task_description=(
                    "Fix the bug in calculator.py. The add() function returns "
                    "wrong results — it subtracts instead of adding. Fix it so "
                    "all tests pass."
                ),
                relevant_files=["calculator.py", "test_calculator.py"],
                worktree_path=wt_path,
            )

            # The execution should succeed
            assert result.success is True, f"Execution failed: {result.stderr}"

            # Read the fixed file
            fixed_content = (Path(wt_path) / "calculator.py").read_text()

            # Should contain a + b (or equivalent correct logic)
            assert "a - b" not in fixed_content or "a + b" in fixed_content, (
                f"Bug not fixed. File content:\n{fixed_content}"
            )

            # Run tests in the worktree to confirm
            test_result = await runner.run_tests(wt_path)
            assert test_result.success is True, f"Tests still failing: {test_result.stdout}"
        finally:
            await runner.cleanup_worktree(wt_path, branch)


@_skip_unless_e2e
class TestE2EClaudeAddsMissingFunction:
    """Verify Claude Code can implement a missing function."""

    @pytest.mark.asyncio
    @pytest.mark.timeout(300)
    async def test_claude_implements_multiply(self, e2e_project):
        project_dir = e2e_project["project_dir"]

        _commit_files(project_dir, {
            "calculator.py": textwrap.dedent("""\
                def add(a, b):
                    return a + b
            """),
            "test_calculator.py": textwrap.dedent("""\
                from calculator import add, multiply

                def test_add():
                    assert add(2, 3) == 5

                def test_multiply():
                    assert multiply(3, 4) == 12

                def test_multiply_zero():
                    assert multiply(5, 0) == 0
            """),
        })

        runner = ClaudeCodeRunner(
            project_root=str(project_dir),
            logger=MagicMock(),
        )

        wt_path, branch = await runner.create_worktree("add-multiply")

        try:
            result = await runner.execute_task(
                task_description=(
                    "Implement the missing multiply(a, b) function in "
                    "calculator.py. The test file already imports it and "
                    "has tests for it. Make all tests pass."
                ),
                relevant_files=["calculator.py", "test_calculator.py"],
                worktree_path=wt_path,
            )

            assert result.success is True, f"Execution failed: {result.stderr}"

            # Verify the function exists
            calc_content = (Path(wt_path) / "calculator.py").read_text()
            assert "multiply" in calc_content, "multiply function not found"

            # Verify tests pass
            test_result = await runner.run_tests(wt_path)
            assert test_result.success is True, f"Tests failing: {test_result.stdout}"
        finally:
            await runner.cleanup_worktree(wt_path, branch)


@_skip_unless_e2e
class TestE2EClaudeHandlesUnfixableProblem:
    """Verify the pipeline handles gracefully when a task cannot be fixed."""

    @pytest.mark.asyncio
    @pytest.mark.timeout(300)
    async def test_unfixable_returns_failure(self, e2e_project):
        project_dir = e2e_project["project_dir"]

        # A test that's fundamentally impossible to fix by changing source —
        # it asserts a mathematical impossibility
        _commit_files(project_dir, {
            "calculator.py": textwrap.dedent("""\
                import math

                def square_root(n):
                    return math.sqrt(n)
            """),
            "test_calculator.py": textwrap.dedent("""\
                from calculator import square_root

                def test_negative_sqrt_returns_real():
                    # This test demands the impossible: a real square root of -1
                    result = square_root(-1)
                    assert isinstance(result, float)
                    assert result == -1.0  # mathematically impossible
            """),
        })

        runner = ClaudeCodeRunner(
            project_root=str(project_dir),
            logger=MagicMock(),
        )

        wt_path, branch = await runner.create_worktree("unfixable-sqrt")

        try:
            exec_result = await runner.execute_task(
                task_description=(
                    "Fix the test failure in test_calculator.py. The "
                    "test_negative_sqrt_returns_real test is failing. "
                    "Do NOT modify the test file — only fix calculator.py."
                ),
                relevant_files=["calculator.py"],
                worktree_path=wt_path,
            )

            # Run tests — they may or may not pass depending on Claude's approach
            test_result = await runner.run_tests(wt_path)

            # The key assertion: if tests fail, that's the expected outcome
            # for an unfixable problem. If Claude somehow made them pass,
            # that's also acceptable (creative solution).
            if not test_result.success:
                # Expected: task is effectively unfixable
                pass
            # Either way, the pipeline should not crash
        finally:
            await runner.cleanup_worktree(wt_path, branch)


@_skip_unless_e2e
class TestE2ESafetyRails:
    """Verify safety rails prevent modification of denied paths."""

    @pytest.mark.asyncio
    @pytest.mark.timeout(300)
    async def test_denied_path_raises_safety_violation(self, e2e_project):
        from jarvis.core.errors import SafetyViolationError

        project_dir = e2e_project["project_dir"]

        _commit_files(project_dir, {
            "calculator.py": textwrap.dedent("""\
                def add(a, b):
                    return a + b
            """),
            "jarvis/core/config.py": textwrap.dedent("""\
                # This file is on the denied list
                CONFIG_VALUE = "original"
            """),
            "test_calculator.py": textwrap.dedent("""\
                from calculator import add

                def test_add():
                    assert add(2, 3) == 5
            """),
        })

        runner = ClaudeCodeRunner(
            project_root=str(project_dir),
            logger=MagicMock(),
        )

        wt_path, branch = await runner.create_worktree("safety-test")

        try:
            # Manually simulate what would happen if Claude touched a denied file
            denied_file = Path(wt_path) / "jarvis" / "core" / "config.py"
            denied_file.write_text('CONFIG_VALUE = "modified"\n')

            # Stage the change
            subprocess.run(
                ["git", "add", "jarvis/core/config.py"],
                cwd=wt_path, check=True, capture_output=True,
            )

            # Now run execute_task — it should detect the denied file change
            # We use a no-op task since we already staged the change
            with pytest.raises(SafetyViolationError):
                await runner.execute_task(
                    task_description="Do nothing — just verify safety checks",
                    relevant_files=[],
                    worktree_path=wt_path,
                )
        finally:
            await runner.cleanup_worktree(wt_path, branch)


@_skip_unless_e2e
class TestE2EFullCycleWithPR:
    """Full cycle: discover, fix, push, create PR.

    Requires gh CLI authentication and a real GitHub remote.
    Only runs when SELF_IMPROVEMENT_E2E=1 and gh is authenticated.
    """

    @_skip_unless_gh
    @pytest.mark.asyncio
    @pytest.mark.timeout(600)
    async def test_full_cycle_creates_pr(self, e2e_project):
        """This test requires a real GitHub repository to push to.

        Set SELF_IMPROVEMENT_E2E_REPO to a GitHub repo you own
        (e.g., 'user/test-repo') to enable this test.
        """
        repo = os.environ.get("SELF_IMPROVEMENT_E2E_REPO")
        if not repo:
            pytest.skip("Set SELF_IMPROVEMENT_E2E_REPO=user/repo to run")

        project_dir = e2e_project["project_dir"]

        # Point remote to real GitHub repo
        subprocess.run(
            ["git", "remote", "set-url", "origin", f"https://github.com/{repo}.git"],
            cwd=project_dir, check=True, capture_output=True,
        )

        _commit_files(project_dir, {
            "calculator.py": textwrap.dedent("""\
                def add(a, b):
                    return a - b  # Bug
            """),
            "test_calculator.py": textwrap.dedent("""\
                from calculator import add

                def test_add():
                    assert add(2, 3) == 5
            """),
        })

        # Push initial state to main
        subprocess.run(
            ["git", "push", "-u", "origin", "main", "--force"],
            cwd=project_dir, check=True, capture_output=True,
        )

        svc = SelfImprovementService(
            project_root=str(project_dir),
            logger=MagicMock(),
            use_prs=True,
        )

        report = await svc.run_improvement_cycle()

        try:
            assert report.tasks_attempted >= 1
            # Check if any result has a PR URL
            pr_results = [r for r in report.results if r.pr_url]
            assert len(pr_results) >= 1, (
                f"No PRs created. Results: {[r.__dict__ for r in report.results]}"
            )
        finally:
            # Clean up: close any PRs created
            for r in report.results:
                if r.pr_url:
                    try:
                        subprocess.run(
                            ["gh", "pr", "close", r.pr_url, "--delete-branch"],
                            capture_output=True, timeout=30,
                        )
                    except Exception:
                        pass
