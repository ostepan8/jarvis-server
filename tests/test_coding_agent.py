"""Tests for CodingAgent."""

from __future__ import annotations

import asyncio
import os
import pytest

from jarvis.agents.coding_agent import CodingAgent, CAPABILITIES
from jarvis.agents.response import AgentResponse


# -- Helpers ---------------------------------------------------------------


class FakeProcess:
    """Mimics asyncio.subprocess with configurable output."""

    def __init__(self, stdout: str = "", stderr: str = "", returncode: int = 0):
        self.returncode = returncode
        self._stdout = stdout.encode()
        self._stderr = stderr.encode()

    async def communicate(self):
        return self._stdout, self._stderr

    def kill(self):
        pass

    def terminate(self):
        pass

    async def wait(self):
        pass


# -- Capability registration -----------------------------------------------


class TestCodingAgentProperties:
    """Verify the agent advertises itself correctly."""

    def test_capabilities_include_all_expected(self):
        agent = CodingAgent(project_root="/tmp")
        expected = {
            "implement_feature",
            "fix_bug",
            "write_tests",
            "explain_code",
            "refactor_code",
            "run_code",
            "edit_file",
            "read_file",
            "create_file",
            "list_files",
        }
        assert agent.capabilities == expected

    def test_name(self):
        agent = CodingAgent(project_root="/tmp")
        assert agent.name == "CodingAgent"

    def test_description_mentions_fallback(self):
        agent = CodingAgent(project_root="/tmp")
        assert "fallback" in agent.description.lower()

    def test_intent_map_covers_all_capabilities(self):
        agent = CodingAgent(project_root="/tmp")
        assert set(agent.intent_map.keys()) == CAPABILITIES

    def test_does_not_support_dialogue(self):
        agent = CodingAgent(project_root="/tmp")
        assert agent.supports_dialogue is False


# -- Execution tests -------------------------------------------------------


class TestCodingAgentExecution:
    """Test the core _execute method with mocked subprocess."""

    @pytest.mark.asyncio
    async def test_execute_empty_prompt_returns_error(self):
        agent = CodingAgent(project_root="/tmp")
        result = await agent._execute(prompt="", capability="run_code")
        assert isinstance(result, AgentResponse)
        assert result.success is False

    @pytest.mark.asyncio
    async def test_execute_success(self, monkeypatch):
        agent = CodingAgent(project_root="/tmp")
        fake = FakeProcess(stdout="Done. Created foo.py", returncode=0)

        async def mock_exec(*args, **kwargs):
            return fake

        monkeypatch.setattr(asyncio, "create_subprocess_exec", mock_exec)
        result = await agent._execute(
            prompt="Create a hello world script",
            capability="create_file",
        )
        assert result.success is True
        assert "foo.py" in result.response

    @pytest.mark.asyncio
    async def test_execute_failure(self, monkeypatch):
        agent = CodingAgent(project_root="/tmp")
        fake = FakeProcess(stderr="Error: permission denied", returncode=1)

        async def mock_exec(*args, **kwargs):
            return fake

        monkeypatch.setattr(asyncio, "create_subprocess_exec", mock_exec)
        result = await agent._execute(
            prompt="Delete system32",
            capability="run_code",
        )
        assert result.success is False
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_execute_timeout(self, monkeypatch):
        agent = CodingAgent(project_root="/tmp", timeout=1)

        class SlowProcess:
            returncode = None

            async def communicate(self):
                await asyncio.sleep(10)
                return b"", b""

            def kill(self):
                pass

            async def wait(self):
                pass

        async def mock_exec(*args, **kwargs):
            return SlowProcess()

        monkeypatch.setattr(asyncio, "create_subprocess_exec", mock_exec)
        result = await agent._execute(
            prompt="Run something slow",
            capability="run_code",
        )
        assert result.success is False
        assert "Timed out" in result.response

    @pytest.mark.asyncio
    async def test_execute_binary_not_found(self, monkeypatch):
        agent = CodingAgent(
            project_root="/tmp", claude_binary="nonexistent-binary-xyz"
        )

        async def mock_exec(*args, **kwargs):
            raise FileNotFoundError("No such file")

        monkeypatch.setattr(asyncio, "create_subprocess_exec", mock_exec)
        result = await agent._execute(
            prompt="do something",
            capability="run_code",
        )
        assert result.success is False
        assert "not found" in result.response.lower()


# -- Preamble construction --------------------------------------------------


class TestPreambleConstruction:
    """Verify capability-specific preambles are generated."""

    def test_preamble_for_known_capability(self):
        preamble = CodingAgent._build_preamble("fix_bug")
        assert "fix" in preamble.lower()
        assert "TASK TYPE" in preamble

    def test_preamble_for_unknown_capability(self):
        preamble = CodingAgent._build_preamble("unknown_thing")
        assert "TASK TYPE" not in preamble
        assert "autonomous" in preamble.lower()

    def test_all_capabilities_have_guidance(self):
        for cap in CAPABILITIES:
            preamble = CodingAgent._build_preamble(cap)
            assert "TASK TYPE" in preamble, f"Missing guidance for {cap}"
