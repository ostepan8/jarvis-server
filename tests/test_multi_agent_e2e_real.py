"""Real LLM end-to-end tests for multi-agent coordination (Phase 5).

These tests require OPENAI_API_KEY to be set and are skipped otherwise.
They verify the full coordinator + lead agent pattern with real LLM calls.
"""

from __future__ import annotations

import asyncio
import os
import time
from typing import Any, Dict, Set

import pytest

from jarvis.agents.agent_network import AgentNetwork
from jarvis.agents.base import NetworkAgent
from jarvis.agents.chat_agent.agent import ChatAgent
from jarvis.agents.message import Message
from jarvis.agents.response import AgentResponse
from jarvis.core.mission import (
    MissionBrief,
    MissionBudget,
    MissionComplexity,
    MissionContext,
)

# Skip all tests in this module if no API key
pytestmark = pytest.mark.skipif(
    not os.environ.get("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY not set - skipping real LLM e2e tests",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class MockWeatherAgent(NetworkAgent):
    """Mock weather agent that returns realistic weather data."""

    @property
    def capabilities(self) -> Set[str]:
        return {"get_weather", "get_forecast"}

    async def _handle_capability_request(self, message: Message) -> None:
        capability = message.content.get("capability")
        if capability in self.capabilities:
            result = AgentResponse.success_response(
                response="Currently 72°F and sunny in San Francisco.",
                data={"temperature": 72, "condition": "sunny", "city": "San Francisco"},
            ).to_dict()
            await self.send_capability_response(
                message.from_agent, result, message.request_id, message.id
            )

    async def _handle_capability_response(self, message: Message) -> None:
        pass


class MockLightingAgent(NetworkAgent):
    """Mock lighting agent that returns realistic light control results."""

    @property
    def capabilities(self) -> Set[str]:
        return {"set_color", "set_brightness", "toggle_lights"}

    async def _handle_capability_request(self, message: Message) -> None:
        capability = message.content.get("capability")
        if capability in self.capabilities:
            result = AgentResponse.success_response(
                response=f"Successfully executed {capability}.",
                data={"action": capability, "success": True},
            ).to_dict()
            await self.send_capability_response(
                message.from_agent, result, message.request_id, message.id
            )

    async def _handle_capability_response(self, message: Message) -> None:
        pass


def make_real_ai_client():
    """Create a real OpenAI client."""
    from jarvis.ai_clients import AIClientFactory
    return AIClientFactory.create(
        "openai",
        api_key=os.environ.get("OPENAI_API_KEY"),
        strong_model="gpt-4o-mini",
        weak_model="gpt-4o-mini",
    )


async def setup_real_network(*agents: NetworkAgent) -> AgentNetwork:
    network = AgentNetwork()
    for agent in agents:
        network.register_agent(agent)
    await network.start()
    return network


# ---------------------------------------------------------------------------
# Real E2E Tests
# ---------------------------------------------------------------------------

class TestRealLLMLeadExecution:
    """Real LLM tests for lead agent execution."""

    @pytest.mark.asyncio
    async def test_chat_agent_recruits_weather(self):
        """ChatAgent should recruit WeatherAgent for weather queries in complex request."""
        ai_client = make_real_ai_client()
        chat = ChatAgent(ai_client)
        weather = MockWeatherAgent("WeatherAgent")
        network = await setup_real_network(chat, weather)

        try:
            brief = MissionBrief(
                user_input="What's the weather like and give me a fun fact",
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
                    user_input="What's the weather like and give me a fun fact",
                    recruitment_chain=["ChatAgent"],
                ),
                available_capabilities={
                    "WeatherAgent": ["get_weather", "get_forecast"],
                },
            )

            result = await chat._execute_as_lead(
                "What's the weather like and give me a fun fact", brief
            )

            assert result["success"] is True
            assert result["response"]  # Should have a non-empty response
            assert result["metadata"]["lead_agent"] == "ChatAgent"

            # Verify the agent recruited WeatherAgent
            recruit_actions = [
                a for a in result.get("actions", [])
                if a.get("function") == "recruit_agent"
            ]
            assert len(recruit_actions) >= 1
            assert recruit_actions[0]["arguments"]["capability"] == "get_weather"
        finally:
            await network.stop()

    @pytest.mark.asyncio
    async def test_simple_request_no_recruitment(self):
        """Simple questions should not trigger recruitment."""
        ai_client = make_real_ai_client()
        chat = ChatAgent(ai_client)
        weather = MockWeatherAgent("WeatherAgent")
        network = await setup_real_network(chat, weather)

        try:
            brief = MissionBrief(
                user_input="What is 2+2?",
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
                    user_input="What is 2+2?",
                    recruitment_chain=["ChatAgent"],
                ),
                available_capabilities={
                    "WeatherAgent": ["get_weather"],
                },
            )

            result = await chat._execute_as_lead("What is 2+2?", brief)

            assert result["success"] is True
            assert result["response"]
            # Should NOT have recruited any agent for simple math
            recruit_actions = [
                a for a in result.get("actions", [])
                if a.get("function") == "recruit_agent"
            ]
            assert len(recruit_actions) == 0
        finally:
            await network.stop()
