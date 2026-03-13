"""Tests for the ClaudeCodeRunner service."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from jarvis.core.errors import SafetyViolationError, WorktreeError
from jarvis.services.claude_code_runner import (
    ClaudeCodeRunner,
    ExecutionResult,
    INIT_MD_PATH,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_process(returncode: int = 0, stdout: bytes = b"", stderr: bytes = b""):
    """Return a mock process whose ``communicate`` returns given outputs."""
    proc = AsyncMock()
    proc.returncode = returncode
    proc.communicate = AsyncMock(return_value=(stdout, stderr))
    proc.kill = MagicMock()
    proc.wait = AsyncMock()
    return proc


# ---------------------------------------------------------------------------
# TestClaudeCodeRunnerAvailability
# ---------------------------------------------------------------------------


class TestClaudeCodeRunnerAvailability:
    @pytest.mark.asyncio
    async def test_available_when_installed(self):
        """Mock subprocess returning exit 0 for claude --version."""
        runner = ClaudeCodeRunner(project_root="/fake")
        proc = _make_process(returncode=0, stdout=b"claude 1.0.0")

        with patch("asyncio.create_subprocess_exec", return_value=proc):
            assert await runner.check_available() is True

    @pytest.mark.asyncio
    async def test_unavailable_when_missing(self):
        """Mock subprocess raising FileNotFoundError."""
        runner = ClaudeCodeRunner(project_root="/fake")

        with patch(
            "asyncio.create_subprocess_exec", side_effect=FileNotFoundError
        ):
            assert await runner.check_available() is False


# ---------------------------------------------------------------------------
# TestPromptConstruction
# ---------------------------------------------------------------------------


class TestPromptConstruction:
    def test_includes_task_description(self):
        runner = ClaudeCodeRunner(project_root="/fake")
        prompt = runner._build_prompt("Fix the bug", ["jarvis/agents/foo.py"])
        assert "Fix the bug" in prompt

    def test_includes_relevant_files(self):
        runner = ClaudeCodeRunner(project_root="/fake")
        prompt = runner._build_prompt("Task", ["jarvis/agents/foo.py"])
        assert "jarvis/agents/foo.py" in prompt

    def test_includes_safety_constraints(self):
        runner = ClaudeCodeRunner(project_root="/fake")
        prompt = runner._build_prompt("Task", [])
        assert "NEVER modify" in prompt
        assert "system.py" in prompt

    def test_empty_files_shows_fallback(self):
        runner = ClaudeCodeRunner(project_root="/fake")
        prompt = runner._build_prompt("Task", [])
        assert "No specific files" in prompt

    def test_includes_multiple_files(self):
        runner = ClaudeCodeRunner(project_root="/fake")
        prompt = runner._build_prompt(
            "Task", ["file_a.py", "file_b.py", "file_c.py"]
        )
        assert "file_a.py" in prompt
        assert "file_b.py" in prompt
        assert "file_c.py" in prompt

    def test_includes_project_conventions(self):
        runner = ClaudeCodeRunner(project_root="/fake")
        prompt = runner._build_prompt("Task", [])
        assert "AgentResponse" in prompt
        assert "pytest" in prompt


# ---------------------------------------------------------------------------
# TestDeniedPathChecking
# ---------------------------------------------------------------------------


class TestDeniedPathChecking:
    def test_detects_env_file(self):
        runner = ClaudeCodeRunner(project_root="/fake")
        assert runner._check_denied_paths([".env"]) is True

    def test_detects_system_py(self):
        runner = ClaudeCodeRunner(project_root="/fake")
        assert runner._check_denied_paths(["jarvis/core/system.py"]) is True

    def test_allows_normal_files(self):
        runner = ClaudeCodeRunner(project_root="/fake")
        assert (
            runner._check_denied_paths(["jarvis/agents/todo_agent/__init__.py"])
            is False
        )

    def test_detects_pem_file(self):
        runner = ClaudeCodeRunner(project_root="/fake")
        assert runner._check_denied_paths(["server.pem"]) is True

    def test_detects_key_file(self):
        runner = ClaudeCodeRunner(project_root="/fake")
        assert runner._check_denied_paths(["private.key"]) is True

    def test_detects_credentials_file(self):
        runner = ClaudeCodeRunner(project_root="/fake")
        assert runner._check_denied_paths(["credentials.json"]) is True

    def test_detects_factory_py(self):
        runner = ClaudeCodeRunner(project_root="/fake")
        assert runner._check_denied_paths(["jarvis/agents/factory.py"]) is True

    def test_detects_config_py(self):
        runner = ClaudeCodeRunner(project_root="/fake")
        assert runner._check_denied_paths(["jarvis/core/config.py"]) is True

    def test_detects_nlu_init(self):
        runner = ClaudeCodeRunner(project_root="/fake")
        assert (
            runner._check_denied_paths(["jarvis/agents/nlu_agent/__init__.py"])
            is True
        )

    def test_allows_empty_list(self):
        runner = ClaudeCodeRunner(project_root="/fake")
        assert runner._check_denied_paths([]) is False

    def test_mixed_allowed_and_denied(self):
        runner = ClaudeCodeRunner(project_root="/fake")
        assert (
            runner._check_denied_paths(["safe_file.py", "jarvis/core/system.py"])
            is True
        )


# ---------------------------------------------------------------------------
# TestExecutionResult
# ---------------------------------------------------------------------------


class TestExecutionResult:
    def test_dataclass_defaults(self):
        result = ExecutionResult(success=True, stdout="ok", stderr="", exit_code=0)
        assert result.files_changed == 0
        assert result.duration_seconds == 0.0
        assert result.worktree_path is None
        assert result.branch_name is None

    def test_dataclass_with_all_fields(self):
        result = ExecutionResult(
            success=False,
            stdout="output",
            stderr="error",
            exit_code=1,
            worktree_path="/tmp/wt",
            branch_name="worktree-night-fix",
            files_changed=3,
            duration_seconds=12.5,
        )
        assert result.success is False
        assert result.exit_code == 1
        assert result.worktree_path == "/tmp/wt"
        assert result.branch_name == "worktree-night-fix"
        assert result.files_changed == 3
        assert result.duration_seconds == 12.5


# ---------------------------------------------------------------------------
# TestCreateWorktree
# ---------------------------------------------------------------------------


class TestSlugify:
    def test_simple_name_includes_hash(self):
        result = ClaudeCodeRunner._slugify("fix-bug")
        assert result.startswith("fix-bug-")
        assert len(result) == len("fix-bug-") + 8  # 8-char hash

    def test_spaces_become_hyphens(self):
        result = ClaudeCodeRunner._slugify("fix the bug")
        assert result.startswith("fix-the-bug-")

    def test_colons_and_slashes_replaced(self):
        result = ClaudeCodeRunner._slugify(
            "Test failure: tests/test_health_service.py::TestClass::test_method"
        )
        assert ":" not in result
        assert "/" not in result
        assert "::" not in result

    def test_truncated_to_max_length(self):
        long_name = "a" * 100
        result = ClaudeCodeRunner._slugify(long_name, max_length=60)
        assert len(result) <= 60

    def test_no_leading_or_trailing_hyphens(self):
        result = ClaudeCodeRunner._slugify("--weird--name--")
        assert result.startswith("weird-name-")

    def test_empty_string_returns_unnamed(self):
        result = ClaudeCodeRunner._slugify(":::")
        assert result.startswith("unnamed-")

    def test_uppercase_lowered(self):
        result = ClaudeCodeRunner._slugify("FIX-BUG")
        assert result.startswith("fix-bug-")

    def test_different_inputs_produce_different_slugs(self):
        """Two test failures from the same file must not collide."""
        a = ClaudeCodeRunner._slugify(
            "Test failure: tests/test_search_service.py::TestInit::test_with_explicit_credentials"
        )
        b = ClaudeCodeRunner._slugify(
            "Test failure: tests/test_search_service.py::TestInit::test_with_env_vars"
        )
        assert a != b

    def test_deterministic(self):
        """Same input always produces the same slug."""
        assert ClaudeCodeRunner._slugify("fix-bug") == ClaudeCodeRunner._slugify("fix-bug")


class TestCreateWorktree:
    @pytest.mark.asyncio
    async def test_success(self):
        runner = ClaudeCodeRunner(project_root="/project")
        proc = _make_process(returncode=0)

        with patch("asyncio.create_subprocess_exec", return_value=proc):
            path, branch = await runner.create_worktree("fix-bug")

        slug = ClaudeCodeRunner._slugify("fix-bug")
        assert path.endswith(f"night-{slug}")
        assert branch == f"worktree-night-{slug}"

    @pytest.mark.asyncio
    async def test_sanitizes_test_failure_title(self):
        runner = ClaudeCodeRunner(project_root="/project")
        proc = _make_process(returncode=0)

        ugly_name = "Test failure: tests/test_health_service.py::TestClass::test_method"
        with patch("asyncio.create_subprocess_exec", return_value=proc) as mock_exec:
            path, branch = await runner.create_worktree(ugly_name)

        # Branch name must be git-safe
        assert ":" not in branch
        assert "/" not in branch
        assert " " not in branch
        # Verify the sanitized name was actually passed to git
        cmd_args = mock_exec.call_args[0]
        assert branch in cmd_args

    @pytest.mark.asyncio
    async def test_failure_raises_worktree_error(self):
        runner = ClaudeCodeRunner(project_root="/project")
        proc = _make_process(returncode=128, stderr=b"fatal: already exists")

        with patch("asyncio.create_subprocess_exec", return_value=proc):
            with pytest.raises(WorktreeError, match="Failed to create worktree"):
                await runner.create_worktree("fix-bug")


# ---------------------------------------------------------------------------
# TestExecuteTask
# ---------------------------------------------------------------------------


class TestExecuteTask:
    @pytest.mark.asyncio
    async def test_success_no_changed_files(self):
        runner = ClaudeCodeRunner(project_root="/project")

        call_count = 0

        async def _fake_exec(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # Claude Code execution
                return _make_process(returncode=0, stdout=b"done")
            # git diff calls -- no files changed
            return _make_process(returncode=0, stdout=b"")

        with patch("asyncio.create_subprocess_exec", side_effect=_fake_exec):
            result = await runner.execute_task("Fix it", [], "/wt")

        assert result.success is True
        assert result.files_changed == 0

    @pytest.mark.asyncio
    async def test_denied_file_raises_safety_violation(self):
        runner = ClaudeCodeRunner(project_root="/project")

        call_count = 0

        async def _fake_exec(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _make_process(returncode=0, stdout=b"done")
            if call_count == 2:
                # git diff --name-only HEAD (unstaged)
                return _make_process(
                    returncode=0, stdout=b"jarvis/core/system.py\n"
                )
            # git diff --name-only --cached HEAD (staged)
            return _make_process(returncode=0, stdout=b"")

        with patch("asyncio.create_subprocess_exec", side_effect=_fake_exec):
            with pytest.raises(SafetyViolationError, match="denied file"):
                await runner.execute_task("Fix it", [], "/wt")

    @pytest.mark.asyncio
    async def test_too_many_files_raises_safety_violation(self):
        runner = ClaudeCodeRunner(project_root="/project")
        many_files = "\n".join(f"file_{i}.py" for i in range(15))

        call_count = 0

        async def _fake_exec(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _make_process(returncode=0, stdout=b"done")
            if call_count == 2:
                return _make_process(
                    returncode=0, stdout=many_files.encode()
                )
            return _make_process(returncode=0, stdout=b"")

        with patch("asyncio.create_subprocess_exec", side_effect=_fake_exec):
            with pytest.raises(SafetyViolationError, match="Too many files"):
                await runner.execute_task("Fix it", [], "/wt")


# ---------------------------------------------------------------------------
# TestRunTests
# ---------------------------------------------------------------------------


class TestRunTests:
    @pytest.mark.asyncio
    async def test_run_full_suite(self):
        runner = ClaudeCodeRunner(project_root="/project")
        proc = _make_process(returncode=0, stdout=b"5 passed")

        with patch("asyncio.create_subprocess_exec", return_value=proc) as mock_exec:
            result = await runner.run_tests("/wt")

        assert result.success is True
        # Verify pytest was called without specific files
        cmd_args = mock_exec.call_args[0]
        assert "pytest" in cmd_args
        assert "-x" in cmd_args

    @pytest.mark.asyncio
    async def test_run_specific_files(self):
        runner = ClaudeCodeRunner(project_root="/project")
        proc = _make_process(returncode=0, stdout=b"2 passed")

        with patch("asyncio.create_subprocess_exec", return_value=proc) as mock_exec:
            result = await runner.run_tests("/wt", test_files=["tests/test_foo.py"])

        assert result.success is True
        cmd_args = mock_exec.call_args[0]
        assert "tests/test_foo.py" in cmd_args


# ---------------------------------------------------------------------------
# TestMergeToMain
# ---------------------------------------------------------------------------


class TestMergeToMain:
    @pytest.mark.asyncio
    async def test_successful_merge(self):
        runner = ClaudeCodeRunner(project_root="/project")
        proc = _make_process(returncode=0)

        with patch("asyncio.create_subprocess_exec", return_value=proc):
            with patch.object(runner, "update_init_md", new_callable=AsyncMock):
                assert await runner.merge_to_main("/wt", "worktree-night-fix") is True

    @pytest.mark.asyncio
    async def test_conflict_aborts_and_returns_false(self):
        runner = ClaudeCodeRunner(project_root="/project")

        call_count = 0

        async def _fake_exec(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # merge fails
                return _make_process(returncode=1, stderr=b"CONFLICT")
            # merge --abort succeeds
            return _make_process(returncode=0)

        with patch("asyncio.create_subprocess_exec", side_effect=_fake_exec):
            assert (
                await runner.merge_to_main("/wt", "worktree-night-fix") is False
            )


# ---------------------------------------------------------------------------
# TestCleanupWorktree
# ---------------------------------------------------------------------------


class TestCleanupWorktree:
    @pytest.mark.asyncio
    async def test_cleanup_success(self):
        runner = ClaudeCodeRunner(project_root="/project")
        proc = _make_process(returncode=0)

        with patch("asyncio.create_subprocess_exec", return_value=proc):
            # Should not raise
            await runner.cleanup_worktree("/wt/path", "worktree-night-fix")

    @pytest.mark.asyncio
    async def test_cleanup_logs_failure_without_raising(self):
        runner = ClaudeCodeRunner(project_root="/project", logger=MagicMock())
        proc = _make_process(returncode=1, stderr=b"error removing")

        with patch("asyncio.create_subprocess_exec", return_value=proc):
            # Should not raise even when both commands fail
            await runner.cleanup_worktree("/wt/path", "worktree-night-fix")

        # Logger should have been called with warning messages
        assert runner.logger.log.call_count >= 1


# ---------------------------------------------------------------------------
# TestRunSubprocess
# ---------------------------------------------------------------------------


class TestRunSubprocess:
    @pytest.mark.asyncio
    async def test_timeout_returns_failure(self):
        runner = ClaudeCodeRunner(project_root="/fake")

        proc = AsyncMock()
        proc.returncode = None
        proc.communicate = AsyncMock(
            side_effect=asyncio.TimeoutError
        )
        proc.kill = MagicMock()
        proc.wait = AsyncMock()

        with patch("asyncio.create_subprocess_exec", return_value=proc):
            # Patch wait_for to raise TimeoutError
            with patch(
                "asyncio.wait_for", side_effect=asyncio.TimeoutError
            ):
                result = await runner._run_subprocess(
                    ["sleep", "100"], timeout=1
                )

        assert result.success is False
        assert result.exit_code == -1
        assert "timed out" in result.stderr

    @pytest.mark.asyncio
    async def test_captures_stdout_and_stderr(self):
        runner = ClaudeCodeRunner(project_root="/fake")
        proc = _make_process(
            returncode=0, stdout=b"hello out", stderr=b"hello err"
        )

        with patch("asyncio.create_subprocess_exec", return_value=proc):
            result = await runner._run_subprocess(["echo", "test"])

        assert result.stdout == "hello out"
        assert result.stderr == "hello err"
        assert result.success is True
        assert result.duration_seconds >= 0.0


# ---------------------------------------------------------------------------
# TestCheckGhAvailable
# ---------------------------------------------------------------------------


class TestCheckGhAvailable:
    @pytest.mark.asyncio
    async def test_gh_available_when_authenticated(self):
        runner = ClaudeCodeRunner(project_root="/fake")
        proc = _make_process(returncode=0, stdout=b"Logged in")

        with patch("asyncio.create_subprocess_exec", return_value=proc):
            assert await runner.check_gh_available() is True

    @pytest.mark.asyncio
    async def test_gh_unavailable_when_not_authenticated(self):
        runner = ClaudeCodeRunner(project_root="/fake")
        proc = _make_process(returncode=1, stderr=b"not logged in")

        with patch("asyncio.create_subprocess_exec", return_value=proc):
            assert await runner.check_gh_available() is False

    @pytest.mark.asyncio
    async def test_gh_unavailable_when_binary_missing(self):
        runner = ClaudeCodeRunner(project_root="/fake")

        with patch(
            "asyncio.create_subprocess_exec", side_effect=FileNotFoundError
        ):
            assert await runner.check_gh_available() is False


# ---------------------------------------------------------------------------
# TestPushBranch
# ---------------------------------------------------------------------------


class TestPushBranch:
    @pytest.mark.asyncio
    async def test_push_branch_success(self):
        runner = ClaudeCodeRunner(project_root="/project")
        proc = _make_process(returncode=0, stdout=b"branch pushed")

        with patch("asyncio.create_subprocess_exec", return_value=proc) as mock_exec:
            result = await runner.push_branch("/wt", "worktree-night-fix")

        assert result.success is True
        cmd_args = mock_exec.call_args[0]
        assert "git" in cmd_args
        assert "push" in cmd_args
        assert "-u" in cmd_args
        assert "origin" in cmd_args
        assert "worktree-night-fix" in cmd_args

    @pytest.mark.asyncio
    async def test_push_branch_failure(self):
        runner = ClaudeCodeRunner(project_root="/project")
        proc = _make_process(returncode=128, stderr=b"rejected")

        with patch("asyncio.create_subprocess_exec", return_value=proc):
            result = await runner.push_branch("/wt", "worktree-night-fix")

        assert result.success is False
        assert result.exit_code == 128


# ---------------------------------------------------------------------------
# TestCreatePullRequest
# ---------------------------------------------------------------------------


class TestCreatePullRequest:
    @pytest.mark.asyncio
    async def test_create_pr_success(self):
        pr_url = b"https://github.com/user/repo/pull/42\n"
        runner = ClaudeCodeRunner(project_root="/project")
        proc = _make_process(returncode=0, stdout=pr_url)

        with patch("asyncio.create_subprocess_exec", return_value=proc) as mock_exec:
            result = await runner.create_pull_request(
                "/wt", "worktree-night-fix", "fix(night-agent): patch", "Body"
            )

        assert result.success is True
        assert "pull/42" in result.stdout
        cmd_args = mock_exec.call_args[0]
        assert "gh" in cmd_args
        assert "pr" in cmd_args
        assert "create" in cmd_args
        assert "--base" in cmd_args
        assert "main" in cmd_args

    @pytest.mark.asyncio
    async def test_create_pr_failure(self):
        runner = ClaudeCodeRunner(project_root="/project")
        proc = _make_process(returncode=1, stderr=b"not a git repo")

        with patch("asyncio.create_subprocess_exec", return_value=proc):
            result = await runner.create_pull_request(
                "/wt", "branch", "title", "body"
            )

        assert result.success is False

    @pytest.mark.asyncio
    async def test_create_pr_custom_base(self):
        runner = ClaudeCodeRunner(project_root="/project")
        proc = _make_process(returncode=0, stdout=b"url")

        with patch("asyncio.create_subprocess_exec", return_value=proc) as mock_exec:
            await runner.create_pull_request(
                "/wt", "branch", "title", "body", base_branch="develop"
            )

        cmd_args = mock_exec.call_args[0]
        assert "develop" in cmd_args


# ---------------------------------------------------------------------------
# TestCleanupWorktreeKeepBranch
# ---------------------------------------------------------------------------


class TestCleanupWorktreeKeepBranch:
    @pytest.mark.asyncio
    async def test_keep_branch_skips_branch_deletion(self):
        runner = ClaudeCodeRunner(project_root="/project")
        calls = []

        async def _track_exec(*args, **kwargs):
            calls.append(args)
            return _make_process(returncode=0)

        with patch("asyncio.create_subprocess_exec", side_effect=_track_exec):
            await runner.cleanup_worktree("/wt/path", "branch-fix", keep_branch=True)

        # Should only have the worktree remove call, not git branch -D
        cmd_strings = [" ".join(c) for c in calls]
        assert any("worktree" in s and "remove" in s for s in cmd_strings)
        assert not any("branch" in s and "-D" in s for s in cmd_strings)

    @pytest.mark.asyncio
    async def test_default_deletes_branch(self):
        runner = ClaudeCodeRunner(project_root="/project")
        calls = []

        async def _track_exec(*args, **kwargs):
            calls.append(args)
            return _make_process(returncode=0)

        with patch("asyncio.create_subprocess_exec", side_effect=_track_exec):
            await runner.cleanup_worktree("/wt/path", "branch-fix")

        cmd_strings = [" ".join(c) for c in calls]
        assert any("worktree" in s and "remove" in s for s in cmd_strings)
        assert any("branch" in s and "-D" in s for s in cmd_strings)


# ---------------------------------------------------------------------------
# TestUpdateInitMd
# ---------------------------------------------------------------------------


class TestUpdateInitMd:
    @pytest.mark.asyncio
    async def test_writes_init_md_with_git_log(self, tmp_path):
        runner = ClaudeCodeRunner(project_root=str(tmp_path))

        log_output = b"abc1234 feat(agents): add FooAgent (2 hours ago)\ndef5678 fix(nlu): handle empty input (1 day ago)\n"

        call_count = 0

        async def _fake_exec(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # git log
                return _make_process(returncode=0, stdout=log_output)
            if call_count == 2:
                # git diff --stat
                return _make_process(returncode=0, stdout=b"")
            # git worktree list
            return _make_process(returncode=0, stdout=b"")

        with patch("asyncio.create_subprocess_exec", side_effect=_fake_exec):
            await runner.update_init_md()

        init_file = tmp_path / ".claude" / "INIT.md"
        assert init_file.exists()
        content = init_file.read_text()
        assert "Implementation Briefing" in content
        assert "abc1234" in content
        assert "FooAgent" in content

    @pytest.mark.asyncio
    async def test_includes_active_worktrees(self, tmp_path):
        runner = ClaudeCodeRunner(project_root=str(tmp_path))

        porcelain = (
            b"worktree /project\n"
            b"branch refs/heads/main\n"
            b"\n"
            b"worktree /project/.claude/worktrees/fix-bug\n"
            b"branch refs/heads/worktree-fix-bug\n"
            b"\n"
        )

        call_count = 0

        async def _fake_exec(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _make_process(returncode=0, stdout=b"abc fix (1h ago)\n")
            if call_count == 2:
                return _make_process(returncode=0, stdout=b"")
            return _make_process(returncode=0, stdout=porcelain)

        with patch("asyncio.create_subprocess_exec", side_effect=_fake_exec):
            await runner.update_init_md()

        content = (tmp_path / ".claude" / "INIT.md").read_text()
        assert "Active Worktrees" in content
        assert "worktree-fix-bug" in content
        # main should be excluded
        assert "` → `/project`" not in content

    @pytest.mark.asyncio
    async def test_handles_all_commands_failing(self, tmp_path):
        runner = ClaudeCodeRunner(project_root=str(tmp_path))

        async def _fail(*args, **kwargs):
            return _make_process(returncode=1, stderr=b"nope")

        with patch("asyncio.create_subprocess_exec", side_effect=_fail):
            await runner.update_init_md()

        content = (tmp_path / ".claude" / "INIT.md").read_text()
        assert "Implementation Briefing" in content
        # Still writes the file — just with header only
        assert "Recent Commits" not in content

    @pytest.mark.asyncio
    async def test_merge_to_main_calls_update_init_md(self):
        runner = ClaudeCodeRunner(project_root="/project")
        proc = _make_process(returncode=0)

        with patch("asyncio.create_subprocess_exec", return_value=proc):
            with patch.object(runner, "update_init_md", new_callable=AsyncMock) as mock_update:
                result = await runner.merge_to_main("/wt", "branch-fix")

        assert result is True
        mock_update.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_merge_conflict_does_not_call_update_init_md(self):
        runner = ClaudeCodeRunner(project_root="/project")

        call_count = 0

        async def _fake_exec(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _make_process(returncode=1, stderr=b"CONFLICT")
            return _make_process(returncode=0)

        with patch("asyncio.create_subprocess_exec", side_effect=_fake_exec):
            with patch.object(runner, "update_init_md", new_callable=AsyncMock) as mock_update:
                result = await runner.merge_to_main("/wt", "branch-fix")

        assert result is False
        mock_update.assert_not_awaited()


# ---------------------------------------------------------------------------
# TestBuildPromptInitMdInjection
# ---------------------------------------------------------------------------


class TestBuildPromptInitMdInjection:
    def test_injects_init_md_when_present(self, tmp_path):
        runner = ClaudeCodeRunner(project_root=str(tmp_path))
        init_dir = tmp_path / ".claude"
        init_dir.mkdir()
        (init_dir / "INIT.md").write_text("# Briefing\n- abc1234 feat: added X\n")

        prompt = runner._build_prompt("Fix bug", ["foo.py"])
        assert "IMPLEMENTATION CONTEXT" in prompt
        assert "abc1234" in prompt

    def test_no_injection_when_missing(self, tmp_path):
        runner = ClaudeCodeRunner(project_root=str(tmp_path))

        prompt = runner._build_prompt("Fix bug", ["foo.py"])
        assert "IMPLEMENTATION CONTEXT" not in prompt
