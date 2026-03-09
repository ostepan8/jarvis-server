"""Tests for CollaborationMixin (Phase 2).

Tests use a concrete TestAgent(NetworkAgent, CollaborationMixin) on
a real AgentNetwork to verify recruitment, budget enforcement, cycle
detection, and lead execution.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Dict, List, Set, Tuple
from unittest.mock import AsyncMock, MagicMock

import pytest

from jarvis.agents.agent_network import AgentNetwork
from jarvis.agents.base import NetworkAgent
from jarvis.agents.collaboration import CollaborationMixin
from jarvis.agents.message import Message
from jarvis.agents.response import AgentResponse
from jarvis.core.errors import (
    BudgetExhaustedError,
    CapabilityNotFoundError,
    CircularRecruitmentError,
)
from jarvis.core.mission import (
    MissionBrief,
    MissionBudget,
    MissionComplexity,
    MissionContext,
)


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

class LeadTestAgent(NetworkAgent, CollaborationMixin):
    """Concrete agent for testing the CollaborationMixin."""

    def __init__(self, name: str = "LeadAgent", ai_client=None):
        super().__init__(name)
        self.ai_client = ai_client
        self.tools = []
        self.intent_map = {
            "greet": self._greet,
        }

    @property
    def capabilities(self) -> Set[str]:
        return {"greet"}

    async def _greet(self, name: str = "World") -> Dict[str, Any]:
        return {"response": f"Hello, {name}!"}

    async def _handle_capability_request(self, message: Message) -> None:
        capability = message.content.get("capability")
        data = message.content.get("data", {})
        prompt = data.get("prompt", "")
        result = await self.run_capability(capability, name=prompt or "World")
        await self.send_capability_response(
            message.from_agent, result, message.request_id, message.id
        )

    async def _handle_capability_response(self, message: Message) -> None:
        pass


class ProviderAgent(NetworkAgent):
    """Simple provider agent that responds to capability requests."""

    def __init__(self, name: str, provided_capabilities: Set[str], response: Any = None):
        super().__init__(name)
        self._capabilities = provided_capabilities
        self._response = response or {"response": f"Result from {name}", "success": True}

    @property
    def capabilities(self) -> Set[str]:
        return self._capabilities

    async def _handle_capability_request(self, message: Message) -> None:
        capability = message.content.get("capability")
        if capability in self._capabilities:
            await self.send_capability_response(
                message.from_agent, self._response, message.request_id, message.id
            )

    async def _handle_capability_response(self, message: Message) -> None:
        pass


class ToolCallAIClient:
    """Mock AI client that returns configurable sequences of tool calls then text."""

    def __init__(self, responses: List[Tuple[str, Any]]):
        """
        Args:
            responses: List of (content, tool_calls) tuples.
                tool_calls should be a list of mock tool call objects or None.
        """
        self._responses = list(responses)
        self._call_count = 0

    async def strong_chat(self, messages, tools=None):
        if self._call_count < len(self._responses):
            content, tool_calls = self._responses[self._call_count]
            self._call_count += 1
            message = MagicMock()
            message.content = content
            return message, tool_calls
        # Default: return empty response with no tool calls
        message = MagicMock()
        message.content = "Done."
        return message, None

    async def weak_chat(self, messages, tools=None):
        return await self.strong_chat(messages, tools)


def make_tool_call(name: str, arguments: Dict[str, Any], call_id: str = "call_1"):
    """Create a mock tool call object."""
    call = MagicMock()
    call.id = call_id
    call.function = MagicMock()
    call.function.name = name
    call.function.arguments = json.dumps(arguments)
    return call


def make_brief(
    lead_agent: str = "LeadAgent",
    available_capabilities: Dict[str, List[str]] = None,
    budget: MissionBudget = None,
    context: MissionContext = None,
) -> MissionBrief:
    """Create a test MissionBrief."""
    if available_capabilities is None:
        available_capabilities = {
            "WeatherAgent": ["get_weather", "get_forecast"],
            "LightingAgent": ["set_color", "set_brightness"],
        }
    if budget is None:
        budget = MissionBudget(
            max_depth=3,
            remaining_depth=3,
            deadline=time.time() + 60,
            max_recruitments=5,
            remaining_recruitments=5,
        )
    if context is None:
        context = MissionContext(
            user_input="test request",
            recruitment_chain=[lead_agent],
        )

    return MissionBrief(
        user_input="test request",
        complexity=MissionComplexity.COMPLEX,
        lead_agent=lead_agent,
        lead_capability="chat",
        budget=budget,
        context=context,
        available_capabilities=available_capabilities,
    )


async def setup_network_with_agents(*agents: NetworkAgent) -> AgentNetwork:
    """Create and start an AgentNetwork with the given agents."""
    network = AgentNetwork()
    for agent in agents:
        network.register_agent(agent)
    await network.start()
    return network


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestRecruitableCapabilities:
    """Tests for get_recruitable_capabilities."""

    def test_excludes_own_agent(self):
        agent = LeadTestAgent("LeadAgent")
        brief = make_brief(
            available_capabilities={
                "LeadAgent": ["greet"],
                "WeatherAgent": ["get_weather"],
            }
        )
        recruitable = agent.get_recruitable_capabilities(brief)
        assert "LeadAgent" not in recruitable
        assert "WeatherAgent" in recruitable

    def test_returns_all_other_agents(self):
        agent = LeadTestAgent("LeadAgent")
        brief = make_brief()
        recruitable = agent.get_recruitable_capabilities(brief)
        assert "WeatherAgent" in recruitable
        assert "LightingAgent" in recruitable

    def test_empty_when_no_other_agents(self):
        agent = LeadTestAgent("LeadAgent")
        brief = make_brief(available_capabilities={"LeadAgent": ["greet"]})
        recruitable = agent.get_recruitable_capabilities(brief)
        assert recruitable == {}


class TestFormatRecruitmentContext:
    """Tests for format_recruitment_context."""

    def test_format_with_agents(self):
        agent = LeadTestAgent("LeadAgent")
        brief = make_brief()
        text = agent.format_recruitment_context(brief)
        assert "WeatherAgent" in text
        assert "get_weather" in text
        assert "LightingAgent" in text

    def test_format_with_no_agents(self):
        agent = LeadTestAgent("LeadAgent")
        brief = make_brief(available_capabilities={"LeadAgent": ["greet"]})
        text = agent.format_recruitment_context(brief)
        assert "No other agents" in text


class TestBuildRecruitToolDefinition:
    """Tests for _build_recruit_tool_definition."""

    def test_builds_valid_tool_spec(self):
        agent = LeadTestAgent("LeadAgent")
        brief = make_brief()
        tool = agent._build_recruit_tool_definition(brief)
        assert tool["type"] == "function"
        assert tool["function"]["name"] == "recruit_agent"
        params = tool["function"]["parameters"]
        assert "capability" in params["properties"]
        assert "prompt" in params["properties"]

    def test_enum_contains_available_capabilities(self):
        agent = LeadTestAgent("LeadAgent")
        brief = make_brief()
        tool = agent._build_recruit_tool_definition(brief)
        cap_enum = tool["function"]["parameters"]["properties"]["capability"]["enum"]
        assert "get_weather" in cap_enum
        assert "get_forecast" in cap_enum
        assert "set_color" in cap_enum

    def test_excludes_own_capabilities(self):
        agent = LeadTestAgent("LeadAgent")
        brief = make_brief(
            available_capabilities={
                "LeadAgent": ["greet"],
                "WeatherAgent": ["get_weather"],
            }
        )
        tool = agent._build_recruit_tool_definition(brief)
        cap_enum = tool["function"]["parameters"]["properties"]["capability"]["enum"]
        assert "greet" not in cap_enum
        assert "get_weather" in cap_enum


class TestFindCapabilityProvider:
    """Tests for _find_capability_provider."""

    def test_finds_correct_provider(self):
        agent = LeadTestAgent("LeadAgent")
        brief = make_brief()
        provider = agent._find_capability_provider("get_weather", brief)
        assert provider == "WeatherAgent"

    def test_returns_none_for_unknown_capability(self):
        agent = LeadTestAgent("LeadAgent")
        brief = make_brief()
        provider = agent._find_capability_provider("nonexistent", brief)
        assert provider is None

    def test_does_not_return_self(self):
        agent = LeadTestAgent("LeadAgent")
        brief = make_brief(
            available_capabilities={
                "LeadAgent": ["get_weather"],
                "WeatherAgent": ["get_weather"],
            }
        )
        provider = agent._find_capability_provider("get_weather", brief)
        assert provider == "WeatherAgent"


class TestRecruit:
    """Tests for the recruit method."""

    @pytest.mark.asyncio
    async def test_successful_recruitment(self):
        """Recruit should return result from provider agent."""
        lead = LeadTestAgent("LeadAgent")
        weather = ProviderAgent(
            "WeatherAgent",
            {"get_weather"},
            {"response": "72°F and sunny", "success": True},
        )
        network = await setup_network_with_agents(lead, weather)

        try:
            brief = make_brief()
            result = await lead.recruit(
                capability="get_weather",
                data={"prompt": "What's the weather?"},
                brief=brief,
            )
            assert result["response"] == "72°F and sunny"
            assert len(brief.context.recruitment_results) == 1
        finally:
            await network.stop()

    @pytest.mark.asyncio
    async def test_budget_exhausted_zero_depth(self):
        """Recruit should raise BudgetExhaustedError when depth is 0."""
        lead = LeadTestAgent("LeadAgent")
        network = await setup_network_with_agents(lead)

        try:
            brief = make_brief(
                budget=MissionBudget(
                    remaining_depth=0,
                    remaining_recruitments=5,
                    deadline=time.time() + 60,
                )
            )
            with pytest.raises(BudgetExhaustedError):
                await lead.recruit(
                    capability="get_weather",
                    data={"prompt": "test"},
                    brief=brief,
                )
        finally:
            await network.stop()

    @pytest.mark.asyncio
    async def test_budget_exhausted_zero_recruitments(self):
        """Recruit should raise BudgetExhaustedError when recruitments are 0."""
        lead = LeadTestAgent("LeadAgent")
        network = await setup_network_with_agents(lead)

        try:
            brief = make_brief(
                budget=MissionBudget(
                    remaining_depth=3,
                    remaining_recruitments=0,
                    deadline=time.time() + 60,
                )
            )
            with pytest.raises(BudgetExhaustedError):
                await lead.recruit(
                    capability="get_weather",
                    data={"prompt": "test"},
                    brief=brief,
                )
        finally:
            await network.stop()

    @pytest.mark.asyncio
    async def test_cycle_detection(self):
        """Recruit should raise CircularRecruitmentError for cycles."""
        lead = LeadTestAgent("LeadAgent")
        weather = ProviderAgent("WeatherAgent", {"get_weather"})
        network = await setup_network_with_agents(lead, weather)

        try:
            brief = make_brief(
                context=MissionContext(
                    user_input="test",
                    recruitment_chain=["LeadAgent", "WeatherAgent"],
                )
            )
            with pytest.raises(CircularRecruitmentError):
                await lead.recruit(
                    capability="get_weather",
                    data={"prompt": "test"},
                    brief=brief,
                )
        finally:
            await network.stop()

    @pytest.mark.asyncio
    async def test_capability_not_found(self):
        """Recruit should raise CapabilityNotFoundError for unknown capabilities."""
        lead = LeadTestAgent("LeadAgent")
        network = await setup_network_with_agents(lead)

        try:
            brief = make_brief()
            with pytest.raises(CapabilityNotFoundError):
                await lead.recruit(
                    capability="nonexistent",
                    data={"prompt": "test"},
                    brief=brief,
                )
        finally:
            await network.stop()

    @pytest.mark.asyncio
    async def test_multiple_recruitments_accumulate_context(self):
        """Multiple recruits should accumulate results in context."""
        lead = LeadTestAgent("LeadAgent")
        weather = ProviderAgent(
            "WeatherAgent", {"get_weather"}, {"response": "sunny"}
        )
        lighting = ProviderAgent(
            "LightingAgent", {"set_color"}, {"response": "lights set"}
        )
        network = await setup_network_with_agents(lead, weather, lighting)

        try:
            brief = make_brief()
            await lead.recruit("get_weather", {"prompt": "weather?"}, brief)
            await lead.recruit("set_color", {"prompt": "warm"}, brief)

            assert len(brief.context.recruitment_results) == 2
            assert brief.context.recruitment_results[0]["agent"] == "WeatherAgent"
            assert brief.context.recruitment_results[1]["agent"] == "LightingAgent"
            # Recruitments decremented
            assert brief.budget.remaining_recruitments == 3
        finally:
            await network.stop()

    @pytest.mark.asyncio
    async def test_recruitment_decrements_budget(self):
        """Each recruit call should decrement remaining_recruitments."""
        lead = LeadTestAgent("LeadAgent")
        weather = ProviderAgent("WeatherAgent", {"get_weather"}, {"response": "ok"})
        network = await setup_network_with_agents(lead, weather)

        try:
            brief = make_brief(
                budget=MissionBudget(
                    remaining_depth=3,
                    remaining_recruitments=2,
                    deadline=time.time() + 60,
                )
            )
            assert brief.budget.remaining_recruitments == 2
            await lead.recruit("get_weather", {"prompt": "test"}, brief)
            assert brief.budget.remaining_recruitments == 1
        finally:
            await network.stop()


class TestExecuteAsLead:
    """Tests for _execute_as_lead."""

    @pytest.mark.asyncio
    async def test_simple_response_no_tools(self):
        """Lead should return text response when LLM doesn't call tools."""
        ai_client = ToolCallAIClient([
            ("Here's your answer!", None),
        ])
        lead = LeadTestAgent("LeadAgent", ai_client=ai_client)
        network = await setup_network_with_agents(lead)

        try:
            brief = make_brief()
            result = await lead._execute_as_lead("Hello", brief)
            assert result["success"] is True
            assert result["response"] == "Here's your answer!"
        finally:
            await network.stop()

    @pytest.mark.asyncio
    async def test_own_tool_call(self):
        """Lead should be able to call its own capabilities via tools."""
        greet_call = make_tool_call("greet", {"name": "Alice"}, "call_greet")
        ai_client = ToolCallAIClient([
            ("", [greet_call]),
            ("Hello Alice! Nice to meet you.", None),
        ])
        lead = LeadTestAgent("LeadAgent", ai_client=ai_client)
        network = await setup_network_with_agents(lead)

        try:
            brief = make_brief()
            result = await lead._execute_as_lead("Greet Alice", brief)
            assert result["success"] is True
            assert "Hello Alice" in result["response"]
            assert len(result["actions"]) == 1
            assert result["actions"][0]["function"] == "greet"
        finally:
            await network.stop()

    @pytest.mark.asyncio
    async def test_recruit_tool_call(self):
        """Lead should recruit another agent via recruit_agent tool."""
        recruit_call = make_tool_call(
            "recruit_agent",
            {"capability": "get_weather", "prompt": "What's the weather?"},
            "call_recruit",
        )
        ai_client = ToolCallAIClient([
            ("", [recruit_call]),
            ("The weather is 72°F and sunny!", None),
        ])
        lead = LeadTestAgent("LeadAgent", ai_client=ai_client)
        weather = ProviderAgent(
            "WeatherAgent", {"get_weather"}, {"response": "72°F and sunny"}
        )
        network = await setup_network_with_agents(lead, weather)

        try:
            brief = make_brief()
            result = await lead._execute_as_lead("What's the weather?", brief)
            assert result["success"] is True
            assert "72°F" in result["response"]
            assert len(result["actions"]) == 1
            assert result["actions"][0]["function"] == "recruit_agent"
        finally:
            await network.stop()

    @pytest.mark.asyncio
    async def test_recruit_budget_exhausted_handled_gracefully(self):
        """When budget is exhausted during lead execution, it should return an error in the tool result."""
        recruit_call = make_tool_call(
            "recruit_agent",
            {"capability": "get_weather", "prompt": "weather?"},
            "call_recruit",
        )
        ai_client = ToolCallAIClient([
            ("", [recruit_call]),
            ("Sorry, I couldn't get the weather due to budget limits.", None),
        ])
        lead = LeadTestAgent("LeadAgent", ai_client=ai_client)
        weather = ProviderAgent("WeatherAgent", {"get_weather"})
        network = await setup_network_with_agents(lead, weather)

        try:
            brief = make_brief(
                budget=MissionBudget(
                    remaining_depth=0,
                    remaining_recruitments=0,
                    deadline=time.time() + 60,
                )
            )
            result = await lead._execute_as_lead("What's the weather?", brief)
            # Should not raise - error is handled in the tool call
            assert result["success"] is True
            # The action should contain an error
            assert "error" in result["actions"][0]["result"]
        finally:
            await network.stop()

    @pytest.mark.asyncio
    async def test_metadata_includes_lead_info(self):
        """Response metadata should identify the lead agent."""
        ai_client = ToolCallAIClient([("Response", None)])
        lead = LeadTestAgent("LeadAgent", ai_client=ai_client)
        network = await setup_network_with_agents(lead)

        try:
            brief = make_brief()
            result = await lead._execute_as_lead("test", brief)
            assert result["metadata"]["lead_agent"] == "LeadAgent"
            assert result["metadata"]["mission_complexity"] == "complex"
        finally:
            await network.stop()


