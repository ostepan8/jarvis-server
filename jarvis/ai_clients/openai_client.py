from __future__ import annotations

import os
from typing import Any, Dict, List, Tuple

from openai import AsyncOpenAI

from .base import BaseAIClient


class OpenAIClient(BaseAIClient):
    """AI client that delegates requests to OpenAI's API."""

    def __init__(self, api_key: str | None = None, model: str = "gpt-4-turbo-preview") -> None:
        self.client = AsyncOpenAI(api_key=api_key or os.environ.get("OPENAI_API_KEY"))
        self.model = model

    async def chat(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]) -> Tuple[Any, Any]:
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=tools,
            tool_choice="auto",
        )
        message = response.choices[0].message
        return message, message.tool_calls
