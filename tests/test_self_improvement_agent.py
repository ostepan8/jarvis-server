import asyncio

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from jarvis.night_agents.self_improvement_agent import SelfImprovementAgent


class TestSelfImprovementAgentProperties:
    def test_name(self):
        agent = SelfImprovementAgent(project_root="/fake")
        assert agent.name == "SelfImprovementAgent"

    def test_description(self):
        agent = SelfImprovementAgent(project_root="/fake")
        assert "autonomous" in agent.description.lower()

    def test_capabilities(self):
        agent = SelfImprovementAgent(project_root="/fake")
        assert "run_self_improvement" in agent.capabilities
        assert "get_improvement_report" in agent.capabilities
        assert len(agent.capabilities) == 2


class TestSelfImprovementAgentCapabilities:
    @pytest.mark.asyncio
    async def test_get_report_no_report(self):
        """When no report exists, should return 'no reports' message."""
        agent = SelfImprovementAgent(project_root="/fake")
        # Mock the service
        agent._service = MagicMock()
        agent._service.get_latest_report.return_value = None

        # Create a mock message
        message = MagicMock()
        message.content = {"capability": "get_improvement_report"}
        message.from_agent = "TestAgent"
        message.request_id = "req-1"
        message.id = "msg-1"

        # Mock send_capability_response
        agent.send_capability_response = AsyncMock()

        await agent._handle_capability_request(message)

        agent.send_capability_response.assert_called_once()
        call_args = agent.send_capability_response.call_args
        result = call_args.kwargs.get("result")
        assert "No improvement reports" in str(result)

    @pytest.mark.asyncio
    async def test_get_report_with_report(self):
        """When a report exists, should return its summary."""
        agent = SelfImprovementAgent(project_root="/fake")

        # Create a mock report
        mock_report = MagicMock()
        mock_report.to_summary_text.return_value = "Night cycle: 2 tasks, 1 succeeded"
        mock_report.to_dict.return_value = {"tasks_attempted": 2, "tasks_succeeded": 1}

        agent._service = MagicMock()
        agent._service.get_latest_report.return_value = mock_report

        message = MagicMock()
        message.content = {"capability": "get_improvement_report"}
        message.from_agent = "TestAgent"
        message.request_id = "req-1"
        message.id = "msg-1"

        agent.send_capability_response = AsyncMock()

        await agent._handle_capability_request(message)

        agent.send_capability_response.assert_called_once()
        call_args = agent.send_capability_response.call_args
        result = call_args.kwargs.get("result")
        assert result["success"] is True
        assert "Night cycle" in result["response"]

    @pytest.mark.asyncio
    async def test_run_self_improvement(self):
        """Should trigger the improvement cycle."""
        agent = SelfImprovementAgent(project_root="/fake")

        mock_report = MagicMock()
        mock_report.to_summary_text.return_value = "Done"
        mock_report.to_dict.return_value = {}
        mock_report.tasks_attempted = 1
        mock_report.tasks_succeeded = 1
        mock_report.tasks_failed = 0

        agent._service = MagicMock()
        agent._service.run_improvement_cycle = AsyncMock(return_value=mock_report)

        message = MagicMock()
        message.content = {"capability": "run_self_improvement"}
        message.from_agent = "TestAgent"
        message.request_id = "req-1"
        message.id = "msg-1"

        agent.send_capability_response = AsyncMock()

        await agent._handle_capability_request(message)

        agent._service.run_improvement_cycle.assert_called_once()
        agent.send_capability_response.assert_called_once()

    @pytest.mark.asyncio
    async def test_unknown_capability(self):
        """Unknown capability should return error response."""
        agent = SelfImprovementAgent(project_root="/fake")

        message = MagicMock()
        message.content = {"capability": "unknown_thing"}
        message.from_agent = "TestAgent"
        message.request_id = "req-1"
        message.id = "msg-1"

        agent.send_capability_response = AsyncMock()

        await agent._handle_capability_request(message)

        agent.send_capability_response.assert_called_once()
        call_args = agent.send_capability_response.call_args
        result = call_args.kwargs.get("result")
        assert result["success"] is False
        assert "Unknown" in result["response"] or "unknown" in result["response"]


class TestSelfImprovementAgentLifecycle:
    @pytest.mark.asyncio
    async def test_start_background_tasks_creates_task(self):
        """start_background_tasks should create a background task."""
        agent = SelfImprovementAgent(project_root="/fake")
        assert len(agent._background_tasks) == 0

        # Mock the _periodic_improvement to not actually run
        async def mock_periodic():
            await asyncio.sleep(1000)

        agent._periodic_improvement = mock_periodic
        await agent.start_background_tasks()

        assert len(agent._background_tasks) == 1

        # Clean up
        await agent.stop_background_tasks()

    @pytest.mark.asyncio
    async def test_handle_capability_response_returns_none(self):
        """_handle_capability_response should return None (no-op)."""
        agent = SelfImprovementAgent(project_root="/fake")
        result = await agent._handle_capability_response(MagicMock())
        assert result is None


class TestConfigIntegration:
    def test_feature_flag_exists(self):
        """The enable_self_improvement flag should exist in FeatureFlags."""
        from jarvis.core.config import FeatureFlags

        flags = FeatureFlags()
        assert hasattr(flags, "enable_self_improvement")
        assert flags.enable_self_improvement is True  # Default on

    def test_self_improvement_agent_importable_from_night_agents(self):
        """Should be importable from the night_agents package."""
        from jarvis.night_agents import SelfImprovementAgent

        assert SelfImprovementAgent is not None
