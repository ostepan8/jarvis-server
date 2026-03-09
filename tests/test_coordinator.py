"""Tests for coordinator integration in RequestOrchestrator (Phase 3).

Tests cover coordinator classification, simple passthrough, complex dispatch,
fallback on failure, catalog building, and budget creation.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Dict, List, Set, Tuple
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from jarvis.agents.agent_network import AgentNetwork
from jarvis.agents.base import NetworkAgent
from jarvis.agents.message import Message
from jarvis.core.mission import MissionBrief, MissionComplexity
from jarvis.core.orchestrator import RequestOrchestrator, RequestMetadata
from jarvis.core.response_logger import ResponseLogger, RequestTimer


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

class MockAIClient:
    """AI client that returns configurable responses."""

    def __init__(self, weak_response: str = '{"complexity": "simple"}'):
        self._weak_response = weak_response

    async def strong_chat(self, messages, tools=None):
        msg = MagicMock()
        msg.content = "Strong response"
        return msg, None

    async def weak_chat(self, messages, tools=None):
        msg = MagicMock()
        msg.content = self._weak_response
        return msg, None


class SimpleAgent(NetworkAgent):
    """Simple test agent that responds to capability requests."""

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


def make_response_logger() -> ResponseLogger:
    """Create a mock ResponseLogger."""
    logger = MagicMock(spec=ResponseLogger)
    logger.log_successful_interaction = AsyncMock()
    logger.log_failed_interaction = AsyncMock()
    logger.close = AsyncMock()
    return logger


def make_logger() -> MagicMock:
    """Create a mock JarvisLogger."""
    logger = MagicMock()
    logger.log = MagicMock()
    return logger


async def setup_orchestrator(
    agents: List[NetworkAgent],
    ai_client=None,
    enable_coordinator: bool = True,
) -> Tuple[RequestOrchestrator, AgentNetwork]:
    """Create a network with agents and an orchestrator."""
    network = AgentNetwork()
    for agent in agents:
        network.register_agent(agent)
    await network.start()

    orchestrator = RequestOrchestrator(
        network=network,
        protocol_runtime=None,
        response_logger=make_response_logger(),
        logger=make_logger(),
        response_timeout=10.0,
        ai_client=ai_client,
        enable_coordinator=enable_coordinator,
    )
    return orchestrator, network


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestBuildCapabilityCatalog:
    """Tests for _build_capability_catalog."""

    @pytest.mark.asyncio
    async def test_builds_catalog_from_registry(self):
        chat = SimpleAgent("ChatAgent", {"chat"})
        weather = SimpleAgent("WeatherAgent", {"get_weather", "get_forecast"})
        orchestrator, network = await setup_orchestrator([chat, weather])

        try:
            catalog = orchestrator._build_capability_catalog()
            assert "ChatAgent" in catalog
            assert "chat" in catalog["ChatAgent"]
            assert "WeatherAgent" in catalog
            assert "get_weather" in catalog["WeatherAgent"]
        finally:
            await network.stop()

    @pytest.mark.asyncio
    async def test_filters_intent_matching(self):
        """intent_matching should not appear in the catalog."""
        nlu = SimpleAgent("NLUAgent", {"intent_matching"})
        chat = SimpleAgent("ChatAgent", {"chat"})
        orchestrator, network = await setup_orchestrator([nlu, chat])

        try:
            catalog = orchestrator._build_capability_catalog()
            assert "NLUAgent" not in catalog
            assert "ChatAgent" in catalog
        finally:
            await network.stop()

    @pytest.mark.asyncio
    async def test_respects_allowed_agents(self):
        chat = SimpleAgent("ChatAgent", {"chat"})
        weather = SimpleAgent("WeatherAgent", {"get_weather"})
        orchestrator, network = await setup_orchestrator([chat, weather])

        try:
            catalog = orchestrator._build_capability_catalog(
                allowed_agents={"ChatAgent"}
            )
            assert "ChatAgent" in catalog
            assert "WeatherAgent" not in catalog
        finally:
            await network.stop()


class TestClassifyComplexity:
    """Tests for _classify_complexity."""

    @pytest.mark.asyncio
    async def test_simple_classification(self):
        ai_client = MockAIClient(
            '{"complexity": "simple", "lead_agent": "WeatherAgent", "lead_capability": "get_weather"}'
        )
        weather = SimpleAgent("WeatherAgent", {"get_weather"})
        orchestrator, network = await setup_orchestrator([weather], ai_client=ai_client)

        try:
            result = await orchestrator._classify_complexity(
                "What's the weather?", {"WeatherAgent": ["get_weather"]}
            )
            assert result["complexity"] == "simple"
            assert result["lead_agent"] == "WeatherAgent"
        finally:
            await network.stop()

    @pytest.mark.asyncio
    async def test_complex_classification(self):
        ai_client = MockAIClient(
            '{"complexity": "complex", "lead_agent": "ChatAgent", "lead_capability": "chat"}'
        )
        chat = SimpleAgent("ChatAgent", {"chat"})
        orchestrator, network = await setup_orchestrator([chat], ai_client=ai_client)

        try:
            result = await orchestrator._classify_complexity(
                "Check weather and set lights", {"ChatAgent": ["chat"]}
            )
            assert result["complexity"] == "complex"
        finally:
            await network.stop()

    @pytest.mark.asyncio
    async def test_parse_failure_returns_simple(self):
        ai_client = MockAIClient("This is not JSON at all")
        chat = SimpleAgent("ChatAgent", {"chat"})
        orchestrator, network = await setup_orchestrator([chat], ai_client=ai_client)

        try:
            result = await orchestrator._classify_complexity(
                "test input", {"ChatAgent": ["chat"]}
            )
            assert result["complexity"] == "simple"
        finally:
            await network.stop()

    @pytest.mark.asyncio
    async def test_missing_complexity_field_returns_simple(self):
        """Response with no 'complexity' field should fall back to simple."""
        ai_client = MockAIClient('{"lead_agent": "ChatAgent"}')
        chat = SimpleAgent("ChatAgent", {"chat"})
        orchestrator, network = await setup_orchestrator([chat], ai_client=ai_client)

        try:
            result = await orchestrator._classify_complexity(
                "test", {"ChatAgent": ["chat"]}
            )
            assert result["complexity"] == "simple"
        finally:
            await network.stop()

    @pytest.mark.asyncio
    async def test_non_string_complexity_returns_simple(self):
        """Non-string complexity value should fall back to simple."""
        ai_client = MockAIClient('{"complexity": 42, "lead_agent": "ChatAgent"}')
        chat = SimpleAgent("ChatAgent", {"chat"})
        orchestrator, network = await setup_orchestrator([chat], ai_client=ai_client)

        try:
            result = await orchestrator._classify_complexity(
                "test", {"ChatAgent": ["chat"]}
            )
            assert result["complexity"] == "simple"
        finally:
            await network.stop()

    @pytest.mark.asyncio
    async def test_complex_with_non_string_lead_agent_returns_simple(self):
        """Complex response with non-string lead_agent should fall back to simple."""
        ai_client = MockAIClient(
            '{"complexity": "complex", "lead_agent": 123, "lead_capability": "chat"}'
        )
        chat = SimpleAgent("ChatAgent", {"chat"})
        orchestrator, network = await setup_orchestrator([chat], ai_client=ai_client)

        try:
            result = await orchestrator._classify_complexity(
                "test", {"ChatAgent": ["chat"]}
            )
            assert result["complexity"] == "simple"
        finally:
            await network.stop()

    @pytest.mark.asyncio
    async def test_complex_with_missing_lead_capability_returns_simple(self):
        """Complex response with missing lead_capability should fall back to simple."""
        ai_client = MockAIClient(
            '{"complexity": "complex", "lead_agent": "ChatAgent"}'
        )
        chat = SimpleAgent("ChatAgent", {"chat"})
        orchestrator, network = await setup_orchestrator([chat], ai_client=ai_client)

        try:
            result = await orchestrator._classify_complexity(
                "test", {"ChatAgent": ["chat"]}
            )
            assert result["complexity"] == "simple"
        finally:
            await network.stop()

    @pytest.mark.asyncio
    async def test_strips_markdown_fences(self):
        ai_client = MockAIClient(
            '```json\n{"complexity": "complex", "lead_agent": "ChatAgent", "lead_capability": "chat"}\n```'
        )
        chat = SimpleAgent("ChatAgent", {"chat"})
        orchestrator, network = await setup_orchestrator([chat], ai_client=ai_client)

        try:
            result = await orchestrator._classify_complexity(
                "test input", {"ChatAgent": ["chat"]}
            )
            assert result["complexity"] == "complex"
        finally:
            await network.stop()


class TestCoordinateRequest:
    """Tests for _coordinate_request."""

    @pytest.mark.asyncio
    async def test_returns_none_when_no_ai_client(self):
        chat = SimpleAgent("ChatAgent", {"chat"})
        orchestrator, network = await setup_orchestrator(
            [chat], ai_client=None
        )

        try:
            result = await orchestrator._coordinate_request(
                "test input",
                RequestMetadata(user_id=1),
                None,
                RequestTimer().start(),
                None,
            )
            assert result is None
        finally:
            await network.stop()

    @pytest.mark.asyncio
    async def test_returns_none_when_coordinator_disabled(self):
        ai_client = MockAIClient()
        chat = SimpleAgent("ChatAgent", {"chat"})
        orchestrator, network = await setup_orchestrator(
            [chat], ai_client=ai_client, enable_coordinator=False
        )

        try:
            result = await orchestrator._coordinate_request(
                "test input",
                RequestMetadata(user_id=1),
                None,
                RequestTimer().start(),
                None,
            )
            assert result is None
        finally:
            await network.stop()

    @pytest.mark.asyncio
    async def test_simple_returns_none(self):
        """Simple classification should return None (fall through to NLU)."""
        ai_client = MockAIClient(
            '{"complexity": "simple", "lead_agent": "ChatAgent", "lead_capability": "chat"}'
        )
        chat = SimpleAgent("ChatAgent", {"chat"})
        orchestrator, network = await setup_orchestrator(
            [chat], ai_client=ai_client
        )

        try:
            result = await orchestrator._coordinate_request(
                "hello",
                RequestMetadata(user_id=1),
                None,
                RequestTimer().start(),
                None,
            )
            assert result is None
        finally:
            await network.stop()

    @pytest.mark.asyncio
    async def test_complex_dispatches_to_lead(self):
        """Complex classification should dispatch to the lead agent."""
        ai_client = MockAIClient(
            '{"complexity": "complex", "lead_agent": "ChatAgent", "lead_capability": "chat"}'
        )
        chat = SimpleAgent(
            "ChatAgent",
            {"chat"},
            {"response": "I handled the complex request", "success": True},
        )
        orchestrator, network = await setup_orchestrator(
            [chat], ai_client=ai_client
        )

        try:
            result = await orchestrator._coordinate_request(
                "Check weather and set lights",
                RequestMetadata(user_id=1),
                None,
                RequestTimer().start(),
                None,
            )
            assert result is not None
            assert result["coordinator"] is True
            assert result["lead_agent"] == "ChatAgent"
            assert "response" in result
        finally:
            await network.stop()

    @pytest.mark.asyncio
    async def test_unknown_lead_agent_returns_none(self):
        """If coordinator picks an agent that doesn't exist, fall through."""
        ai_client = MockAIClient(
            '{"complexity": "complex", "lead_agent": "NonexistentAgent", "lead_capability": "foo"}'
        )
        chat = SimpleAgent("ChatAgent", {"chat"})
        orchestrator, network = await setup_orchestrator(
            [chat], ai_client=ai_client
        )

        try:
            result = await orchestrator._coordinate_request(
                "do something complex",
                RequestMetadata(user_id=1),
                None,
                RequestTimer().start(),
                None,
            )
            assert result is None
        finally:
            await network.stop()

    @pytest.mark.asyncio
    async def test_mismatched_agent_capability_returns_none(self):
        """If coordinator picks agent that doesn't provide lead_capability, fall through."""
        ai_client = MockAIClient(
            '{"complexity": "complex", "lead_agent": "ChatAgent", "lead_capability": "get_weather"}'
        )
        chat = SimpleAgent("ChatAgent", {"chat"})  # ChatAgent doesn't have get_weather
        orchestrator, network = await setup_orchestrator(
            [chat], ai_client=ai_client
        )

        try:
            result = await orchestrator._coordinate_request(
                "do something complex",
                RequestMetadata(user_id=1),
                None,
                RequestTimer().start(),
                None,
            )
            assert result is None
        finally:
            await network.stop()

    @pytest.mark.asyncio
    async def test_fallback_on_llm_exception(self):
        """If the AI client raises, coordinator should return None gracefully."""

        class FailingAIClient:
            async def weak_chat(self, messages, tools=None):
                raise RuntimeError("LLM is down")

            async def strong_chat(self, messages, tools=None):
                raise RuntimeError("LLM is down")

        chat = SimpleAgent("ChatAgent", {"chat"})
        orchestrator, network = await setup_orchestrator(
            [chat], ai_client=FailingAIClient()
        )

        try:
            result = await orchestrator._coordinate_request(
                "do something",
                RequestMetadata(user_id=1),
                None,
                RequestTimer().start(),
                None,
            )
            assert result is None
        finally:
            await network.stop()


