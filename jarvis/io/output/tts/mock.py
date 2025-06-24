from __future__ import annotations

from .base import TextToSpeechEngine


class MockTTSEngine(TextToSpeechEngine):
    """Mock TTS engine that records spoken text."""

    def __init__(self) -> None:
        self.spoken: list[str] = []

    async def speak(self, text: str) -> None:
        from ....performance import get_tracker

        tracker = get_tracker()
        if tracker and tracker.enabled:
            async with tracker.timer(
                "tts_synthesis", metadata={"engine": "mock_tts"}
            ):
                # simply record the text without real synthesis
                self.spoken.append(text)
        else:
            self.spoken.append(text)
