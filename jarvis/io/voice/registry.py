from __future__ import annotations

from typing import Callable, Dict, List

from .base import VoiceInputInterface


class VoiceInputRegistry:
    """Registry for named voice input listeners."""

    _registry: Dict[str, Callable[[], VoiceInputInterface]] = {}

    @classmethod
    def register(cls, name: str, factory: Callable[[], VoiceInputInterface]) -> None:
        cls._registry[name] = factory

    @classmethod
    def create(cls, name: str) -> VoiceInputInterface:
        if name not in cls._registry:
            raise KeyError(f"Unknown voice listener '{name}'")
        return cls._registry[name]()

    @classmethod
    def available(cls) -> List[str]:
        return list(cls._registry.keys())