class TestBuildLeadSystemPrompt:
    """Tests for _build_lead_system_prompt."""

    def test_includes_agent_name(self):
        agent = LeadTestAgent("MyAgent")
        brief = make_brief(lead_agent="MyAgent")
        prompt = agent._build_lead_system_prompt(brief)
        assert "MyAgent" in prompt

    def test_includes_user_input(self):
        agent = LeadTestAgent("LeadAgent")
        brief = make_brief()
        brief.user_input = "Turn on the lights and check weather"
        prompt = agent._build_lead_system_prompt(brief)
        assert "Turn on the lights and check weather" in prompt

    def test_includes_available_capabilities(self):
        agent = LeadTestAgent("LeadAgent")
        brief = make_brief()
        prompt = agent._build_lead_system_prompt(brief)
        assert "WeatherAgent" in prompt
        assert "get_weather" in prompt


class TestMalformedToolArguments:
    """Tests for handling malformed LLM tool call arguments."""

    @pytest.mark.asyncio
    async def test_empty_arguments_string(self):
        """Empty arguments string should return error, not crash."""
        call = MagicMock()
        call.id = "call_1"
        call.function = MagicMock()
        call.function.name = "recruit_agent"
        call.function.arguments = ""  # Empty string — invalid JSON

        ai_client = ToolCallAIClient([
            ("", [call]),
            ("I'll handle this myself.", None),
        ])
        lead = LeadTestAgent("LeadAgent", ai_client=ai_client)
        network = await setup_network_with_agents(lead)

        try:
            brief = make_brief()
            result = await lead._execute_as_lead("test", brief)
            assert result["success"] is True
            # Should have an error in the action, not a crash
            assert "error" in result["actions"][0]["result"]
            assert "Invalid arguments" in result["actions"][0]["result"]["error"]
        finally:
            await network.stop()

    @pytest.mark.asyncio
    async def test_none_arguments(self):
        """None arguments should return error, not crash."""
        call = MagicMock()
        call.id = "call_1"
        call.function = MagicMock()
        call.function.name = "recruit_agent"
        call.function.arguments = None  # None — will TypeError in json.loads

        ai_client = ToolCallAIClient([
            ("", [call]),
            ("Handled it.", None),
        ])
        lead = LeadTestAgent("LeadAgent", ai_client=ai_client)
        network = await setup_network_with_agents(lead)

        try:
            brief = make_brief()
            result = await lead._execute_as_lead("test", brief)
            assert result["success"] is True
            assert "error" in result["actions"][0]["result"]
        finally:
            await network.stop()

    @pytest.mark.asyncio
    async def test_invalid_json_arguments(self):
        """Malformed JSON arguments should return error, not crash."""
        call = MagicMock()
        call.id = "call_1"
        call.function = MagicMock()
        call.function.name = "recruit_agent"
        call.function.arguments = '{"capability": "get_weather", "prompt": '  # Truncated

        ai_client = ToolCallAIClient([
            ("", [call]),
            ("Handled without weather.", None),
        ])
        lead = LeadTestAgent("LeadAgent", ai_client=ai_client)
        network = await setup_network_with_agents(lead)

        try:
            brief = make_brief()
            result = await lead._execute_as_lead("test", brief)
            assert result["success"] is True
            assert "error" in result["actions"][0]["result"]
        finally:
            await network.stop()


