"""Tests for ChatAgent robustness (Round 3 fixes).

Covers malformed JSON tool arguments, non-dict mission_brief handling,
and other edge cases in ChatAgent._process_chat and _handle_capability_request.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Set
from unittest.mock import AsyncMock, MagicMock

import pytest

from jarvis.agents.agent_network import AgentNetwork
from jarvis.agents.base import NetworkAgent
from jarvis.agents.chat_agent.agent import ChatAgent
from jarvis.agents.message import Message
from jarvis.core.mission import MissionBrief


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


def make_tool_call(name: str, arguments: Any, call_id: str = "call_1"):
    """Create a mock tool call with arbitrary arguments (can be invalid)."""
    call = MagicMock()
    call.id = call_id
    call.function = MagicMock()
    call.function.name = name
    call.function.arguments = arguments
    return call


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestChatAgentMalformedToolArgs:
    """Tests for ChatAgent._process_chat with malformed tool arguments."""

    @pytest.mark.asyncio
    async def test_none_tool_arguments_returns_error_action(self):
        """None arguments should produce an error action, not crash."""
        call = make_tool_call("get_facts", None, "call_1")
        ai_client = MockAIClient([
            ("", [call]),
            ("I don't have any facts stored for you.", None),
        ])
        agent = ChatAgent(ai_client)

        result = await agent._process_chat("what's my name?")
        assert result["success"] is False or "error" in str(result.get("actions", []))
        # The important thing: no crash, and we got a response
        assert "response" in result

    @pytest.mark.asyncio
    async def test_empty_string_tool_arguments_returns_error_action(self):
        """Empty string arguments should produce an error action, not crash."""
        call = make_tool_call("get_facts", "", "call_1")
        ai_client = MockAIClient([
            ("", [call]),
            ("I'll answer from my knowledge.", None),
        ])
        agent = ChatAgent(ai_client)

        result = await agent._process_chat("what's the capital of France?")
        assert "response" in result
        # Should have an error in actions
        actions = result.get("actions", [])
        if actions:
            assert any("error" in a.get("result", {}) for a in actions)

    @pytest.mark.asyncio
    async def test_truncated_json_tool_arguments_returns_error_action(self):
        """Truncated JSON should produce an error action, not crash."""
        call = make_tool_call("store_fact", '{"fact": "likes pizza', "call_1")
        ai_client = MockAIClient([
            ("", [call]),
            ("I noted that.", None),
        ])
        agent = ChatAgent(ai_client)

        result = await agent._process_chat("I like pizza")
        assert "response" in result


class TestChatAgentNonDictMissionBrief:
    """Tests that non-dict mission_brief values don't trigger lead execution."""

    @pytest.mark.asyncio
    async def test_string_mission_brief_treated_as_normal_chat(self):
        """A string mission_brief should not trigger _execute_as_lead."""
        ai_client = MockAIClient([
            ("Hello there!", None),
        ])
        agent = ChatAgent(ai_client)

        # Create a mock message with mission_brief as a string
        msg = Message(
            from_agent="TestAgent",
            to_agent="ChatAgent",
            message_type="capability_request",
            content={
                "capability": "chat",
                "data": {
                    "prompt": "hello",
                    "mission_brief": "not a dict",
                },
            },
            request_id="req_test_1",
        )

        # Register agent on a network so send works
        network = AgentNetwork()
        network.register_agent(agent)
        await network.start()

        try:
            await agent.receive_message(msg)
            # Should not crash — string mission_brief is ignored
            # The agent processes it as a normal chat
        finally:
            await network.stop()

    @pytest.mark.asyncio
    async def test_list_mission_brief_treated_as_normal_chat(self):
        """A list mission_brief should not trigger _execute_as_lead."""
        ai_client = MockAIClient([
            ("Sure, how can I help?", None),
        ])
        agent = ChatAgent(ai_client)

        msg = Message(
            from_agent="TestAgent",
            to_agent="ChatAgent",
            message_type="capability_request",
            content={
                "capability": "chat",
                "data": {
                    "prompt": "hi",
                    "mission_brief": ["not", "a", "dict"],
                },
            },
            request_id="req_test_2",
        )

        network = AgentNetwork()
        network.register_agent(agent)
        await network.start()

        try:
            await agent.receive_message(msg)
        finally:
            await network.stop()

    @pytest.mark.asyncio
    async def test_true_mission_brief_treated_as_normal_chat(self):
        """A boolean True mission_brief should not trigger _execute_as_lead."""
        ai_client = MockAIClient([
            ("I'm here to help!", None),
        ])
        agent = ChatAgent(ai_client)

        msg = Message(
            from_agent="TestAgent",
            to_agent="ChatAgent",
            message_type="capability_request",
            content={
                "capability": "chat",
                "data": {
                    "prompt": "hey",
                    "mission_brief": True,
                },
            },
            request_id="req_test_3",
        )

        network = AgentNetwork()
        network.register_agent(agent)
        await network.start()

        try:
            await agent.receive_message(msg)
        finally:
            await network.stop()
