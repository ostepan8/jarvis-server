from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Tuple


class BaseAIClient(ABC):
    """Abstract base class defining the interface for chat-based AI models."""

    @abstractmethod
    async def strong_chat(
        self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]] | None = None
    ) -> Tuple[Any, Any]:
        """High quality chat using more capable (and expensive) models."""
        raise NotImplementedError

    @abstractmethod
    async def weak_chat(
        self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]] | None = None
    ) -> Tuple[Any, Any]:
        """Lower quality chat for lightweight tasks."""
        raise NotImplementedError
