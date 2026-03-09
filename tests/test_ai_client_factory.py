"""Tests for AI client factory."""

import pytest

from jarvis.ai_clients.factory import AIClientFactory
from jarvis.ai_clients.base import BaseAIClient
from jarvis.ai_clients.openai_client import OpenAIClient
from jarvis.ai_clients.anthropic_client import AnthropicClient
from jarvis.ai_clients.dummy_client import DummyAIClient


class TestAIClientFactory:
    """Test AIClientFactory.create method."""

    def test_create_openai_client(self):
        """Test factory creates OpenAIClient for 'openai' provider."""
        client = AIClientFactory.create("openai", api_key="test-key")
        assert isinstance(client, OpenAIClient)
        assert isinstance(client, BaseAIClient)

    def test_create_openai_client_case_insensitive(self):
        """Test factory handles case-insensitive provider names."""
        client = AIClientFactory.create("OpenAI", api_key="test-key")
        assert isinstance(client, OpenAIClient)

    def test_create_openai_client_uppercase(self):
        """Test factory handles fully uppercase provider name."""
        client = AIClientFactory.create("OPENAI", api_key="test-key")
        assert isinstance(client, OpenAIClient)

    def test_create_anthropic_client(self):
        """Test factory creates AnthropicClient for 'anthropic' provider."""
        client = AIClientFactory.create("anthropic", api_key="test-key")
        assert isinstance(client, AnthropicClient)
        assert isinstance(client, BaseAIClient)

    def test_create_anthropic_client_case_insensitive(self):
        """Test factory handles case-insensitive 'Anthropic'."""
        client = AIClientFactory.create("Anthropic", api_key="test-key")
        assert isinstance(client, AnthropicClient)

    def test_create_dummy_client(self):
        """Test factory creates DummyAIClient for 'dummy' provider."""
        client = AIClientFactory.create("dummy")
        assert isinstance(client, DummyAIClient)
        assert isinstance(client, BaseAIClient)

    def test_create_mock_client(self):
        """Test factory creates DummyAIClient for 'mock' provider."""
        client = AIClientFactory.create("mock")
        assert isinstance(client, DummyAIClient)

    def test_create_mock_client_case_insensitive(self):
        """Test factory handles case-insensitive 'Mock'."""
        client = AIClientFactory.create("Mock")
        assert isinstance(client, DummyAIClient)

    def test_unsupported_provider_raises_value_error(self):
        """Test factory raises ValueError for unknown provider."""
        with pytest.raises(ValueError, match="Unsupported AI provider: unknown"):
            AIClientFactory.create("unknown")

    def test_unsupported_provider_empty_string_raises_value_error(self):
        """Test factory raises ValueError for empty string."""
        with pytest.raises(ValueError, match="Unsupported AI provider"):
            AIClientFactory.create("")

    def test_create_openai_with_custom_models(self):
        """Test factory passes custom model names to OpenAIClient."""
        client = AIClientFactory.create(
            "openai",
            api_key="test-key",
            strong_model="gpt-4-turbo",
            weak_model="gpt-3.5-turbo",
        )
        assert isinstance(client, OpenAIClient)
        assert client.strong_model == "gpt-4-turbo"
        assert client.weak_model == "gpt-3.5-turbo"

    def test_create_openai_with_strong_model_only(self):
        """Test factory passes only strong_model when weak_model is None."""
        client = AIClientFactory.create(
            "openai",
            api_key="test-key",
            strong_model="gpt-4-turbo",
        )
        assert isinstance(client, OpenAIClient)
        assert client.strong_model == "gpt-4-turbo"
        assert client.weak_model == "gpt-4o-mini"  # default

    def test_create_openai_with_weak_model_only(self):
        """Test factory passes only weak_model when strong_model is None."""
        client = AIClientFactory.create(
            "openai",
            api_key="test-key",
            weak_model="gpt-3.5-turbo",
        )
        assert isinstance(client, OpenAIClient)
        assert client.strong_model == "gpt-4o"  # default
        assert client.weak_model == "gpt-3.5-turbo"

    def test_create_openai_with_no_api_key(self):
        """Test factory creates OpenAIClient without explicit api_key (falls back to env).

        Note: OpenAI client does not validate key at construction time,
        so this works even without OPENAI_API_KEY set.
        """
        client = AIClientFactory.create("openai", api_key="fake-key-for-test")
        assert isinstance(client, OpenAIClient)

    def test_create_anthropic_with_no_api_key(self):
        """Test factory creates AnthropicClient without explicit api_key."""
        client = AIClientFactory.create("anthropic")
        assert isinstance(client, AnthropicClient)

    def test_create_dummy_ignores_api_key(self):
        """Test factory creates DummyAIClient ignoring api_key."""
        client = AIClientFactory.create("dummy", api_key="ignored-key")
        assert isinstance(client, DummyAIClient)

    def test_create_dummy_ignores_model_args(self):
        """Test factory creates DummyAIClient ignoring model arguments."""
        client = AIClientFactory.create(
            "dummy",
            api_key="ignored",
            strong_model="ignored",
            weak_model="ignored",
        )
        assert isinstance(client, DummyAIClient)

    def test_anthropic_custom_models_not_passed(self):
        """Test factory does not pass custom models to AnthropicClient (not supported by factory)."""
        client = AIClientFactory.create(
            "anthropic",
            api_key="test-key",
            strong_model="claude-3-opus-custom",
            weak_model="claude-3-haiku-custom",
        )
        assert isinstance(client, AnthropicClient)
        # AnthropicClient uses its own defaults since factory doesn't forward models
        assert client.strong_model == "claude-3-opus-20240229"
        assert client.weak_model == "claude-3-haiku-20240307"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
