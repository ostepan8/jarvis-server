from __future__ import annotations

import asyncio
import io
import os

import sounddevice as sd
import soundfile as sf
import openai

from ..logger import JarvisLogger
from ..interfaces import TextToSpeechEngine


class OpenAITTSEngine(TextToSpeechEngine):
    """Text to speech engine using OpenAI's TTS API."""

    def __init__(
        self,
        model: str = "tts-1",
        voice: str = "alloy",
        api_key: str | None = None,
        *,
        logger: JarvisLogger | None = None,
    ) -> None:
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY is required")
        self.logger = logger or JarvisLogger()
        self.model = model
        self.voice = voice
        self.client = openai.AsyncOpenAI(api_key=self.api_key)

    async def speak(self, text: str) -> None:  # noqa: D401 - interface impl
        """Convert ``text`` to speech and play it asynchronously."""

        try:
            response = await self.client.audio.speech.create(
                model=self.model, voice=self.voice, input=text
            )
            audio_bytes = await response.read()
            await asyncio.to_thread(self._play_audio, audio_bytes)
        except Exception as exc:  # pragma: no cover - network errors
            self.logger.log("ERROR", "OpenAI TTS error", str(exc))

    def _play_audio(self, audio_bytes: bytes) -> None:
        with sf.SoundFile(io.BytesIO(audio_bytes)) as f:
            data = f.read(dtype="float32")
            sd.play(data, f.samplerate, blocking=False)