class TestBudgetLockConcurrency:
    """Tests for budget lock preventing race conditions."""

    @pytest.mark.asyncio
    async def test_parallel_recruits_respect_budget_limit(self):
        """Two parallel recruits with budget=1 should only allow one."""
        lead = LeadTestAgent("LeadAgent")
        weather = ProviderAgent("WeatherAgent", {"get_weather"}, {"response": "sunny"})
        lighting = ProviderAgent("LightingAgent", {"set_color"}, {"response": "warm"})
        network = await setup_network_with_agents(lead, weather, lighting)

        try:
            brief = make_brief(
                budget=MissionBudget(
                    remaining_depth=3,
                    remaining_recruitments=1,  # Only 1 recruit allowed
                    deadline=time.time() + 30,
                )
            )

            async def recruit_weather():
                return await lead.recruit("get_weather", {"prompt": "w"}, brief)

            async def recruit_lights():
                return await lead.recruit("set_color", {"prompt": "l"}, brief)

            # Run both concurrently — only one should succeed
            results = await asyncio.gather(
                recruit_weather(), recruit_lights(), return_exceptions=True
            )

            successes = [r for r in results if not isinstance(r, Exception)]
            errors = [r for r in results if isinstance(r, BudgetExhaustedError)]
            assert len(successes) == 1
            assert len(errors) == 1
        finally:
            await network.stop()


