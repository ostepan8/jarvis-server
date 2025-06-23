# speech_to_text.py
from __future__ import annotations

from abc import ABC, abstractmethod


class SpeechToTextEngine(ABC):
    """Interface for speech-to-text engines."""

    @abstractmethod
    async def listen_for_speech(self, timeout: float = 5.0) -> str:
        """Listen for speech and return the transcribed text."""
        raise NotImplementedError
