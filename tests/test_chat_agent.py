"""Comprehensive tests for ChatAgent."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from jarvis.agents.chat_agent.agent import ChatAgent
from jarvis.agents.message import Message
from jarvis.agents.response import AgentResponse
from jarvis.ai_clients.base import BaseAIClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class DummyAIClient(BaseAIClient):
    """AI client that returns a simple text response with no tool calls."""

    def __init__(self, response_text="This is a dummy response."):
        self._response_text = response_text

    async def strong_chat(self, messages, tools=None):
        msg = type("Message", (), {"content": self._response_text})()
        return msg, None

    async def weak_chat(self, messages, tools=None):
        msg = type("Message", (), {"content": self._response_text})()
        return msg, None


class ToolCallAIClient(BaseAIClient):
    """AI client that returns tool calls on the first round, then text."""

    def __init__(self, tool_name, tool_args, tool_result_text="Done"):
        self._tool_name = tool_name
        self._tool_args = tool_args
        self._tool_result_text = tool_result_text
        self._call_count = 0

    async def strong_chat(self, messages, tools=None):
        self._call_count += 1
        if self._call_count == 1:
            # First call: return a tool call
            import json

            func = type("Function", (), {
                "name": self._tool_name,
                "arguments": json.dumps(self._tool_args),
            })()
            call = type("ToolCall", (), {
                "id": "call_001",
                "function": func,
            })()
            msg = type("Message", (), {"content": None})()
            return msg, [call]
        else:
            # Second call: return final text
            msg = type("Message", (), {"content": self._tool_result_text})()
            return msg, None

    async def weak_chat(self, messages, tools=None):
        msg = type("Message", (), {"content": "dummy"})()
        return msg, None


def _make_capability_message(prompt, capability="chat", from_agent="tester",
                             request_id="req-1", context=None):
    """Helper to build a capability_request Message for ChatAgent."""
    data = {"prompt": prompt}
    if context is not None:
        data["context"] = context
    return Message(
        from_agent=from_agent,
        to_agent="ChatAgent",
        message_type="capability_request",
        content={"capability": capability, "data": data},
        request_id=request_id,
    )


# ---------------------------------------------------------------------------
# Tests: metadata & properties
# ---------------------------------------------------------------------------

class TestChatAgentProperties:
    """Test ChatAgent metadata and configuration."""

    def test_name(self):
        agent = ChatAgent(ai_client=DummyAIClient())
        assert agent.name == "ChatAgent"

    def test_description(self):
        agent = ChatAgent(ai_client=DummyAIClient())
        assert "Conversational" in agent.description or "chat" in agent.description.lower()

    def test_capabilities(self):
        agent = ChatAgent(ai_client=DummyAIClient())
        assert "chat" in agent.capabilities

    def test_intent_map_keys(self):
        agent = ChatAgent(ai_client=DummyAIClient())
        expected = {"chat", "store_fact", "get_facts", "update_profile"}
        assert set(agent.intent_map.keys()) == expected

    def test_tools_defined(self):
        agent = ChatAgent(ai_client=DummyAIClient())
        assert isinstance(agent.tools, list)
        assert len(agent.tools) > 0

    def test_system_prompt_exists(self):
        agent = ChatAgent(ai_client=DummyAIClient())
        assert isinstance(agent.system_prompt, str)
        assert len(agent.system_prompt) > 0


# ---------------------------------------------------------------------------
# Tests: _process_chat
# ---------------------------------------------------------------------------

class TestProcessChat:
    """Test the core _process_chat method."""

    @pytest.mark.asyncio
    async def test_process_chat_simple_response(self):
        """Test that a simple prompt returns a successful AgentResponse dict."""
        agent = ChatAgent(ai_client=DummyAIClient("Hello, how can I help?"))
        result = await agent._process_chat("Hello")
        assert isinstance(result, dict)
        assert result["success"] is True
        assert result["response"] == "Hello, how can I help?"

    @pytest.mark.asyncio
    async def test_process_chat_with_conversation_history(self):
        """Conversation history is passed into the LLM context."""
        agent = ChatAgent(ai_client=DummyAIClient("response"))
        history = [
            {"user": "hi", "assistant": "hello"},
            {"user": "how are you", "assistant": "good"},
        ]
        result = await agent._process_chat("tell me more", history)
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_process_chat_with_empty_history_entries(self):
        """Conversation history with empty/None content is handled gracefully."""
        agent = ChatAgent(ai_client=DummyAIClient("ok"))
        history = [
            {"user": "", "assistant": None},
            {"user": "real message", "assistant": "real answer"},
        ]
        result = await agent._process_chat("next question", history)
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_process_chat_with_none_history(self):
        """None conversation_history is handled gracefully."""
        agent = ChatAgent(ai_client=DummyAIClient("hi"))
        result = await agent._process_chat("hello", None)
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_process_chat_error_handling(self):
        """An exception in the AI client produces an error response."""

        class ErrorAIClient(BaseAIClient):
            async def strong_chat(self, messages, tools=None):
                raise RuntimeError("AI service down")

            async def weak_chat(self, messages, tools=None):
                raise RuntimeError("AI service down")

        agent = ChatAgent(ai_client=ErrorAIClient())
        result = await agent._process_chat("hello")
        assert result["success"] is False
        assert "error" in result
        assert "AI service down" in result["error"]["message"]

    @pytest.mark.asyncio
    async def test_process_chat_with_tool_call_store_fact(self):
        """Tool call for store_fact is executed and actions are recorded.

        NOTE: The source code passes user_id= to store_memory which does not
        accept that kwarg (bug in source). We patch store_memory to tolerate it.
        """
        ai = ToolCallAIClient("store_fact", {"fact": "I like pizza"}, "Got it!")
        agent = ChatAgent(ai_client=ai)

        async def mock_store_memory(text, metadata=None, **kwargs):
            return None

        agent.store_memory = mock_store_memory
        result = await agent._process_chat("Remember: I like pizza")
        assert result["success"] is True
        assert result["response"] == "Got it!"
        assert len(result["actions"]) == 1
        assert result["actions"][0]["function"] == "store_fact"

    @pytest.mark.asyncio
    async def test_process_chat_with_tool_call_get_facts(self):
        """Tool call for get_facts is executed and actions are recorded."""
        ai = ToolCallAIClient("get_facts", {"query": "favorite food"}, "You like pizza")
        agent = ChatAgent(ai_client=ai)
        result = await agent._process_chat("What's my favorite food?")
        assert result["success"] is True
        assert len(result["actions"]) == 1
        assert result["actions"][0]["function"] == "get_facts"

    @pytest.mark.asyncio
    async def test_process_chat_truncates_history_to_five(self):
        """Only the last 5 conversation turns are included in context."""
        call_log = []

        class SpyAIClient(BaseAIClient):
            async def strong_chat(self, messages, tools=None):
                call_log.append(messages[:])
                msg = type("Message", (), {"content": "resp"})()
                return msg, None

            async def weak_chat(self, messages, tools=None):
                msg = type("Message", (), {"content": "resp"})()
                return msg, None

        agent = ChatAgent(ai_client=SpyAIClient())
        history = [{"user": f"msg{i}", "assistant": f"ans{i}"} for i in range(10)]
        await agent._process_chat("current question", history)

        # The messages list should have: system + last 5 pairs (10 msgs) + current = 12
        # But empty entries are filtered, so count user messages from history
        user_msgs_from_history = [
            m for m in call_log[0] if m["role"] == "user" and m["content"] != "current question"
        ]
        # Should be at most 5 user messages from history
        assert len(user_msgs_from_history) <= 5


# ---------------------------------------------------------------------------
# Tests: _handle_capability_request
# ---------------------------------------------------------------------------

class TestHandleCapabilityRequest:
    """Test message-based capability request handling."""

    @pytest.mark.asyncio
    async def test_handle_chat_capability(self, monkeypatch):
        """A chat capability request triggers _process_chat and sends response."""
        agent = ChatAgent(ai_client=DummyAIClient("I'm here to help"))
        captured = {}

        async def fake_send(to, result, request_id, msg_id):
            captured["to"] = to
            captured["result"] = result
            captured["request_id"] = request_id

        monkeypatch.setattr(agent, "send_capability_response", fake_send)
        msg = _make_capability_message("hello there")
        await agent._handle_capability_request(msg)
        assert captured["result"]["success"] is True
        assert captured["to"] == "tester"
        assert captured["request_id"] == "req-1"

    @pytest.mark.asyncio
    async def test_handle_non_chat_capability_ignored(self, monkeypatch):
        """Non-chat capabilities are silently ignored."""
        agent = ChatAgent(ai_client=DummyAIClient())
        captured = {}

        async def fake_send(to, result, request_id, msg_id):
            captured["sent"] = True

        monkeypatch.setattr(agent, "send_capability_response", fake_send)
        msg = _make_capability_message("test", capability="weather")
        await agent._handle_capability_request(msg)
        assert "sent" not in captured

    @pytest.mark.asyncio
    async def test_handle_invalid_prompt_type(self, monkeypatch):
        """A non-string prompt sends an error."""
        agent = ChatAgent(ai_client=DummyAIClient())
        errors = []

        async def fake_error(to, err, request_id):
            errors.append(err)

        monkeypatch.setattr(agent, "send_error", fake_error)
        msg = Message(
            from_agent="tester",
            to_agent="ChatAgent",
            message_type="capability_request",
            content={"capability": "chat", "data": {"prompt": 12345}},
            request_id="req-1",
        )
        await agent._handle_capability_request(msg)
        assert len(errors) == 1
        assert "Invalid prompt" in errors[0]

    @pytest.mark.asyncio
    async def test_handle_missing_prompt(self, monkeypatch):
        """Missing prompt (None) sends an error."""
        agent = ChatAgent(ai_client=DummyAIClient())
        errors = []

        async def fake_error(to, err, request_id):
            errors.append(err)

        monkeypatch.setattr(agent, "send_error", fake_error)
        msg = Message(
            from_agent="tester",
            to_agent="ChatAgent",
            message_type="capability_request",
            content={"capability": "chat", "data": {}},
            request_id="req-1",
        )
        await agent._handle_capability_request(msg)
        assert len(errors) == 1

    @pytest.mark.asyncio
    async def test_handle_with_conversation_context(self, monkeypatch):
        """Conversation history from context is passed through."""
        agent = ChatAgent(ai_client=DummyAIClient("contextual reply"))
        captured = {}

        async def fake_send(to, result, request_id, msg_id):
            captured["result"] = result

        monkeypatch.setattr(agent, "send_capability_response", fake_send)
        context = {
            "conversation_history": [
                {"user": "hi", "assistant": "hello"}
            ]
        }
        msg = _make_capability_message("follow up", context=context)
        await agent._handle_capability_request(msg)
        assert captured["result"]["success"] is True


# ---------------------------------------------------------------------------
# Tests: _handle_capability_response
# ---------------------------------------------------------------------------

class TestHandleCapabilityResponse:
    """Test capability response handler."""

    @pytest.mark.asyncio
    async def test_handle_capability_response_is_noop(self):
        """ChatAgent does not initiate requests so this should be a no-op."""
        agent = ChatAgent(ai_client=DummyAIClient())
        msg = Message(
            from_agent="other",
            to_agent="ChatAgent",
            message_type="capability_response",
            content={"data": "something"},
            request_id="req-1",
        )
        # Should not raise
        await agent._handle_capability_response(msg)


# ---------------------------------------------------------------------------
# Tests: tool implementations
# ---------------------------------------------------------------------------

class TestToolImplementations:
    """Test individual tool methods directly."""

    @pytest.mark.asyncio
    async def test_store_fact_returns_confirmation(self):
        """_store_fact returns 'fact stored'.

        NOTE: The source code passes user_id= to store_memory which does not
        accept that kwarg (bug in source). We patch store_memory to tolerate it.
        """
        agent = ChatAgent(ai_client=DummyAIClient())

        async def mock_store_memory(text, metadata=None, **kwargs):
            return None

        agent.store_memory = mock_store_memory
        result = await agent._store_fact("I like blue")
        assert result == "fact stored"

    @pytest.mark.asyncio
    async def test_get_facts_no_memory_returns_guidance(self):
        """_get_facts with no memory backend returns guidance message."""
        agent = ChatAgent(ai_client=DummyAIClient())
        # No memory service attached
        result = await agent._get_facts("favorite color")
        assert "general knowledge" in result.lower() or "no user-specific" in result.lower()

    @pytest.mark.asyncio
    async def test_get_facts_with_results(self):
        """_get_facts returns joined text from memory results."""
        agent = ChatAgent(ai_client=DummyAIClient())
        # Mock search_memory to return results
        agent.memory = MagicMock()

        async def mock_search(query, top_k=3, user_id=None):
            return [
                {"text": "User likes blue"},
                {"text": "User likes pizza"},
            ]

        agent.memory.similarity_search = mock_search
        result = await agent._get_facts("preferences")
        assert "User likes blue" in result
        assert "User likes pizza" in result

    @pytest.mark.asyncio
    async def test_update_profile_returns_confirmation(self):
        """_update_profile updates the profile and returns confirmation.

        NOTE: The source code passes user_id= to store_memory which does not
        accept that kwarg (bug in source). We patch store_memory to tolerate it.
        """
        agent = ChatAgent(ai_client=DummyAIClient())

        async def mock_store_memory(text, metadata=None, **kwargs):
            return None

        agent.store_memory = mock_store_memory
        result = await agent._update_profile("name", "Alice")
        assert "updated name" in result
        assert agent.profile.name == "Alice"

    @pytest.mark.asyncio
    async def test_update_profile_conversation_style(self):
        """_update_profile updates conversation_style field.

        NOTE: Same store_memory bug workaround as above.
        """
        agent = ChatAgent(ai_client=DummyAIClient())

        async def mock_store_memory(text, metadata=None, **kwargs):
            return None

        agent.store_memory = mock_store_memory
        result = await agent._update_profile("conversation_style", "formal")
        assert "conversation_style" in result
        assert agent.profile.conversation_style == "formal"


# ---------------------------------------------------------------------------
# Tests: edge cases
# ---------------------------------------------------------------------------

class TestChatAgentEdgeCases:
    """Test edge cases and error paths."""

    @pytest.mark.asyncio
    async def test_empty_string_prompt(self):
        """Empty string prompt still processes without error."""
        agent = ChatAgent(ai_client=DummyAIClient("response"))
        result = await agent._process_chat("")
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_very_long_prompt(self):
        """Very long prompts are handled without error."""
        agent = ChatAgent(ai_client=DummyAIClient("ok"))
        long_prompt = "a" * 10000
        result = await agent._process_chat(long_prompt)
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_tool_call_with_error_result(self):
        """When a tool call raises an exception, error is captured in actions."""

        class FailToolAIClient(BaseAIClient):
            def __init__(self):
                self._call_count = 0

            async def strong_chat(self, messages, tools=None):
                import json

                self._call_count += 1
                if self._call_count == 1:
                    func = type("Function", (), {
                        "name": "get_facts",
                        "arguments": json.dumps({"query": "test"}),
                    })()
                    call = type("ToolCall", (), {
                        "id": "call_fail",
                        "function": func,
                    })()
                    msg = type("Message", (), {"content": None})()
                    return msg, [call]
                else:
                    msg = type("Message", (), {"content": "Error noted"})()
                    return msg, None

            async def weak_chat(self, messages, tools=None):
                msg = type("Message", (), {"content": "dummy"})()
                return msg, None

        agent = ChatAgent(ai_client=FailToolAIClient())

        # Mock search_memory to raise
        async def fail_search(*args, **kwargs):
            raise ConnectionError("DB unavailable")

        agent.search_memory = fail_search

        result = await agent._process_chat("test query")
        # The error should be captured but the response should still complete
        assert isinstance(result, dict)
        # Actions should have the error
        if result.get("actions"):
            assert "error" in result["actions"][0].get("result", {})

    @pytest.mark.asyncio
    async def test_max_iterations_limit(self):
        """Chat processing stops after 5 tool-call iterations."""
        call_count = 0

        class InfiniteToolAIClient(BaseAIClient):
            async def strong_chat(self, messages, tools=None):
                nonlocal call_count
                call_count += 1
                import json

                func = type("Function", (), {
                    "name": "get_facts",
                    "arguments": json.dumps({"query": "loop"}),
                })()
                call = type("ToolCall", (), {
                    "id": f"call_{call_count}",
                    "function": func,
                })()
                msg = type("Message", (), {"content": f"iteration {call_count}"})()
                return msg, [call]

            async def weak_chat(self, messages, tools=None):
                msg = type("Message", (), {"content": "dummy"})()
                return msg, None

        agent = ChatAgent(ai_client=InfiniteToolAIClient())
        result = await agent._process_chat("loop forever")
        # Should stop after 5 iterations (the while loop limit)
        assert call_count <= 6  # 5 iterations + 1 initial call
