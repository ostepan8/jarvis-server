from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Tuple


class BaseAIClient(ABC):
    """Abstract base class defining the interface for chat-based AI models."""

    @abstractmethod
    async def chat(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]) -> Tuple[Any, Any]:
        """Send chat messages with optional tools and return response and tool calls."""
        raise NotImplementedError
