"""Integration tests for multi-agent coordination (Phase 5).

Full network integration tests with mock agents verifying the coordinator
+ lead agent pattern end-to-end.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Dict, List, Set
from unittest.mock import MagicMock

import pytest

from jarvis.agents.agent_network import AgentNetwork
from jarvis.agents.base import NetworkAgent
from jarvis.agents.collaboration import CollaborationMixin
from jarvis.agents.message import Message
from jarvis.agents.response import AgentResponse
from jarvis.core.errors import BudgetExhaustedError, CircularRecruitmentError
from jarvis.core.mission import (
    MissionBrief,
    MissionBudget,
    MissionComplexity,
    MissionContext,
)
from jarvis.core.orchestrator import RequestOrchestrator, RequestMetadata
from jarvis.core.response_logger import ResponseLogger, RequestTimer


# ---------------------------------------------------------------------------
# Test agents
# ---------------------------------------------------------------------------

class MockAIClient:
    """AI client returning configurable sequences of responses."""

    def __init__(self, responses=None, weak_response=None):
        self._responses = list(responses or [])
        self._weak_response = weak_response or '{"complexity": "simple"}'
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
        msg = MagicMock()
        msg.content = self._weak_response
        return msg, None


def make_tool_call(name: str, arguments: Dict[str, Any], call_id: str = "call_1"):
    call = MagicMock()
    call.id = call_id
    call.function = MagicMock()
    call.function.name = name
    call.function.arguments = json.dumps(arguments)
    return call


class LeadAgent(NetworkAgent, CollaborationMixin):
    """Lead agent that can recruit and execute as lead."""

    def __init__(self, name: str, ai_client, capabilities_set: Set[str] = None):
        super().__init__(name)
        self.ai_client = ai_client
        self._capabilities = capabilities_set or {"chat"}
        self.tools = []

    @property
    def capabilities(self) -> Set[str]:
        return self._capabilities

    async def _handle_capability_request(self, message: Message) -> None:
        capability = message.content.get("capability")
        if capability not in self._capabilities:
            return

        data = message.content.get("data", {})
        prompt = data.get("prompt", "")

        mission_brief_data = data.get("mission_brief")
        if mission_brief_data:
            brief = MissionBrief.from_dict(mission_brief_data)
            result = await self._execute_as_lead(prompt, brief)
        else:
            # Simple response
            result = AgentResponse.success_response(
                response=f"Simple response from {self.name}: {prompt}"
            ).to_dict()

        await self.send_capability_response(
            message.from_agent, result, message.request_id, message.id
        )

    async def _handle_capability_response(self, message: Message) -> None:
        pass


class ProviderAgent(NetworkAgent):
    """Simple agent that responds to capability requests."""

    def __init__(self, name: str, capabilities: Set[str], response: Any = None):
        super().__init__(name)
        self._capabilities = capabilities
        self._response = response or {
            "response": f"Result from {name}",
            "success": True,
        }

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


class ErrorAgent(NetworkAgent):
    """Agent that always returns an error."""

    def __init__(self, name: str, capabilities: Set[str]):
        super().__init__(name)
        self._capabilities = capabilities

    @property
    def capabilities(self) -> Set[str]:
        return self._capabilities

    async def _handle_capability_request(self, message: Message) -> None:
        await self.send_error(
            message.from_agent,
            "Service unavailable",
            message.request_id,
        )

    async def _handle_capability_response(self, message: Message) -> None:
        pass


class SlowAgent(NetworkAgent):
    """Agent that takes too long to respond."""

    def __init__(self, name: str, capabilities: Set[str], delay: float = 10.0):
        super().__init__(name)
        self._capabilities = capabilities
        self._delay = delay

    @property
    def capabilities(self) -> Set[str]:
        return self._capabilities

    async def _handle_capability_request(self, message: Message) -> None:
        await asyncio.sleep(self._delay)
        await self.send_capability_response(
            message.from_agent,
            {"response": "Finally done", "success": True},
            message.request_id,
            message.id,
        )

    async def _handle_capability_response(self, message: Message) -> None:
        pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_response_logger():
    logger = MagicMock(spec=ResponseLogger)
    from unittest.mock import AsyncMock
    logger.log_successful_interaction = AsyncMock()
    logger.log_failed_interaction = AsyncMock()
    logger.close = AsyncMock()
    return logger


async def setup_full_network(
    agents: List[NetworkAgent],
    ai_client=None,
    enable_coordinator: bool = True,
) -> tuple[RequestOrchestrator, AgentNetwork]:
    network = AgentNetwork()
    for agent in agents:
        network.register_agent(agent)
    await network.start()

    orchestrator = RequestOrchestrator(
        network=network,
        protocol_runtime=None,
        response_logger=make_response_logger(),
        logger=MagicMock(),
        response_timeout=10.0,
        ai_client=ai_client,
        enable_coordinator=enable_coordinator,
    )
    return orchestrator, network


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------

class TestCoordinatorLeadAgentIntegration:
    """End-to-end tests for coordinator + lead agent pattern."""

    @pytest.mark.asyncio
    async def test_simple_request_bypasses_coordinator(self):
        """Simple requests should fall through coordinator to NLU."""
        ai_client = MockAIClient(
            weak_response='{"complexity": "simple", "lead_agent": "ChatAgent", "lead_capability": "chat"}',
        )
        # NLU agent to handle intent_matching
        nlu = ProviderAgent("NLUAgent", {"intent_matching"}, {
            "response": "Simple response via NLU",
            "success": True,
        })
        chat = LeadAgent("ChatAgent", ai_client, {"chat"})
        orchestrator, network = await setup_full_network(
            [nlu, chat], ai_client=ai_client
        )

        try:
            result = await orchestrator.process_request(
                "what's the weather?", "UTC"
            )
            # Should have gone through NLU (coordinator said simple)
            assert "response" in result
        finally:
            await network.stop()

    @pytest.mark.asyncio
    async def test_complex_request_dispatches_to_lead(self):
        """Complex requests should be dispatched to the lead agent."""
        recruit_call = make_tool_call(
            "recruit_agent",
            {"capability": "get_weather", "prompt": "What's the weather?"},
            "call_1",
        )
        ai_client = MockAIClient(
            responses=[
                ("", [recruit_call]),
                ("It's 72°F and sunny, and I've set your lights to warm!", None),
            ],
            weak_response='{"complexity": "complex", "lead_agent": "ChatAgent", "lead_capability": "chat"}',
        )
        chat = LeadAgent("ChatAgent", ai_client, {"chat"})
        weather = ProviderAgent(
            "WeatherAgent",
            {"get_weather"},
            {"response": "72°F and sunny", "success": True},
        )
        lighting = ProviderAgent(
            "LightingAgent",
            {"set_color"},
            {"response": "Lights set to warm", "success": True},
        )
        orchestrator, network = await setup_full_network(
            [chat, weather, lighting], ai_client=ai_client
        )

        try:
            result = await orchestrator.process_request(
                "Check weather and set lights to warm", "UTC"
            )
            assert result is not None
            assert result.get("coordinator") is True
            assert result.get("lead_agent") == "ChatAgent"
            assert "72°F" in result.get("response", "")
        finally:
            await network.stop()

    @pytest.mark.asyncio
    async def test_coordinator_disabled_uses_nlu(self):
        """With coordinator disabled, all requests go to NLU."""
        ai_client = MockAIClient(
            weak_response='{"complexity": "complex", "lead_agent": "ChatAgent", "lead_capability": "chat"}',
        )
        nlu = ProviderAgent("NLUAgent", {"intent_matching"}, {
            "response": "NLU response",
            "success": True,
        })
        chat = LeadAgent("ChatAgent", ai_client, {"chat"})
        orchestrator, network = await setup_full_network(
            [nlu, chat],
            ai_client=ai_client,
            enable_coordinator=False,
        )

        try:
            result = await orchestrator.process_request(
                "Check weather and set lights", "UTC"
            )
            # Should NOT have coordinator flag
            assert result.get("coordinator") is not True
        finally:
            await network.stop()


class TestLeadAgentRecruitmentIntegration:
    """Tests for recruitment mechanics in full network context."""

    @pytest.mark.asyncio
    async def test_lead_recruits_multiple_agents(self):
        """Lead agent should be able to recruit multiple agents sequentially."""
        weather_call = make_tool_call(
            "recruit_agent",
            {"capability": "get_weather", "prompt": "weather?"},
            "call_weather",
        )
        lights_call = make_tool_call(
            "recruit_agent",
            {"capability": "set_color", "prompt": "warm lights"},
            "call_lights",
        )
        ai_client = MockAIClient(responses=[
            ("", [weather_call]),
            ("", [lights_call]),
            ("Done! Weather is sunny and lights are warm.", None),
        ])
        lead = LeadAgent("ChatAgent", ai_client, {"chat"})
        weather = ProviderAgent(
            "WeatherAgent", {"get_weather"}, {"response": "sunny"}
        )
        lighting = ProviderAgent(
            "LightingAgent", {"set_color"}, {"response": "lights warm"}
        )
        network = AgentNetwork()
        for agent in [lead, weather, lighting]:
            network.register_agent(agent)
        await network.start()

        try:
            brief = MissionBrief(
                user_input="Check weather and set lights",
                complexity=MissionComplexity.COMPLEX,
                lead_agent="ChatAgent",
                lead_capability="chat",
                budget=MissionBudget(
                    max_depth=3,
                    remaining_depth=3,
                    deadline=time.time() + 30,
                    max_recruitments=5,
                    remaining_recruitments=5,
                ),
                context=MissionContext(
                    user_input="Check weather and set lights",
                    recruitment_chain=["ChatAgent"],
                ),
                available_capabilities={
                    "WeatherAgent": ["get_weather"],
                    "LightingAgent": ["set_color"],
                },
            )
            result = await lead._execute_as_lead(
                "Check weather and set lights", brief
            )
            assert result["success"] is True
            assert len(result["actions"]) == 2
            assert result["actions"][0]["function"] == "recruit_agent"
            assert result["actions"][1]["function"] == "recruit_agent"
        finally:
            await network.stop()

    @pytest.mark.asyncio
    async def test_failed_recruitment_handled_gracefully(self):
        """When a recruited agent returns an error, lead should handle it."""
        recruit_call = make_tool_call(
            "recruit_agent",
            {"capability": "get_weather", "prompt": "weather?"},
            "call_weather",
        )
        ai_client = MockAIClient(responses=[
            ("", [recruit_call]),
            ("Sorry, I couldn't get the weather.", None),
        ])
        lead = LeadAgent("ChatAgent", ai_client, {"chat"})
        error_weather = ErrorAgent("WeatherAgent", {"get_weather"})
        network = AgentNetwork()
        for agent in [lead, error_weather]:
            network.register_agent(agent)
        await network.start()

        try:
            brief = MissionBrief(
                user_input="What's the weather?",
                complexity=MissionComplexity.COMPLEX,
                lead_agent="ChatAgent",
                lead_capability="chat",
                budget=MissionBudget(
                    max_depth=3,
                    remaining_depth=3,
                    deadline=time.time() + 30,
                    max_recruitments=5,
                    remaining_recruitments=5,
                ),
                context=MissionContext(
                    user_input="What's the weather?",
                    recruitment_chain=["ChatAgent"],
                ),
                available_capabilities={
                    "WeatherAgent": ["get_weather"],
                },
            )
            result = await lead._execute_as_lead("What's the weather?", brief)
            # Should not crash - result should still be a valid response
            assert result["success"] is True
        finally:
            await network.stop()

    @pytest.mark.asyncio
    async def test_budget_exhaustion_returns_partial_results(self):
        """When budget runs out, lead should respond with what it has."""
        recruit_call = make_tool_call(
            "recruit_agent",
            {"capability": "get_weather", "prompt": "weather?"},
            "call_1",
        )
        ai_client = MockAIClient(responses=[
            ("", [recruit_call]),
            ("I could only partially help.", None),
        ])
        lead = LeadAgent("ChatAgent", ai_client, {"chat"})
        weather = ProviderAgent("WeatherAgent", {"get_weather"})
        network = AgentNetwork()
        for agent in [lead, weather]:
            network.register_agent(agent)
        await network.start()

        try:
            brief = MissionBrief(
                user_input="Do many things",
                complexity=MissionComplexity.COMPLEX,
                lead_agent="ChatAgent",
                lead_capability="chat",
                budget=MissionBudget(
                    max_depth=0,
                    remaining_depth=0,
                    deadline=time.time() + 30,
                    max_recruitments=0,
                    remaining_recruitments=0,
                ),
                context=MissionContext(
                    user_input="Do many things",
                    recruitment_chain=["ChatAgent"],
                ),
                available_capabilities={
                    "WeatherAgent": ["get_weather"],
                },
            )
            result = await lead._execute_as_lead("Do many things", brief)
            # Should still return a valid response, but the action should have an error
            assert result["success"] is True
            assert "error" in result["actions"][0]["result"]
        finally:
            await network.stop()

    @pytest.mark.asyncio
    async def test_cycle_detection_prevents_loop(self):
        """Recruitment should detect and prevent circular chains."""
        recruit_call = make_tool_call(
            "recruit_agent",
            {"capability": "get_weather", "prompt": "weather?"},
            "call_1",
        )
        ai_client = MockAIClient(responses=[
            ("", [recruit_call]),
            ("Couldn't recruit due to cycle.", None),
        ])
        lead = LeadAgent("ChatAgent", ai_client, {"chat"})
        weather = ProviderAgent("WeatherAgent", {"get_weather"})
        network = AgentNetwork()
        for agent in [lead, weather]:
            network.register_agent(agent)
        await network.start()

        try:
            brief = MissionBrief(
                user_input="test",
                complexity=MissionComplexity.COMPLEX,
                lead_agent="ChatAgent",
                lead_capability="chat",
                budget=MissionBudget(
                    max_depth=3,
                    remaining_depth=3,
                    deadline=time.time() + 30,
                    max_recruitments=5,
                    remaining_recruitments=5,
                ),
                context=MissionContext(
                    user_input="test",
                    # WeatherAgent already in chain - cycle!
                    recruitment_chain=["ChatAgent", "WeatherAgent"],
                ),
                available_capabilities={
                    "WeatherAgent": ["get_weather"],
                },
            )
            result = await lead._execute_as_lead("test", brief)
            assert result["success"] is True
            # The recruitment should have failed with cycle error
            assert "error" in result["actions"][0]["result"]
            assert "Circular" in result["actions"][0]["result"]["error"]
        finally:
            await network.stop()


class TestOrchestratorRegressions:
    """Regression tests ensuring existing behavior is preserved."""

    @pytest.mark.asyncio
    async def test_simple_request_still_works_with_coordinator_enabled(self):
        """Simple requests should work identically with coordinator enabled."""
        ai_client = MockAIClient(
            weak_response='{"complexity": "simple", "lead_agent": "NLUAgent", "lead_capability": "intent_matching"}',
        )
        nlu = ProviderAgent("NLUAgent", {"intent_matching"}, {
            "response": "Hello! How can I help?",
            "success": True,
        })
        orchestrator, network = await setup_full_network(
            [nlu], ai_client=ai_client
        )

        try:
            result = await orchestrator.process_request("hello", "UTC")
            assert "response" in result
            assert result.get("coordinator") is not True
        finally:
            await network.stop()

    @pytest.mark.asyncio
    async def test_no_ai_client_falls_through_to_nlu(self):
        """Without an AI client, coordinator is bypassed entirely."""
        nlu = ProviderAgent("NLUAgent", {"intent_matching"}, {
            "response": "NLU handled it",
            "success": True,
        })
        orchestrator, network = await setup_full_network(
            [nlu], ai_client=None
        )

        try:
            result = await orchestrator.process_request(
                "complex multi-agent request", "UTC"
            )
            assert "response" in result
            assert result.get("coordinator") is not True
        finally:
            await network.stop()
