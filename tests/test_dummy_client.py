"""Tests for DummyAIClient used for testing without real API calls."""

import pytest

from jarvis.ai_clients.dummy_client import DummyAIClient
from jarvis.ai_clients.base import BaseAIClient


class TestDummyAIClientInit:
    """Test DummyAIClient initialization."""

    def test_inherits_from_base(self):
        """Test DummyAIClient inherits from BaseAIClient."""
        client = DummyAIClient()
        assert isinstance(client, BaseAIClient)

    def test_no_constructor_args_required(self):
        """Test DummyAIClient needs no arguments."""
        client = DummyAIClient()
        assert client is not None


class TestDummyAIClientStrongChat:
    """Test DummyAIClient strong_chat method."""

    @pytest.mark.asyncio
    async def test_strong_chat_returns_tuple(self):
        """Test strong_chat returns a 2-tuple."""
        client = DummyAIClient()
        result = await client.strong_chat([{"role": "user", "content": "Hello"}])
        assert isinstance(result, tuple)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_strong_chat_message_has_content(self):
        """Test strong_chat message object has 'content' attribute."""
        client = DummyAIClient()
        message, tool_calls = await client.strong_chat(
            [{"role": "user", "content": "Hello"}]
        )
        assert hasattr(message, "content")
        assert message.content == "This is a dummy response."

    @pytest.mark.asyncio
    async def test_strong_chat_tool_calls_is_none(self):
        """Test strong_chat returns None for tool_calls."""
        client = DummyAIClient()
        _, tool_calls = await client.strong_chat(
            [{"role": "user", "content": "Hello"}]
        )
        assert tool_calls is None

    @pytest.mark.asyncio
    async def test_strong_chat_ignores_messages_content(self):
        """Test strong_chat returns the same dummy response regardless of input."""
        client = DummyAIClient()
        msg1, _ = await client.strong_chat([{"role": "user", "content": "Hello"}])
        msg2, _ = await client.strong_chat(
            [{"role": "user", "content": "Something completely different"}]
        )
        assert msg1.content == msg2.content

    @pytest.mark.asyncio
    async def test_strong_chat_ignores_tools(self):
        """Test strong_chat ignores the tools parameter."""
        client = DummyAIClient()
        tools = [{"type": "function", "function": {"name": "test"}}]
        message, tool_calls = await client.strong_chat(
            [{"role": "user", "content": "Hello"}], tools=tools
        )
        assert message.content == "This is a dummy response."
        assert tool_calls is None

    @pytest.mark.asyncio
    async def test_strong_chat_with_empty_messages(self):
        """Test strong_chat works with empty messages list."""
        client = DummyAIClient()
        message, tool_calls = await client.strong_chat([])
        assert message.content == "This is a dummy response."

    @pytest.mark.asyncio
    async def test_strong_chat_message_is_dynamic_class(self):
        """Test the message object is a dynamically created type named 'Message'."""
        client = DummyAIClient()
        message, _ = await client.strong_chat(
            [{"role": "user", "content": "Hello"}]
        )
        # type('Message', (), response) returns the class itself, so __name__ is 'Message'
        assert message.__name__ == "Message"


class TestDummyAIClientWeakChat:
    """Test DummyAIClient weak_chat method."""

    @pytest.mark.asyncio
    async def test_weak_chat_returns_tuple(self):
        """Test weak_chat returns a 2-tuple."""
        client = DummyAIClient()
        result = await client.weak_chat([{"role": "user", "content": "Hello"}])
        assert isinstance(result, tuple)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_weak_chat_message_has_content(self):
        """Test weak_chat message object has 'content' attribute."""
        client = DummyAIClient()
        message, tool_calls = await client.weak_chat(
            [{"role": "user", "content": "Hello"}]
        )
        assert message.content == "This is a dummy response."

    @pytest.mark.asyncio
    async def test_weak_chat_tool_calls_is_none(self):
        """Test weak_chat returns None for tool_calls."""
        client = DummyAIClient()
        _, tool_calls = await client.weak_chat(
            [{"role": "user", "content": "Hello"}]
        )
        assert tool_calls is None

    @pytest.mark.asyncio
    async def test_weak_chat_same_response_as_strong(self):
        """Test weak_chat returns same response as strong_chat."""
        client = DummyAIClient()
        strong_msg, _ = await client.strong_chat(
            [{"role": "user", "content": "Hello"}]
        )
        weak_msg, _ = await client.weak_chat(
            [{"role": "user", "content": "Hello"}]
        )
        assert strong_msg.content == weak_msg.content

    @pytest.mark.asyncio
    async def test_weak_chat_ignores_tools(self):
        """Test weak_chat ignores the tools parameter."""
        client = DummyAIClient()
        tools = [{"type": "function", "function": {"name": "test"}}]
        message, tool_calls = await client.weak_chat(
            [{"role": "user", "content": "Hello"}], tools=tools
        )
        assert message.content == "This is a dummy response."
        assert tool_calls is None


class TestDummyAIClientConsistency:
    """Test DummyAIClient consistency properties."""

    @pytest.mark.asyncio
    async def test_multiple_calls_return_same_content(self):
        """Test multiple calls always return the same content."""
        client = DummyAIClient()
        for _ in range(5):
            message, _ = await client.strong_chat(
                [{"role": "user", "content": "test"}]
            )
            assert message.content == "This is a dummy response."

    @pytest.mark.asyncio
    async def test_strong_and_weak_independent_instances(self):
        """Test strong and weak return independent message objects."""
        client = DummyAIClient()
        msg1, _ = await client.strong_chat([{"role": "user", "content": "a"}])
        msg2, _ = await client.weak_chat([{"role": "user", "content": "b"}])
        # Different object instances
        assert msg1 is not msg2
        # But same content
        assert msg1.content == msg2.content


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
