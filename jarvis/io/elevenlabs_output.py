from __future__ import annotations

import asyncio
import io
import os
from typing import Optional

import httpx
import sounddevice as sd
import soundfile as sf

from .base import OutputHandler
from ..logger import JarvisLogger


class ElevenLabsOutput(OutputHandler):
    """Output handler that uses Eleven Labs text-to-speech to speak messages."""

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

    async def send_output(self, message: str) -> None:  # noqa: D401 - override
        """Send output by speaking it using Eleven Labs."""
        await self.speak(message)

    async def speak(self, text: str, voice_id: Optional[str] = None) -> None:
        """Convert ``text`` to speech using Eleven Labs and play it asynchronously."""
        voice = voice_id or self.default_voice
        headers = {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json",
        }
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice}"
        try:
            response = await self.client.post(url, headers=headers, json={"text": text})
            response.raise_for_status()
            audio_bytes = response.content
            await asyncio.to_thread(self._play_audio, audio_bytes)
        except Exception as exc:  # pragma: no cover - network / playback errors
            self.logger.log("ERROR", "ElevenLabsOutput error", str(exc))

    def _play_audio(self, audio_bytes: bytes) -> None:
        """Play audio bytes using sounddevice without blocking the event loop."""
        with sf.SoundFile(io.BytesIO(audio_bytes)) as f:
            data = f.read(dtype="float32")
            sd.play(data, f.samplerate, blocking=False)


if __name__ == "__main__":  # pragma: no cover - manual demonstration
    async def _demo() -> None:
        output = ElevenLabsOutput(default_voice="ErXwobaYiN019PkySvjV")
        await output.speak("Hello from Eleven Labs")
        await asyncio.sleep(1)  # allow playback to start
        await output.close()

    asyncio.run(_demo())

