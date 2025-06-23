from __future__ import annotations

import asyncio

from ..interfaces import WakeWordListener, TextToSpeechEngine


class MockWakeWordListener(WakeWordListener):
    """Mock listener that triggers immediately for tests."""

    def __init__(self, delay: float = 0.0) -> None:
        self.delay = delay
        self.triggered = False

    async def wait_for_wake_word(self) -> None:
        await asyncio.sleep(self.delay)
        self.triggered = True


class MockTTSEngine(TextToSpeechEngine):
    """Mock TTS engine that records spoken text."""

    def __init__(self) -> None:
        self.spoken: list[str] = []

    async def speak(self, text: str) -> None:
        self.spoken.append(text)

