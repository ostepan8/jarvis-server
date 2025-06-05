from __future__ import annotations

from typing import Optional

from .base import BaseAIClient
from .openai_client import OpenAIClient
from .anthropic_client import AnthropicClient
from .dummy_client import DummyAIClient


class AIClientFactory:
    """Factory to create AI clients based on provider string."""

    @staticmethod
    def create(provider: str, api_key: Optional[str] = None) -> BaseAIClient:
        provider = provider.lower()
        if provider == "openai":
            return OpenAIClient(api_key=api_key)
        if provider == "anthropic":
            return AnthropicClient(api_key=api_key)
        if provider in {"dummy", "mock"}:
            return DummyAIClient()
        raise ValueError(f"Unsupported AI provider: {provider}")
