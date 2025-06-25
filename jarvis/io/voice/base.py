from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator


class VoiceInputInterface(ABC):
    """Abstract base for microphone listeners yielding transcription chunks."""

    @abstractmethod
    async def listen(self) -> AsyncIterator[str]:
        """Yield transcribed text chunks until a final result is produced."""
        raise NotImplementedError
