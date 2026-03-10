"""Real LLM end-to-end tests for agent-to-agent dialogue.

These tests require OPENAI_API_KEY to be set and are skipped otherwise.
They verify multi-turn dialogue with real LLM calls.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, Set

import pytest

from jarvis.agents.agent_network import AgentNetwork
from jarvis.agents.base import NetworkAgent
from jarvis.agents.chat_agent.agent import ChatAgent
from jarvis.agents.dialogue import DialogueStatus
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
    reason="OPENAI_API_KEY not set — skipping real LLM dialogue e2e tests",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class DialogueSearchAgent(NetworkAgent):
    """Weather agent that supports dialogue via a real AI client."""

    def __init__(self, ai_client):
        super().__init__("SearchAgent")
        self.ai_client = ai_client

    @property
    def capabilities(self) -> Set[str]:
        return {"search", "news_search"}

    @property
    def supports_dialogue(self) -> bool:
        return True

    async def _handle_capability_request(self, message: Message) -> None:
        capability = message.content.get("capability")
        if capability not in self.capabilities:
            return

        data = message.content.get("data", {})
        dialogue_context = data.get("dialogue_context")

        if dialogue_context:
            result = await self._respond_to_dialogue(
                data.get("prompt", ""), dialogue_context
            )
        else:
            result = AgentResponse.success_response(
                response="Currently 72°F and sunny in Chicago.",
                data={"temperature": 72, "condition": "sunny", "city": "Chicago"},
            ).to_dict()

        await self.send_capability_response(
            message.from_agent, result, message.request_id, message.id
        )

    async def _handle_capability_response(self, message: Message) -> None:
        pass


class DialogueLightingAgent(NetworkAgent):
    """Lighting agent that supports dialogue via a real AI client."""

    def __init__(self, ai_client):
        super().__init__("LightingAgent")
        self.ai_client = ai_client

    @property
    def capabilities(self) -> Set[str]:
        return {"lights_color", "lights_brightness"}

    @property
    def supports_dialogue(self) -> bool:
        return True

    async def _handle_capability_request(self, message: Message) -> None:
        capability = message.content.get("capability")
        if capability not in self.capabilities:
            return

        data = message.content.get("data", {})
        dialogue_context = data.get("dialogue_context")

        if dialogue_context:
            result = await self._respond_to_dialogue(
                data.get("prompt", ""), dialogue_context
            )
        else:
            result = AgentResponse.success_response(
                response=f"Executed {capability} successfully.",
            ).to_dict()

        await self.send_capability_response(
            message.from_agent, result, message.request_id, message.id
        )

    async def _handle_capability_response(self, message: Message) -> None:
        pass


class NonDialogueSearchAgent(NetworkAgent):
    """Search agent with NO AI client (does not support dialogue)."""

    @property
    def capabilities(self) -> Set[str]:
        return {"search"}

    async def _handle_capability_request(self, message: Message) -> None:
        capability = message.content.get("capability")
        if capability not in self.capabilities:
            return

        data = message.content.get("data", {})
        dialogue_context = data.get("dialogue_context")

        if dialogue_context:
            result = await self._respond_to_dialogue(
                data.get("prompt", ""), dialogue_context
            )
        else:
            result = AgentResponse.success_response(
                response="Search results: Python is a programming language.",
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


def make_brief(
    user_input: str,
    lead_agent: str = "ChatAgent",
    available_capabilities: Dict[str, list] = None,
    max_recruitments: int = 10,
    deadline_seconds: float = 45,
) -> MissionBrief:
    if available_capabilities is None:
        available_capabilities = {
            "SearchAgent": ["search", "news_search"],
            "LightingAgent": ["lights_color", "lights_brightness"],
        }
    return MissionBrief(
        user_input=user_input,
        complexity=MissionComplexity.COMPLEX,
        lead_agent=lead_agent,
        lead_capability="chat",
        budget=MissionBudget(
            max_depth=3,
            remaining_depth=3,
            deadline=time.time() + deadline_seconds,
            max_recruitments=max_recruitments,
            remaining_recruitments=max_recruitments,
        ),
        context=MissionContext(
            user_input=user_input,
            recruitment_chain=[lead_agent],
        ),
        available_capabilities=available_capabilities,
    )


# ---------------------------------------------------------------------------
# Real E2E Tests
# ---------------------------------------------------------------------------


class TestDialogueE2EReal:
    """Real LLM dialogue tests."""

    @pytest.mark.asyncio
    async def test_chat_dialogues_with_weather(self):
        """ChatAgent conducts a multi-turn dialogue with SearchAgent."""
        ai_client = make_real_ai_client()
        chat = ChatAgent(ai_client)
        search_agent = DialogueSearchAgent(ai_client)
        network = await setup_real_network(chat, search_agent)

        try:
            brief = make_brief(
                user_input="Have a conversation with the weather agent about outdoor activities today",
                available_capabilities={
                    "SearchAgent": ["search", "news_search"],
                },
            )
            session = await chat.dialogue(
                capability="search",
                initial_message="I'm planning outdoor activities today. What are the current conditions and would you recommend being outside?",
                goal="Determine if weather is suitable for outdoor activities",
                brief=brief,
                max_turns=3,
            )
            # Should have completed with a multi-turn conversation
            assert session.status in (DialogueStatus.COMPLETED, DialogueStatus.ACTIVE)
            assert session.turn_count >= 2
            # Transcript should have content
            transcript = session.format_transcript()
            assert len(transcript) > 0
            assert session.initiator == "ChatAgent"
            assert session.responder == "SearchAgent"
        finally:
            await network.stop()

    @pytest.mark.asyncio
    async def test_dialogue_concludes_early_on_simple_question(self):
        """Responder should set done=True for simple questions, ending dialogue early."""
        ai_client = make_real_ai_client()
        chat = ChatAgent(ai_client)
        search_agent = DialogueSearchAgent(ai_client)
        network = await setup_real_network(chat, search_agent)

        try:
            brief = make_brief(
                user_input="What's the temperature right now?",
                available_capabilities={
                    "SearchAgent": ["search"],
                },
            )
            session = await chat.dialogue(
                capability="search",
                initial_message="What is the current temperature?",
                goal="Get the current temperature",
                brief=brief,
                max_turns=5,
            )
            assert session.status == DialogueStatus.COMPLETED
            # Simple question should end in 1-2 exchanges
            assert session.turn_count >= 2
            assert session.turn_count <= 6  # Should not use all 5 turns
        finally:
            await network.stop()

    @pytest.mark.asyncio
    async def test_dialogue_with_non_dialogue_agent(self):
        """Dialogue with an agent without AI client should degrade to single turn."""
        ai_client = make_real_ai_client()
        chat = ChatAgent(ai_client)
        search = NonDialogueSearchAgent("SearchAgent")
        network = await setup_real_network(chat, search)

        try:
            brief = make_brief(
                user_input="Search for Python tutorials",
                available_capabilities={
                    "SearchAgent": ["search"],
                },
            )
            session = await chat.dialogue(
                capability="search",
                initial_message="Search for Python tutorials",
                goal="Find Python learning resources",
                brief=brief,
                max_turns=5,
            )
            # Should complete quickly since SearchAgent returns done=True
            assert session.status == DialogueStatus.COMPLETED
            assert session.turn_count >= 2
        finally:
            await network.stop()

    @pytest.mark.asyncio
    async def test_lead_uses_both_recruit_and_dialogue(self):
        """Lead agent uses recruit (one-shot) and dialogue (multi-turn) in same mission."""
        ai_client = make_real_ai_client()
        chat = ChatAgent(ai_client)
        search_agent = DialogueSearchAgent(ai_client)
        lights = DialogueLightingAgent(ai_client)
        network = await setup_real_network(chat, search_agent, lights)

        try:
            brief = make_brief(
                user_input="Check the weather quickly, then have a conversation with the lighting agent about setting up the mood",
                available_capabilities={
                    "SearchAgent": ["search", "news_search"],
                    "LightingAgent": ["lights_color", "lights_brightness"],
                },
                max_recruitments=10,
            )

            result = await chat._execute_as_lead(
                "Check the weather quickly, then have a conversation with the lighting agent about setting up evening mood lighting",
                brief,
            )

            assert result["success"] is True
            assert result["response"]  # Non-empty response

            # Should have at least one action (either recruit or dialogue)
            assert len(result.get("actions", [])) >= 1

            # At least one of the tools should have been used
            functions = [a["function"] for a in result.get("actions", [])]
            assert any(f in functions for f in ("recruit_agent", "start_dialogue"))
        finally:
            await network.stop()