class TestRecruitCleansUpActiveTasks:
    """Tests that recruit() cleans up active_tasks after completion."""

    @pytest.mark.asyncio
    async def test_active_tasks_cleaned_after_successful_recruit(self):
        """active_tasks entry from recruit should be removed after success."""
        lead = LeadTestAgent("LeadAgent")
        weather = ProviderAgent("WeatherAgent", {"get_weather"}, {"response": "sunny"})
        network = await setup_network_with_agents(lead, weather)

        try:
            brief = make_brief()
            # Before recruit, no active tasks
            initial_count = len(lead.active_tasks)

            await lead.recruit("get_weather", {"prompt": "weather?"}, brief)

            # After recruit, the entry should have been cleaned up
            assert len(lead.active_tasks) == initial_count
        finally:
            await network.stop()

    @pytest.mark.asyncio
    async def test_active_tasks_cleaned_after_failed_recruit(self):
        """active_tasks entry should be cleaned up even if recruit times out."""
        lead = LeadTestAgent("LeadAgent")
        # No provider registered — the request will time out

        class SilentAgent(NetworkAgent):
            """Agent that receives but never responds."""

            @property
            def capabilities(self):
                return {"get_weather"}

            async def _handle_capability_request(self, message):
                pass  # Never responds

            async def _handle_capability_response(self, message):
                pass

        silent = SilentAgent("WeatherAgent")
        network = await setup_network_with_agents(lead, silent)

        try:
            brief = make_brief(
                budget=MissionBudget(
                    remaining_depth=3,
                    remaining_recruitments=5,
                    deadline=time.time() + 0.3,
                )
            )
            initial_count = len(lead.active_tasks)

            with pytest.raises(Exception):
                await lead.recruit(
                    "get_weather", {"prompt": "weather?"}, brief, timeout=0.2
                )

            # Even on failure, active_tasks should be cleaned up
            assert len(lead.active_tasks) == initial_count
        finally:
            await network.stop()


class TestLLMCallTimeout:
    """Tests for LLM API call timeout in lead execution."""

    @pytest.mark.asyncio
    async def test_llm_hang_times_out_gracefully(self):
        """If strong_chat hangs, lead should timeout and return partial results."""

        class HangingAIClient:
            async def strong_chat(self, messages, tools=None):
                await asyncio.sleep(100)  # Simulate hang

        lead = LeadTestAgent("LeadAgent", ai_client=HangingAIClient())
        network = await setup_network_with_agents(lead)

        try:
            brief = make_brief(
                budget=MissionBudget(
                    remaining_depth=3,
                    remaining_recruitments=5,
                    deadline=time.time() + 0.2,  # 200ms deadline
                )
            )
            result = await lead._execute_as_lead("test", brief)
            assert result["success"] is True
            # Should have timed out, not hung forever
            assert result["metadata"].get("budget_expired") is True
        finally:
            await network.stop()
