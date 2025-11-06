from __future__ import annotations

import asyncio
import os

import openai

from ...utils.audio import play_audio_bytes
from ....logging import JarvisLogger
from .base import TextToSpeechEngine
from ....utils.performance import get_tracker


class OpenAITTSEngine(TextToSpeechEngine):
    """Text-to-speech engine using OpenAI's TTS API."""

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
        tracker = get_tracker()
        try:
            # Request audio from OpenAI; SDK may return bytes or a stream-like object
            if tracker and tracker.enabled:
                async with tracker.timer(
                    "tts_synthesis",
                    metadata={
                        "engine": "openai_tts",
                        "model": self.model,
                        "voice": self.voice,
                    },
                ):
                    response = await self.client.audio.speech.create(
                        model=self.model, voice=self.voice, input=text
                    )
            else:
                response = await self.client.audio.speech.create(
                    model=self.model, voice=self.voice, input=text
                )

            # Normalize various SDK response shapes to raw bytes
            audio_bytes = None
            if isinstance(response, (bytes, bytearray)):
                audio_bytes = bytes(response)
            elif hasattr(response, "read"):
                maybe = response.read()
                if asyncio.iscoroutine(maybe):
                    audio_bytes = await maybe
                else:
                    audio_bytes = maybe
            elif hasattr(response, "content"):
                audio_bytes = response.content  # type: ignore[attr-defined]
            elif hasattr(response, "data"):
                audio_bytes = response.data  # type: ignore[attr-defined]
            else:  # Fallback: try to_bytes()
                try:
                    audio_bytes = response.to_bytes()  # type: ignore[attr-defined]
                except Exception:
                    pass

            if not audio_bytes:
                raise RuntimeError("OpenAI TTS returned no audio bytes")

            if tracker and tracker.enabled:
                async with tracker.timer(
                    "audio_playback", metadata={"engine": "openai_tts"}
                ):
                    await asyncio.to_thread(play_audio_bytes, audio_bytes)
            else:
                await asyncio.to_thread(play_audio_bytes, audio_bytes)
        except Exception as exc:  # pragma: no cover - network errors
            self.logger.log("ERROR", "OpenAI TTS error", str(exc))
