from __future__ import annotations

import os
from typing import Any, Dict, List, Tuple

from openai import AsyncOpenAI

from .base import BaseAIClient
from ..performance import track_async


class OpenAIClient(BaseAIClient):
    """AI client that delegates requests to OpenAI's API."""

    def __init__(
        self,
        api_key: str | None = None,
        strong_model: str = "gpt-4-turbo-preview",
        weak_model: str = "gpt-3.5-turbo",
    ) -> None:
        self.client = AsyncOpenAI(api_key=api_key or os.environ.get("OPENAI_API_KEY"))
        self.strong_model = strong_model
        self.weak_model = weak_model

    @track_async("llm_reasoning")
    async def _chat(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]] | None,
        model: str,
    ) -> Tuple[Any, Any]:
        params: Dict[str, Any] = {"model": model, "messages": messages}

        # Only add tools and tool_choice if tools are actually provided
        if tools:
            params["tools"] = tools
            params["tool_choice"] = "auto"
        # Don't set tool_choice at all when there are no tools

        response = await self.client.chat.completions.create(**params)
        message = response.choices[0].message

        # Return the message and any tool calls (will be None if no tools were used)
        return message, getattr(message, "tool_calls", None)

    async def strong_chat(
        self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]] | None = None
    ) -> Tuple[Any, Any]:
        return await self._chat(messages, tools, self.strong_model)

    async def weak_chat(
        self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]] | None = None
    ) -> Tuple[Any, Any]:
        return await self._chat(messages, tools, self.weak_model)
