from __future__ import annotations

import os
from typing import Any, Dict, List, Tuple

import anthropic

from .base import BaseAIClient


class AnthropicClient(BaseAIClient):
    """AI client that delegates requests to Anthropic's API."""

    def __init__(
        self,
        api_key: str | None = None,
        strong_model: str = "claude-3-opus-20240229",
        weak_model: str = "claude-3-haiku-20240307",
    ) -> None:
        self.client = anthropic.AsyncAnthropic(
            api_key=api_key or os.environ.get("ANTHROPIC_API_KEY")
        )
        self.strong_model = strong_model
        self.weak_model = weak_model

    async def _chat(
        self, messages: List[Dict[str, Any]], model: str
    ) -> Tuple[Any, Any]:
        response = await self.client.messages.create(
            model=model,
            messages=messages,
            system="",
            max_tokens=1000,
        )
        message = response
        return message, []  # tool calls not implemented for Anthropic yet

    async def strong_chat(
        self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]] | None = None
    ) -> Tuple[Any, Any]:
        return await self._chat(messages, self.strong_model)

    async def weak_chat(
        self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]] | None = None
    ) -> Tuple[Any, Any]:
        return await self._chat(messages, self.weak_model)
