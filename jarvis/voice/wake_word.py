from __future__ import annotations

from abc import ABC, abstractmethod


class WakeWordListener(ABC):
    """Interface for wake word detection engines."""

    @abstractmethod
    async def wait_for_wake_word(self) -> None:
        """Block until the configured wake word is detected."""
        raise NotImplementedError
