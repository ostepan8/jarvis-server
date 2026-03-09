"""Tests for Anthropic AI client wrapper."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from jarvis.ai_clients.anthropic_client import AnthropicClient
from jarvis.ai_clients.base import BaseAIClient


class TestAnthropicClientInit:
    """Test AnthropicClient initialization."""

    def test_inherits_from_base(self):
        """Test AnthropicClient inherits from BaseAIClient."""
        client = AnthropicClient(api_key="test-key")
        assert isinstance(client, BaseAIClient)

    def test_default_models(self):
        """Test default model assignments."""
        client = AnthropicClient(api_key="test-key")
        assert client.strong_model == "claude-3-opus-20240229"
        assert client.weak_model == "claude-3-haiku-20240307"

    def test_custom_models(self):
        """Test custom model assignments."""
        client = AnthropicClient(
            api_key="test-key",
            strong_model="claude-custom-strong",
            weak_model="claude-custom-weak",
        )
        assert client.strong_model == "claude-custom-strong"
        assert client.weak_model == "claude-custom-weak"

    def test_client_created_with_api_key(self):
        """Test AsyncAnthropic client is instantiated."""
        client = AnthropicClient(api_key="test-key")
        assert client.client is not None


class TestAnthropicClientChat:
    """Test AnthropicClient chat methods."""

    @pytest.fixture
    def client(self):
        """Create an AnthropicClient with mocked AsyncAnthropic."""
        c = AnthropicClient(api_key="test-key")
        return c

    def _make_mock_response(self, content="Hello from Claude"):
        """Create a mock Anthropic response."""
        response = MagicMock()
        response.content = [MagicMock(text=content)]
        return response

    @pytest.mark.asyncio
    async def test_strong_chat_returns_message_and_empty_tool_calls(self, client):
        """Test strong_chat returns message and empty list for tool_calls."""
        mock_response = self._make_mock_response()
        client.client = MagicMock()
        client.client.messages = MagicMock()
        client.client.messages.create = AsyncMock(return_value=mock_response)

        messages = [{"role": "user", "content": "Hello"}]
        message, tool_calls = await client.strong_chat(messages)

        assert message is mock_response
        assert tool_calls == []

    @pytest.mark.asyncio
    async def test_weak_chat_returns_message_and_empty_tool_calls(self, client):
        """Test weak_chat returns message and empty list for tool_calls."""
        mock_response = self._make_mock_response()
        client.client = MagicMock()
        client.client.messages = MagicMock()
        client.client.messages.create = AsyncMock(return_value=mock_response)

        messages = [{"role": "user", "content": "Hello"}]
        message, tool_calls = await client.weak_chat(messages)

        assert message is mock_response
        assert tool_calls == []

    @pytest.mark.asyncio
    async def test_strong_chat_uses_strong_model(self, client):
        """Test strong_chat passes the strong_model to the API."""
        mock_response = self._make_mock_response()
        client.client = MagicMock()
        client.client.messages = MagicMock()
        client.client.messages.create = AsyncMock(return_value=mock_response)

        messages = [{"role": "user", "content": "Hello"}]
        await client.strong_chat(messages)

        call_kwargs = client.client.messages.create.call_args[1]
        assert call_kwargs["model"] == "claude-3-opus-20240229"

    @pytest.mark.asyncio
    async def test_weak_chat_uses_weak_model(self, client):
        """Test weak_chat passes the weak_model to the API."""
        mock_response = self._make_mock_response()
        client.client = MagicMock()
        client.client.messages = MagicMock()
        client.client.messages.create = AsyncMock(return_value=mock_response)

        messages = [{"role": "user", "content": "Hello"}]
        await client.weak_chat(messages)

        call_kwargs = client.client.messages.create.call_args[1]
        assert call_kwargs["model"] == "claude-3-haiku-20240307"

    @pytest.mark.asyncio
    async def test_chat_passes_messages_to_api(self, client):
        """Test that messages are correctly passed to the API."""
        mock_response = self._make_mock_response()
        client.client = MagicMock()
        client.client.messages = MagicMock()
        client.client.messages.create = AsyncMock(return_value=mock_response)

        messages = [{"role": "user", "content": "Hello Claude"}]
        await client.strong_chat(messages)

        call_kwargs = client.client.messages.create.call_args[1]
        assert call_kwargs["messages"] == messages
        assert call_kwargs["system"] == ""
        assert call_kwargs["max_tokens"] == 1000

    @pytest.mark.asyncio
    async def test_chat_api_error_propagates(self, client):
        """Test that API errors propagate through the client."""
        client.client = MagicMock()
        client.client.messages = MagicMock()
        client.client.messages.create = AsyncMock(
            side_effect=Exception("Anthropic API error")
        )

        messages = [{"role": "user", "content": "Hello"}]
        with pytest.raises(Exception, match="Anthropic API error"):
            await client.strong_chat(messages)

    @pytest.mark.asyncio
    async def test_strong_chat_ignores_tools_parameter(self, client):
        """Test strong_chat accepts but ignores the tools parameter."""
        mock_response = self._make_mock_response()
        client.client = MagicMock()
        client.client.messages = MagicMock()
        client.client.messages.create = AsyncMock(return_value=mock_response)

        messages = [{"role": "user", "content": "Hello"}]
        tools = [{"type": "function", "function": {"name": "test"}}]
        message, tool_calls = await client.strong_chat(messages, tools=tools)

        # Should succeed without passing tools to the API
        assert message is mock_response
        assert tool_calls == []
        call_kwargs = client.client.messages.create.call_args[1]
        assert "tools" not in call_kwargs

    @pytest.mark.asyncio
    async def test_weak_chat_ignores_tools_parameter(self, client):
        """Test weak_chat accepts but ignores the tools parameter."""
        mock_response = self._make_mock_response()
        client.client = MagicMock()
        client.client.messages = MagicMock()
        client.client.messages.create = AsyncMock(return_value=mock_response)

        messages = [{"role": "user", "content": "Hello"}]
        tools = [{"type": "function", "function": {"name": "test"}}]
        message, tool_calls = await client.weak_chat(messages, tools=tools)

        assert tool_calls == []

    @pytest.mark.asyncio
    async def test_chat_with_multiple_messages(self, client):
        """Test chat with a conversation history."""
        mock_response = self._make_mock_response()
        client.client = MagicMock()
        client.client.messages = MagicMock()
        client.client.messages.create = AsyncMock(return_value=mock_response)

        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi!"},
            {"role": "user", "content": "How are you?"},
        ]
        message, tool_calls = await client.strong_chat(messages)

        call_kwargs = client.client.messages.create.call_args[1]
        assert len(call_kwargs["messages"]) == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