class TestDispatchMission:
    """Tests for _dispatch_mission."""

    @pytest.mark.asyncio
    async def test_dispatches_and_returns_result(self):
        chat = SimpleAgent(
            "ChatAgent",
            {"chat"},
            {"response": "Mission accomplished", "success": True},
        )
        ai_client = MockAIClient()
        orchestrator, network = await setup_orchestrator(
            [chat], ai_client=ai_client
        )

        try:
            brief = MissionBrief(
                user_input="test mission",
                complexity=MissionComplexity.COMPLEX,
                lead_agent="ChatAgent",
                lead_capability="chat",
                budget=MissionBrief.from_dict({}).budget,
                context=MissionBrief.from_dict({}).context,
                available_capabilities={"ChatAgent": ["chat"]},
            )
            brief.budget.deadline = time.time() + 10

            result = await orchestrator._dispatch_mission(
                brief,
                RequestMetadata(user_id=1),
                RequestTimer().start(),
                None,
            )
            assert result is not None
            assert "Mission accomplished" in result["response"]
            assert result["coordinator"] is True
        finally:
            await network.stop()

    @pytest.mark.asyncio
    async def test_timeout_returns_none(self):
        """If the lead agent doesn't respond in time, return None."""

        class SlowAgent(NetworkAgent):
            @property
            def capabilities(self):
                return {"chat"}

            async def _handle_capability_request(self, message):
                await asyncio.sleep(10)  # Never responds in time

            async def _handle_capability_response(self, message):
                pass

        slow = SlowAgent("ChatAgent")
        ai_client = MockAIClient()
        orchestrator, network = await setup_orchestrator(
            [slow], ai_client=ai_client
        )

        try:
            brief = MissionBrief(
                user_input="test mission",
                complexity=MissionComplexity.COMPLEX,
                lead_agent="ChatAgent",
                lead_capability="chat",
                budget=MissionBrief.from_dict({}).budget,
                context=MissionBrief.from_dict({}).context,
                available_capabilities={"ChatAgent": ["chat"]},
            )
            # Set a very short deadline
            brief.budget.deadline = time.time() + 0.2

            result = await orchestrator._dispatch_mission(
                brief,
                RequestMetadata(user_id=1),
                RequestTimer().start(),
                None,
            )
            assert result is None
        finally:
            await network.stop()
