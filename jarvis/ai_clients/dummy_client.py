from __future__ import annotations

from typing import Any, Dict, List, Tuple

from .base import BaseAIClient


class DummyAIClient(BaseAIClient):
    """Simple AI client that returns a canned response without network calls."""

    async def strong_chat(
        self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]] | None = None
    ) -> Tuple[Any, Any]:
        response = {"content": "This is a dummy response."}
        return type("Message", (), response), None

    async def weak_chat(
        self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]] | None = None
    ) -> Tuple[Any, Any]:
        response = {"content": "This is a dummy response."}
        return type("Message", (), response), None
