"""Tests for OpenAI AI client wrapper."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from jarvis.ai_clients.openai_client import OpenAIClient
from jarvis.ai_clients.base import BaseAIClient


class TestOpenAIClientInit:
    """Test OpenAIClient initialization."""

    def test_inherits_from_base(self):
        """Test OpenAIClient inherits from BaseAIClient."""
        client = OpenAIClient(api_key="test-key")
        assert isinstance(client, BaseAIClient)

    def test_default_models(self):
        """Test default model assignments."""
        client = OpenAIClient(api_key="test-key")
        assert client.strong_model == "gpt-4o"
        assert client.weak_model == "gpt-4o-mini"

    def test_custom_models(self):
        """Test custom model assignments."""
        client = OpenAIClient(
            api_key="test-key",
            strong_model="gpt-4-turbo",
            weak_model="gpt-3.5-turbo",
        )
        assert client.strong_model == "gpt-4-turbo"
        assert client.weak_model == "gpt-3.5-turbo"

    def test_client_created_with_api_key(self):
        """Test AsyncOpenAI client is instantiated."""
        client = OpenAIClient(api_key="test-key")
        assert client.client is not None


class TestOpenAIClientChat:
    """Test OpenAIClient chat methods."""

    @pytest.fixture
    def client(self):
        """Create an OpenAIClient with mocked AsyncOpenAI."""
        c = OpenAIClient(api_key="test-key")
        return c

    def _make_mock_response(self, content="Hello", tool_calls=None):
        """Create a mock OpenAI response."""
        message = MagicMock()
        message.content = content
        message.tool_calls = tool_calls
        choice = MagicMock()
        choice.message = message
        response = MagicMock()
        response.choices = [choice]
        return response

    @pytest.mark.asyncio
    async def test_strong_chat_returns_message_and_tool_calls(self, client):
        """Test strong_chat returns a tuple of (message, tool_calls)."""
        mock_response = self._make_mock_response(content="Response text")
        client.client = MagicMock()
        client.client.chat = MagicMock()
        client.client.chat.completions = MagicMock()
        client.client.chat.completions.create = AsyncMock(return_value=mock_response)

        messages = [{"role": "user", "content": "Hello"}]
        message, tool_calls = await client.strong_chat(messages)

        assert message.content == "Response text"
        assert tool_calls is None  # default mock has no tool_calls attribute value set
        client.client.chat.completions.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_weak_chat_returns_message_and_tool_calls(self, client):
        """Test weak_chat returns a tuple of (message, tool_calls)."""
        mock_response = self._make_mock_response(content="Weak response")
        client.client = MagicMock()
        client.client.chat = MagicMock()
        client.client.chat.completions = MagicMock()
        client.client.chat.completions.create = AsyncMock(return_value=mock_response)

        messages = [{"role": "user", "content": "Hello"}]
        message, tool_calls = await client.weak_chat(messages)

        assert message.content == "Weak response"

    @pytest.mark.asyncio
    async def test_strong_chat_uses_strong_model(self, client):
        """Test strong_chat passes the strong_model to the API."""
        mock_response = self._make_mock_response()
        client.client = MagicMock()
        client.client.chat = MagicMock()
        client.client.chat.completions = MagicMock()
        client.client.chat.completions.create = AsyncMock(return_value=mock_response)

        messages = [{"role": "user", "content": "Hello"}]
        await client.strong_chat(messages)

        call_kwargs = client.client.chat.completions.create.call_args[1]
        assert call_kwargs["model"] == "gpt-4o"

    @pytest.mark.asyncio
    async def test_weak_chat_uses_weak_model(self, client):
        """Test weak_chat passes the weak_model to the API."""
        mock_response = self._make_mock_response()
        client.client = MagicMock()
        client.client.chat = MagicMock()
        client.client.chat.completions = MagicMock()
        client.client.chat.completions.create = AsyncMock(return_value=mock_response)

        messages = [{"role": "user", "content": "Hello"}]
        await client.weak_chat(messages)

        call_kwargs = client.client.chat.completions.create.call_args[1]
        assert call_kwargs["model"] == "gpt-4o-mini"

    @pytest.mark.asyncio
    async def test_chat_with_tools(self, client):
        """Test chat includes tools and tool_choice when tools provided."""
        mock_tool_call = MagicMock()
        mock_tool_call.function.name = "search"
        mock_response = self._make_mock_response(tool_calls=[mock_tool_call])
        client.client = MagicMock()
        client.client.chat = MagicMock()
        client.client.chat.completions = MagicMock()
        client.client.chat.completions.create = AsyncMock(return_value=mock_response)

        messages = [{"role": "user", "content": "What is the weather?"}]
        tools = [{"type": "function", "function": {"name": "search"}}]
        message, tool_calls = await client.strong_chat(messages, tools=tools)

        call_kwargs = client.client.chat.completions.create.call_args[1]
        assert "tools" in call_kwargs
        assert call_kwargs["tool_choice"] == "auto"
        assert tool_calls is not None
        assert len(tool_calls) == 1

    @pytest.mark.asyncio
    async def test_chat_without_tools_omits_tool_choice(self, client):
        """Test chat does not include tool_choice when no tools are provided."""
        mock_response = self._make_mock_response()
        client.client = MagicMock()
        client.client.chat = MagicMock()
        client.client.chat.completions = MagicMock()
        client.client.chat.completions.create = AsyncMock(return_value=mock_response)

        messages = [{"role": "user", "content": "Hello"}]
        await client.strong_chat(messages)

        call_kwargs = client.client.chat.completions.create.call_args[1]
        assert "tools" not in call_kwargs
        assert "tool_choice" not in call_kwargs

    @pytest.mark.asyncio
    async def test_chat_with_empty_tools_list_omits_tool_choice(self, client):
        """Test chat omits tools/tool_choice when tools is an empty list."""
        mock_response = self._make_mock_response()
        client.client = MagicMock()
        client.client.chat = MagicMock()
        client.client.chat.completions = MagicMock()
        client.client.chat.completions.create = AsyncMock(return_value=mock_response)

        messages = [{"role": "user", "content": "Hello"}]
        await client.strong_chat(messages, tools=[])

        call_kwargs = client.client.chat.completions.create.call_args[1]
        assert "tools" not in call_kwargs
        assert "tool_choice" not in call_kwargs

    @pytest.mark.asyncio
    async def test_chat_with_none_tools_omits_tool_choice(self, client):
        """Test chat omits tools/tool_choice when tools is None."""
        mock_response = self._make_mock_response()
        client.client = MagicMock()
        client.client.chat = MagicMock()
        client.client.chat.completions = MagicMock()
        client.client.chat.completions.create = AsyncMock(return_value=mock_response)

        messages = [{"role": "user", "content": "Hello"}]
        await client.strong_chat(messages, tools=None)

        call_kwargs = client.client.chat.completions.create.call_args[1]
        assert "tools" not in call_kwargs
        assert "tool_choice" not in call_kwargs

    @pytest.mark.asyncio
    async def test_chat_api_error_propagates(self, client):
        """Test that API errors propagate through the client."""
        client.client = MagicMock()
        client.client.chat = MagicMock()
        client.client.chat.completions = MagicMock()
        client.client.chat.completions.create = AsyncMock(
            side_effect=Exception("API error")
        )

        messages = [{"role": "user", "content": "Hello"}]
        with pytest.raises(Exception, match="API error"):
            await client.strong_chat(messages)

    @pytest.mark.asyncio
    async def test_chat_passes_messages_to_api(self, client):
        """Test that messages are correctly passed to the API."""
        mock_response = self._make_mock_response()
        client.client = MagicMock()
        client.client.chat = MagicMock()
        client.client.chat.completions = MagicMock()
        client.client.chat.completions.create = AsyncMock(return_value=mock_response)

        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello"},
        ]
        await client.strong_chat(messages)

        call_kwargs = client.client.chat.completions.create.call_args[1]
        assert call_kwargs["messages"] == messages

    @pytest.mark.asyncio
    async def test_message_without_tool_calls_attribute_returns_none(self, client):
        """Test message with no tool_calls attribute returns None for tool_calls."""
        message = MagicMock(spec=[])  # No attributes at all
        message.content = "Hello"
        # getattr with default None should return None
        choice = MagicMock()
        choice.message = message
        response = MagicMock()
        response.choices = [choice]
        client.client = MagicMock()
        client.client.chat = MagicMock()
        client.client.chat.completions = MagicMock()
        client.client.chat.completions.create = AsyncMock(return_value=response)

        messages = [{"role": "user", "content": "Hello"}]
        msg, tool_calls = await client.strong_chat(messages)
        assert tool_calls is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
