"""Tests for NetworkAgent base class."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Set

from jarvis.agents.base import NetworkAgent
from jarvis.agents.agent_network import AgentNetwork
from jarvis.agents.message import Message
from jarvis.core.profile import AgentProfile


# ---------------------------------------------------------------------------
# Concrete subclass for testing the abstract base
# ---------------------------------------------------------------------------

class ConcreteAgent(NetworkAgent):
    """Minimal concrete agent for testing base class behavior."""

    def __init__(self, name, capabilities=None, **kwargs):
        super().__init__(name, **kwargs)
        self._capabilities = capabilities or set()

    @property
    def capabilities(self) -> Set[str]:
        return self._capabilities


class CapabilityAgent(NetworkAgent):
    """Agent with intent_map for testing run_capability."""

    def __init__(self, name, **kwargs):
        super().__init__(name, **kwargs)
        self._capabilities = {"greet", "compute"}
        self.intent_map["greet"] = self._greet
        self.intent_map["compute"] = self._compute_sync

    @property
    def capabilities(self) -> Set[str]:
        return self._capabilities

    async def _greet(self, name="World"):
        return f"Hello, {name}!"

    def _compute_sync(self, x=1, y=2):
        return x + y


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestNetworkAgentInit:
    """Test NetworkAgent initialization."""

    def test_name_property(self):
        """Test agent name is accessible via property."""
        agent = ConcreteAgent("test-agent")
        assert agent.name == "test-agent"

    def test_default_description(self):
        """Test default description."""
        agent = ConcreteAgent("test-agent")
        assert agent.description == "Base network agent"

    def test_default_capabilities_empty(self):
        """Test default capabilities from base class is empty."""
        agent = ConcreteAgent("test-agent")
        assert agent.capabilities == set()

    def test_capabilities_from_subclass(self):
        """Test capabilities set in subclass."""
        agent = ConcreteAgent("test-agent", capabilities={"cap1", "cap2"})
        assert agent.capabilities == {"cap1", "cap2"}

    def test_network_is_none_initially(self):
        """Test network is None before set_network."""
        agent = ConcreteAgent("test-agent")
        assert agent.network is None

    def test_set_network(self):
        """Test set_network assigns the network."""
        agent = ConcreteAgent("test-agent")
        network = AgentNetwork()
        agent.set_network(network)
        assert agent.network is network

    def test_default_profile(self):
        """Test agent gets a default profile."""
        agent = ConcreteAgent("test-agent")
        assert agent.profile is not None
        assert isinstance(agent.profile, AgentProfile)

    def test_custom_profile(self):
        """Test agent accepts a custom profile."""
        profile = AgentProfile(name="custom", preferred_personality="formal")
        agent = ConcreteAgent("test-agent", profile=profile)
        assert agent.profile.name == "custom"
        assert agent.profile.preferred_personality == "formal"

    def test_active_tasks_empty_initially(self):
        """Test active_tasks starts empty."""
        agent = ConcreteAgent("test-agent")
        assert agent.active_tasks == {}

    def test_message_handlers_setup(self):
        """Test base message handlers are registered."""
        agent = ConcreteAgent("test-agent")
        assert "capability_request" in agent.message_handlers
        assert "capability_response" in agent.message_handlers
        assert "error" in agent.message_handlers

    def test_intent_map_empty_initially(self):
        """Test intent_map starts empty for base agent."""
        agent = ConcreteAgent("test-agent")
        assert agent.intent_map == {}


class TestNetworkAgentReceiveMessage:
    """Test NetworkAgent message handling."""

    @pytest.mark.asyncio
    async def test_receive_known_message_type(self):
        """Test receiving a message with a known handler."""
        agent = ConcreteAgent("test-agent")
        handled = []

        async def custom_handler(msg):
            handled.append(msg)

        agent.message_handlers["custom_type"] = custom_handler
        msg = Message(
            from_agent="sender",
            to_agent="test-agent",
            message_type="custom_type",
            content={"data": "test"},
            request_id="req-1",
        )
        await agent.receive_message(msg)
        assert len(handled) == 1
        assert handled[0].content == {"data": "test"}

    @pytest.mark.asyncio
    async def test_receive_unknown_message_type(self):
        """Test receiving a message with an unknown type calls _handle_unknown."""
        agent = ConcreteAgent("test-agent")
        # Should not raise
        msg = Message(
            from_agent="sender",
            to_agent="test-agent",
            message_type="nonexistent_type",
            content={},
            request_id="req-1",
        )
        await agent.receive_message(msg)

    @pytest.mark.asyncio
    async def test_receive_message_handler_error_sends_error(self):
        """Test that handler errors trigger send_error."""
        agent = ConcreteAgent("test-agent")
        network = AgentNetwork()
        network.register_agent(agent)

        # Register a handler that raises
        async def bad_handler(msg):
            raise RuntimeError("Handler failed")

        agent.message_handlers["bad_type"] = bad_handler
        agent.send_error = AsyncMock()

        msg = Message(
            from_agent="sender",
            to_agent="test-agent",
            message_type="bad_type",
            content={},
            request_id="req-1",
        )
        await agent.receive_message(msg)
        agent.send_error.assert_called_once_with("sender", "Handler failed", "req-1")


class TestNetworkAgentCapabilityRequest:
    """Test capability_request handling in base class."""

    @pytest.mark.asyncio
    async def test_handle_capability_request_raises_not_implemented(self):
        """Test base class _handle_capability_request raises NotImplementedError."""
        agent = ConcreteAgent("test-agent")
        msg = Message(
            from_agent="sender",
            message_type="capability_request",
            content={},
            request_id="req-1",
        )
        with pytest.raises(NotImplementedError, match="must implement"):
            await agent._handle_capability_request(msg)

    @pytest.mark.asyncio
    async def test_handle_capability_response_raises_not_implemented(self):
        """Test base class _handle_capability_response raises NotImplementedError."""
        agent = ConcreteAgent("test-agent")
        msg = Message(
            from_agent="sender",
            message_type="capability_response",
            content={},
            request_id="req-1",
        )
        with pytest.raises(NotImplementedError, match="must implement"):
            await agent._handle_capability_response(msg)


class TestNetworkAgentRunCapability:
    """Test run_capability method."""

    @pytest.mark.asyncio
    async def test_run_async_capability(self):
        """Test running an async capability from intent_map."""
        agent = CapabilityAgent("test-agent")
        result = await agent.run_capability("greet", name="Alice")
        assert result == "Hello, Alice!"

    @pytest.mark.asyncio
    async def test_run_sync_capability(self):
        """Test running a sync capability from intent_map (runs in executor)."""
        agent = CapabilityAgent("test-agent")
        result = await agent.run_capability("compute", x=3, y=4)
        assert result == 7

    @pytest.mark.asyncio
    async def test_run_unknown_capability_raises(self):
        """Test running an unknown capability raises NotImplementedError."""
        agent = CapabilityAgent("test-agent")
        with pytest.raises(NotImplementedError, match="does not implement capability"):
            await agent.run_capability("unknown_capability")


class TestNetworkAgentSendMessage:
    """Test send_message method."""

    @pytest.mark.asyncio
    async def test_send_message_creates_message_and_sends(self):
        """Test send_message creates a Message and delegates to network."""
        agent = ConcreteAgent("test-agent")
        network = MagicMock()
        network.send_message = AsyncMock()
        agent.set_network(network)

        await agent.send_message("receiver", "test_type", {"data": 1}, "req-1")
        network.send_message.assert_called_once()
        sent_msg = network.send_message.call_args[0][0]
        assert sent_msg.from_agent == "test-agent"
        assert sent_msg.to_agent == "receiver"
        assert sent_msg.message_type == "test_type"
        assert sent_msg.content == {"data": 1}
        assert sent_msg.request_id == "req-1"

    @pytest.mark.asyncio
    async def test_send_message_with_reply_to(self):
        """Test send_message includes reply_to field."""
        agent = ConcreteAgent("test-agent")
        network = MagicMock()
        network.send_message = AsyncMock()
        agent.set_network(network)

        await agent.send_message(
            "receiver", "response", {"data": 1}, "req-1", reply_to="msg-1"
        )
        sent_msg = network.send_message.call_args[0][0]
        assert sent_msg.reply_to == "msg-1"

    @pytest.mark.asyncio
    async def test_send_message_broadcast(self):
        """Test send_message with None to_agent for broadcast."""
        agent = ConcreteAgent("test-agent")
        network = MagicMock()
        network.send_message = AsyncMock()
        agent.set_network(network)

        await agent.send_message(None, "broadcast", {"data": 1}, "req-1")
        sent_msg = network.send_message.call_args[0][0]
        assert sent_msg.to_agent is None


class TestNetworkAgentSendError:
    """Test send_error method."""

    @pytest.mark.asyncio
    async def test_send_error_sends_error_message(self):
        """Test send_error sends an error message type."""
        agent = ConcreteAgent("test-agent")
        network = MagicMock()
        network.send_message = AsyncMock()
        agent.set_network(network)

        await agent.send_error("receiver", "Something went wrong", "req-1")
        sent_msg = network.send_message.call_args[0][0]
        assert sent_msg.message_type == "error"
        assert sent_msg.content == {"error": "Something went wrong"}
        assert sent_msg.to_agent == "receiver"


class TestNetworkAgentSendCapabilityResponse:
    """Test send_capability_response method."""

    @pytest.mark.asyncio
    async def test_send_capability_response(self):
        """Test send_capability_response sends correct message."""
        agent = ConcreteAgent("test-agent")
        network = MagicMock()
        network.send_message = AsyncMock()
        agent.set_network(network)

        await agent.send_capability_response(
            "requester", {"result": "ok"}, "req-1", "msg-1"
        )
        sent_msg = network.send_message.call_args[0][0]
        assert sent_msg.message_type == "capability_response"
        assert sent_msg.to_agent == "requester"
        assert sent_msg.content == {"result": "ok"}
        assert sent_msg.reply_to == "msg-1"


class TestNetworkAgentRequestCapability:
    """Test request_capability method."""

    @pytest.mark.asyncio
    async def test_request_capability_delegates_to_network(self):
        """Test request_capability calls network.request_capability."""
        agent = ConcreteAgent("test-agent")
        network = MagicMock()
        network.request_capability = AsyncMock(return_value=["provider1"])
        agent.set_network(network)

        req_id = await agent.request_capability(
            "test_cap", {"data": "test"}, request_id="req-1"
        )
        assert req_id == "req-1"
        network.request_capability.assert_called_once()
        assert agent.active_tasks["req-1"]["capability"] == "test_cap"

    @pytest.mark.asyncio
    async def test_request_capability_generates_request_id(self):
        """Test request_capability generates a UUID when none given."""
        agent = ConcreteAgent("test-agent")
        network = MagicMock()
        network.request_capability = AsyncMock(return_value=["provider1"])
        agent.set_network(network)

        req_id = await agent.request_capability("test_cap", {"data": "test"})
        assert req_id is not None
        assert len(req_id) > 0

    @pytest.mark.asyncio
    async def test_request_capability_no_providers_no_active_task(self):
        """Test request_capability with no providers does not create active task."""
        agent = ConcreteAgent("test-agent")
        network = MagicMock()
        network.request_capability = AsyncMock(return_value=[])
        agent.set_network(network)

        req_id = await agent.request_capability(
            "test_cap", {"data": "test"}, request_id="req-1"
        )
        assert "req-1" not in agent.active_tasks


class TestNetworkAgentUpdateProfile:
    """Test update_profile method."""

    def test_update_existing_field(self):
        """Test updating an existing profile field."""
        agent = ConcreteAgent("test-agent")
        agent.update_profile(preferred_personality="formal")
        assert agent.profile.preferred_personality == "formal"

    def test_update_multiple_fields(self):
        """Test updating multiple profile fields."""
        agent = ConcreteAgent("test-agent")
        agent.update_profile(
            preferred_personality="formal",
            conversation_style="professional",
        )
        assert agent.profile.preferred_personality == "formal"
        assert agent.profile.conversation_style == "professional"

    def test_update_nonexistent_field_ignored(self):
        """Test updating a nonexistent field is silently ignored."""
        agent = ConcreteAgent("test-agent")
        agent.update_profile(nonexistent_field="value")
        assert not hasattr(agent.profile, "nonexistent_field")

    def test_update_creates_profile_if_none(self):
        """Test update_profile creates a new profile if one does not exist."""
        agent = ConcreteAgent("test-agent")
        agent.profile = None
        agent.update_profile(preferred_personality="sarcastic")
        assert agent.profile is not None
        assert agent.profile.preferred_personality == "sarcastic"


class TestNetworkAgentMemoryHelpers:
    """Test remember/recall shared memory helpers."""

    @pytest.mark.asyncio
    async def test_remember_returns_none_without_network(self):
        """Test remember returns None when no network is attached."""
        agent = ConcreteAgent("test-agent")
        result = await agent.remember("test content")
        assert result is None

    @pytest.mark.asyncio
    async def test_recall_returns_default_without_network(self):
        """Test recall returns default message when no network is attached."""
        agent = ConcreteAgent("test-agent")
        result = await agent.recall("test query")
        assert result == "No memory network available."

    @pytest.mark.asyncio
    async def test_search_memory_returns_empty_without_memory_service(self):
        """Test search_memory returns empty list without memory service."""
        agent = ConcreteAgent("test-agent")
        result = await agent.search_memory("test query")
        assert result == []


class TestNetworkAgentContextHelpers:
    """Test context extraction and enhancement helpers for DAG execution."""

    def test_extract_context_from_message(self):
        """Test extracting context from a capability request message."""
        agent = ConcreteAgent("test-agent")
        msg = Message(
            from_agent="sender",
            message_type="capability_request",
            content={
                "data": {
                    "context": {
                        "previous_results": [{"capability": "search", "result": {}}],
                        "conversation_history": [{"role": "user", "content": "hi"}],
                    }
                }
            },
            request_id="req-1",
        )
        context_info = agent._extract_context_from_message(msg)
        assert "context" in context_info
        assert len(context_info["previous_results"]) == 1
        assert len(context_info["conversation_history"]) == 1

    def test_extract_context_from_message_empty(self):
        """Test extracting context when no context is present."""
        agent = ConcreteAgent("test-agent")
        msg = Message(
            from_agent="sender",
            message_type="capability_request",
            content={"data": {}},
            request_id="req-1",
        )
        context_info = agent._extract_context_from_message(msg)
        assert context_info["context"] == {}
        assert context_info["previous_results"] == []
        assert context_info["conversation_history"] == []

    def test_enhance_prompt_with_no_previous_results(self):
        """Test enhance_prompt returns original when no previous results."""
        agent = ConcreteAgent("test-agent")
        prompt = "What is the weather?"
        result = agent._enhance_prompt_with_context(prompt, [])
        assert result == prompt

    def test_enhance_prompt_with_previous_results(self):
        """Test enhance_prompt appends previous results context."""
        agent = ConcreteAgent("test-agent")
        prompt = "Summarize the results"
        previous = [
            {
                "capability": "search",
                "from_agent": "SearchAgent",
                "result": {"response": "Found 3 results"},
            }
        ]
        result = agent._enhance_prompt_with_context(prompt, previous)
        assert "Summarize the results" in result
        assert "search" in result
        assert "SearchAgent" in result
        assert "Found 3 results" in result

    def test_get_previous_result_by_capability_found(self):
        """Test finding a specific capability result."""
        agent = ConcreteAgent("test-agent")
        previous = [
            {"capability": "search", "result": {"data": "search_result"}},
            {"capability": "weather", "result": {"data": "weather_result"}},
        ]
        result = agent._get_previous_result_by_capability(previous, "weather")
        assert result == {"data": "weather_result"}

    def test_get_previous_result_by_capability_not_found(self):
        """Test returning None when capability not found."""
        agent = ConcreteAgent("test-agent")
        previous = [
            {"capability": "search", "result": {"data": "search_result"}},
        ]
        result = agent._get_previous_result_by_capability(previous, "calendar")
        assert result is None

    def test_get_previous_result_by_capability_empty_list(self):
        """Test returning None with empty previous results."""
        agent = ConcreteAgent("test-agent")
        result = agent._get_previous_result_by_capability([], "anything")
        assert result is None


class TestNetworkAgentHandleError:
    """Test error handling in base agent."""

    @pytest.mark.asyncio
    async def test_handle_error_logs_error(self):
        """Test _handle_error logs the error (should not raise)."""
        agent = ConcreteAgent("test-agent")
        msg = Message(
            from_agent="sender",
            message_type="error",
            content="An error occurred",
            request_id="req-1",
        )
        # Should not raise
        await agent._handle_error(msg)


class TestNetworkAgentDecideNextStep:
    """Test autonomous routing helpers."""

    @pytest.mark.asyncio
    async def test_decide_next_step_defaults_to_complete(self):
        """Test default _decide_next_step returns 'complete' action."""
        agent = ConcreteAgent("test-agent")
        result = await agent._decide_next_step({}, {}, "prompt")
        assert result == {"action": "complete"}


class TestNetworkAgentRequestAndWait:
    """Test _request_and_wait_for_agent helper."""

    @pytest.mark.asyncio
    async def test_request_and_wait_raises_without_network(self):
        """Test _request_and_wait_for_agent raises if no network."""
        agent = ConcreteAgent("test-agent")
        with pytest.raises(RuntimeError, match="not connected to network"):
            await agent._request_and_wait_for_agent(
                "test_cap", {"data": "test"}, "req-1"
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
