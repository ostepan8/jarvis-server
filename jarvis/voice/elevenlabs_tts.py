from __future__ import annotations

from ..interfaces import TextToSpeechEngine
from ..io.elevenlabs_output import ElevenLabsOutput


class ElevenLabsTTSEngine(TextToSpeechEngine):
    """Text-to-speech engine that wraps :class:`ElevenLabsOutput`."""

    def __init__(self, default_voice: str) -> None:
        self._output = ElevenLabsOutput(default_voice)

    async def speak(self, text: str) -> None:  # noqa: D401 - interface impl
        """Speak ``text`` using ElevenLabs."""
        await self._output.speak(text)
