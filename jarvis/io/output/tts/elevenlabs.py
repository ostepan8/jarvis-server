from __future__ import annotations

import asyncio
import os
from typing import Optional

import httpx

from ...utils.audio import play_audio_bytes
from ....logger import JarvisLogger
from .base import TextToSpeechEngine


class ElevenLabsTTSEngine(TextToSpeechEngine):
    """Text-to-speech engine using the ElevenLabs API."""

    def __init__(self, default_voice: str, logger: JarvisLogger | None = None) -> None:
        self.default_voice = default_voice
        self.logger = logger or JarvisLogger()
        self.api_key = os.getenv("ELEVEN_LABS_API_KEY")
        if not self.api_key:
            raise ValueError("ELEVEN_LABS_API_KEY environment variable is required")
        self.client = httpx.AsyncClient()

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self.client.aclose()

    async def speak(self, text: str, voice_id: Optional[str] = None) -> None:  # noqa: D401
        """Convert ``text`` to speech and play it."""
        voice = voice_id or self.default_voice
        headers = {"xi-api-key": self.api_key, "Content-Type": "application/json"}
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice}"
        try:
            response = await self.client.post(url, headers=headers, json={"text": text})
            response.raise_for_status()
            audio_bytes = response.content
            await asyncio.to_thread(play_audio_bytes, audio_bytes)
        except Exception as exc:  # pragma: no cover - network / playback errors
            self.logger.log("ERROR", "ElevenLabs TTS error", str(exc))
