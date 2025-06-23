from __future__ import annotations

from .base import TextToSpeechEngine


class MockTTSEngine(TextToSpeechEngine):
    """Mock TTS engine that records spoken text."""

    def __init__(self) -> None:
        self.spoken: list[str] = []

    async def speak(self, text: str) -> None:
        self.spoken.append(text)
