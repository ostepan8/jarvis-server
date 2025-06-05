from __future__ import annotations

import os
from typing import Any, Dict, List, Tuple

import anthropic

from .base import BaseAIClient


class AnthropicClient(BaseAIClient):
    """AI client that delegates requests to Anthropic's API."""

    def __init__(self, api_key: str | None = None, model: str = "claude-3-opus-20240229") -> None:
        self.client = anthropic.AsyncAnthropic(api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"))
        self.model = model

    async def chat(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]) -> Tuple[Any, Any]:
        response = await self.client.messages.create(
            model=self.model,
            messages=messages,
            system="",
            max_tokens=1000,
        )
        message = response
        return message, []  # tool calls not implemented for Anthropic yet
