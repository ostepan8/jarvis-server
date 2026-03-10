"""Tests for ChatAgent lead agent behavior (Phase 4).

Tests verify that ChatAgent correctly detects mission_brief in capability
requests and delegates to _execute_as_lead, while preserving normal
chat behavior when no mission_brief is present.
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Set
from unittest.mock import MagicMock

import pytest

from jarvis.agents.agent_network import AgentNetwork
from jarvis.agents.base import NetworkAgent
from jarvis.agents.chat_agent.agent import ChatAgent
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
    """AI client returning configurable sequences of responses."""

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
    available_capabilities: Dict[str, List[str]] = None,
) -> MissionBrief:
    return MissionBrief(
        user_input="Check weather and set lights",
        complexity=MissionComplexity.COMPLEX,
        lead_agent="ChatAgent",
        lead_capability="chat",
        budget=MissionBudget(
            max_depth=3,
            remaining_depth=3,
            deadline=time.time() + 60,
            max_recruitments=5,
            remaining_recruitments=5,
        ),
        context=MissionContext(
            user_input="Check weather and set lights",
            recruitment_chain=["ChatAgent"],
        ),
        available_capabilities=available_capabilities or {
            "SearchAgent": ["search"],
            "LightingAgent": ["set_color"],
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

class TestChatAgentLeadDetection:
    """Tests that ChatAgent correctly detects mission_brief and routes."""

    @pytest.mark.asyncio
    async def test_normal_chat_without_mission_brief(self):
        """Without mission_brief, ChatAgent should use normal _process_chat."""
        ai_client = MockAIClient([("Hello! How can I help?", None)])
        chat = ChatAgent(ai_client)
        network = await setup_network(chat)

        try:
            msg = Message(
                from_agent="JarvisSystem",
                to_agent="ChatAgent",
                message_type="capability_request",
                content={
                    "capability": "chat",
                    "data": {
                        "prompt": "Hello",
                        "context": {"conversation_history": []},
                    },
                },
                request_id="req_1",
            )
            await chat.receive_message(msg)
            # Give time for async processing
            import asyncio
            await asyncio.sleep(0.2)

            # Verify response was sent (check via network future)
            # Since we can't easily intercept the response, we verify
            # the AI client was called (which means _process_chat ran)
            assert ai_client._call_count == 1
        finally:
            await network.stop()

    @pytest.mark.asyncio
    async def test_lead_mode_with_mission_brief(self):
        """With mission_brief in data, ChatAgent should use _execute_as_lead."""
        recruit_call = make_tool_call(
            "recruit_agent",
            {"capability": "search", "prompt": "What's the weather?"},
            "call_recruit",
        )
        ai_client = MockAIClient([
            ("", [recruit_call]),
            ("The weather is sunny and 72°F!", None),
        ])
        chat = ChatAgent(ai_client)
        weather = ProviderAgent(
            "SearchAgent", {"search"}, {"response": "72°F and sunny"}
        )
        network = await setup_network(chat, weather)

        try:
            brief = make_brief()
            msg = Message(
                from_agent="JarvisSystem",
                to_agent="ChatAgent",
                message_type="capability_request",
                content={
                    "capability": "chat",
                    "data": {
                        "prompt": "Check weather and set lights",
                        "mission_brief": brief.to_dict(),
                        "context": {"conversation_history": []},
                    },
                },
                request_id="req_lead",
            )
            await chat.receive_message(msg)

            import asyncio
            await asyncio.sleep(0.5)

            # AI client should have been called at least twice
            # (once for recruit tool call, once for final response)
            assert ai_client._call_count >= 2
        finally:
            await network.stop()


class TestChatAgentLeadPrompt:
    """Tests for ChatAgent's custom lead system prompt."""

    def test_includes_conversational_personality(self):
        ai_client = MockAIClient()
        chat = ChatAgent(ai_client)
        brief = make_brief()
        prompt = chat._build_lead_system_prompt(brief)
        assert "friendly" in prompt.lower() or "conversational" in prompt.lower()

    def test_includes_user_request(self):
        ai_client = MockAIClient()
        chat = ChatAgent(ai_client)
        brief = make_brief()
        prompt = chat._build_lead_system_prompt(brief)
        assert brief.user_input in prompt

    def test_includes_available_capabilities(self):
        ai_client = MockAIClient()
        chat = ChatAgent(ai_client)
        brief = make_brief()
        prompt = chat._build_lead_system_prompt(brief)
        assert "SearchAgent" in prompt
        assert "search" in prompt


class TestChatAgentCollaborationMixin:
    """Verify ChatAgent has CollaborationMixin methods."""

    def test_has_recruit_method(self):
        ai_client = MockAIClient()
        chat = ChatAgent(ai_client)
        assert hasattr(chat, "recruit")

    def test_has_execute_as_lead_method(self):
        ai_client = MockAIClient()
        chat = ChatAgent(ai_client)
        assert hasattr(chat, "_execute_as_lead")

    def test_has_get_recruitable_capabilities(self):
        ai_client = MockAIClient()
        chat = ChatAgent(ai_client)
        assert hasattr(chat, "get_recruitable_capabilities")
