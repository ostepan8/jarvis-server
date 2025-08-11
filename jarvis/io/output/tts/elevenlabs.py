from __future__ import annotations

import asyncio
import os
from typing import Optional

import httpx

from ...utils.audio import play_audio_bytes
from ....logger import JarvisLogger
from .base import TextToSpeechEngine
from ....performance import get_tracker


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
        headers = {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json",
            "Accept": "audio/wav",
        }
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice}"
        tracker = get_tracker()
        try:
            if tracker and tracker.enabled:
                async with tracker.timer(
                    "tts_synthesis",
                    metadata={"engine": "elevenlabs_tts", "voice": voice},
                ):
                    response = await self.client.post(
                        url,
                        headers=headers,
                        params={"output_format": "pcm"},
                        json={"text": text},
                    )
                    response.raise_for_status()
                    audio_bytes = response.content
            else:
                response = await self.client.post(
                    url,
                    headers=headers,
                    params={"output_format": "pcm"},
                    json={"text": text},
                )
                response.raise_for_status()
                audio_bytes = response.content

            content_type = response.headers.get("Content-Type", "")
            if "audio/wav" not in content_type and "audio/x-wav" not in content_type:
                raise ValueError(f"Unexpected content type: {content_type}")
            if not audio_bytes.startswith(b"RIFF"):
                raise ValueError("ElevenLabs TTS did not return WAV/PCM audio")

            if tracker and tracker.enabled:
                async with tracker.timer(
                    "audio_playback", metadata={"engine": "elevenlabs_tts"}
                ):
                    await asyncio.to_thread(play_audio_bytes, audio_bytes)
            else:
                await asyncio.to_thread(play_audio_bytes, audio_bytes)
        except Exception as exc:  # pragma: no cover - network / playback errors
            self.logger.log("ERROR", "ElevenLabs TTS error", str(exc))
