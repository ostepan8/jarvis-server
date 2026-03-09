"""Tests for CalendarAgent lead agent behavior (Phase 4).

Tests verify that CalendarAgent correctly detects mission_brief in capability
requests and delegates to _execute_as_lead, while preserving normal
calendar behavior when no mission_brief is present.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Dict, List, Set
from unittest.mock import AsyncMock, MagicMock

import pytest

from jarvis.agents.agent_network import AgentNetwork
from jarvis.agents.base import NetworkAgent
from jarvis.agents.calendar_agent.agent import CollaborativeCalendarAgent
from jarvis.agents.message import Message
from jarvis.core.mission import (
    MissionBrief,
    MissionBudget,
    MissionComplexity,
    MissionContext,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class MockAIClient:
    """AI client returning configurable responses."""

    def __init__(self, responses=None):
        self._responses = list(responses or [])
        self._call_count = 0

    async def strong_chat(self, messages, tools=None):
        if self._call_count < len(self._responses):
            content, tool_calls = self._responses[self._call_count]
            self._call_count += 1
            msg = MagicMock()
            msg.content = content
            return msg, tool_calls
        msg = MagicMock()
        msg.content = "Default response"
        return msg, None

    async def weak_chat(self, messages, tools=None):
        return await self.strong_chat(messages, tools)


def make_mock_calendar_service():
    """Create a mock calendar service with all required methods.

    Uses MagicMock so any attribute access returns a mock callable,
    which satisfies CalendarFunctionRegistry._build_function_map().
    """
    return MagicMock()


class ProviderAgent(NetworkAgent):
    """Simple agent that responds to capability requests."""

    def __init__(self, name: str, capabilities: Set[str], response: Any = None):
        super().__init__(name)
        self._capabilities = capabilities
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


def make_tool_call(name: str, arguments: Dict[str, Any], call_id: str = "call_1"):
    call = MagicMock()
    call.id = call_id
    call.function = MagicMock()
    call.function.name = name
    call.function.arguments = json.dumps(arguments)
    return call


def make_brief(
    lead_agent: str = "CalendarAgent",
    available_capabilities: Dict[str, List[str]] = None,
) -> MissionBrief:
    return MissionBrief(
        user_input="Check my calendar and get the weather",
        complexity=MissionComplexity.COMPLEX,
        lead_agent=lead_agent,
        lead_capability="create_event",
        budget=MissionBudget(
            max_depth=3,
            remaining_depth=3,
            deadline=time.time() + 60,
            max_recruitments=5,
            remaining_recruitments=5,
        ),
        context=MissionContext(
            user_input="Check my calendar and get the weather",
            recruitment_chain=[lead_agent],
        ),
        available_capabilities=available_capabilities or {
            "CalendarAgent": ["create_event", "list_events"],
            "WeatherAgent": ["get_weather"],
        },
    )


async def setup_network(*agents: NetworkAgent) -> AgentNetwork:
    network = AgentNetwork()
    for agent in agents:
        network.register_agent(agent)
    await network.start()
    return network


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestCalendarAgentLeadPrompt:
    """Tests for CalendarAgent's custom lead system prompt."""

    def test_includes_scheduling_focus(self):
        ai_client = MockAIClient()
        cal = CollaborativeCalendarAgent(ai_client, make_mock_calendar_service())
        brief = make_brief()
        prompt = cal._build_lead_system_prompt(brief)
        assert "scheduling" in prompt.lower() or "calendar" in prompt.lower()

    def test_includes_user_request(self):
        ai_client = MockAIClient()
        cal = CollaborativeCalendarAgent(ai_client, make_mock_calendar_service())
        brief = make_brief()
        prompt = cal._build_lead_system_prompt(brief)
        assert brief.user_input in prompt

    def test_includes_available_capabilities(self):
        ai_client = MockAIClient()
        cal = CollaborativeCalendarAgent(ai_client, make_mock_calendar_service())
        brief = make_brief()
        prompt = cal._build_lead_system_prompt(brief)
        assert "WeatherAgent" in prompt


class TestCalendarAgentCollaborationMixin:
    """Verify CalendarAgent has CollaborationMixin methods."""

    def test_has_recruit_method(self):
        ai_client = MockAIClient()
        cal = CollaborativeCalendarAgent(ai_client, make_mock_calendar_service())
        assert hasattr(cal, "recruit")

    def test_has_execute_as_lead_method(self):
        ai_client = MockAIClient()
        cal = CollaborativeCalendarAgent(ai_client, make_mock_calendar_service())
        assert hasattr(cal, "_execute_as_lead")

    def test_has_get_recruitable_capabilities(self):
        ai_client = MockAIClient()
        cal = CollaborativeCalendarAgent(ai_client, make_mock_calendar_service())
        assert hasattr(cal, "get_recruitable_capabilities")

    def test_recruitable_excludes_own_agent(self):
        ai_client = MockAIClient()
        cal = CollaborativeCalendarAgent(ai_client, make_mock_calendar_service())
        brief = make_brief()
        recruitable = cal.get_recruitable_capabilities(brief)
        assert "CalendarAgent" not in recruitable
        assert "WeatherAgent" in recruitable


class TestCalendarAgentMissionBriefDetection:
    """Tests that CalendarAgent correctly routes based on mission_brief."""

    @pytest.mark.asyncio
    async def test_lead_execution_via_execute_as_lead(self):
        """Verify _execute_as_lead works correctly on CalendarAgent."""
        ai_client = MockAIClient([
            ("Your calendar is clear and sunny weather ahead!", None),
        ])
        cal = CollaborativeCalendarAgent(ai_client, make_mock_calendar_service())
        network = await setup_network(cal)

        try:
            brief = make_brief()
            result = await cal._execute_as_lead("Check calendar and weather", brief)
            assert result["success"] is True
            assert result["metadata"]["lead_agent"] == "CalendarAgent"
            assert ai_client._call_count == 1
        finally:
            await network.stop()

    @pytest.mark.asyncio
    async def test_lead_execution_with_recruitment(self):
        """CalendarAgent as lead should be able to recruit WeatherAgent."""
        recruit_call = make_tool_call(
            "recruit_agent",
            {"capability": "get_weather", "prompt": "What's the weather?"},
            "call_recruit",
        )
        ai_client = MockAIClient([
            ("", [recruit_call]),
            ("Your calendar is clear and it's 72°F and sunny!", None),
        ])
        cal = CollaborativeCalendarAgent(ai_client, make_mock_calendar_service())
        weather = ProviderAgent(
            "WeatherAgent", {"get_weather"}, {"response": "72°F and sunny"}
        )
        network = await setup_network(cal, weather)

        try:
            brief = make_brief()
            result = await cal._execute_as_lead("Check calendar and weather", brief)
            assert result["success"] is True
            assert ai_client._call_count == 2
            assert len(result["actions"]) == 1
            assert result["actions"][0]["function"] == "recruit_agent"
        finally:
            await network.stop()
