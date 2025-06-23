from __future__ import annotations

from abc import ABC, abstractmethod


class TextToSpeechEngine(ABC):
    """Interface for text-to-speech engines."""

    @abstractmethod
    async def speak(self, text: str) -> None:
        """Speak the given ``text`` asynchronously."""
        raise NotImplementedError
