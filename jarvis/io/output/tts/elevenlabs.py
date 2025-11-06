from __future__ import annotations

import asyncio
import os
from typing import Optional, Tuple
import os

import httpx

from ...utils.audio import play_audio_bytes
from ....logging import JarvisLogger
from .base import TextToSpeechEngine
from ....utils.performance import get_tracker


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
        """Convert ``text`` to speech and play it.

        If the provided/default voice is unauthorized (403), attempt to
        discover an available voice from the account and retry once.
        """
        tracker = get_tracker()
        voice = voice_id or self.default_voice
        try:
            audio_bytes, used_voice = await self._synthesize(text, voice)
        except httpx.HTTPStatusError as exc:  # pragma: no cover - network / API errors
            if exc.response is not None and exc.response.status_code in (401, 403, 404):
                # Try to select a fallback voice available to this account
                try:
                    fallback_voice = await self._select_fallback_voice()
                    if fallback_voice and fallback_voice != voice:
                        self.logger.log(
                            "INFO",
                            "ElevenLabs fallback voice",
                            f"Using '{fallback_voice}' after 403 for '{voice}'",
                        )
                        audio_bytes, used_voice = await self._synthesize(
                            text, fallback_voice
                        )
                    else:
                        raise
                except Exception as inner_exc:  # pragma: no cover
                    self.logger.log(
                        "ERROR", "ElevenLabs TTS fallback failed", str(inner_exc)
                    )
                    raise
            else:
                raise
        except Exception as exc:  # pragma: no cover - other errors
            self.logger.log("ERROR", "ElevenLabs TTS error", str(exc))
            raise

        # Play audio
        if tracker and tracker.enabled:
            async with tracker.timer(
                "audio_playback", metadata={"engine": "elevenlabs_tts", "voice": used_voice}
            ):
                await asyncio.to_thread(play_audio_bytes, audio_bytes)
        else:
            await asyncio.to_thread(play_audio_bytes, audio_bytes)

    async def _synthesize(self, text: str, voice: str) -> Tuple[bytes, str]:
        headers = {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json",
            "Accept": "audio/wav",
        }
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice}"
        model_id = os.getenv("ELEVEN_MODEL_ID", "eleven_multilingual_v2")
        # Optional voice settings
        stability = os.getenv("ELEVEN_STABILITY")
        similarity = os.getenv("ELEVEN_SIMILARITY_BOOST")
        voice_settings = {}
        if stability is not None:
            try:
                voice_settings["stability"] = float(stability)
            except Exception:
                pass
        if similarity is not None:
            try:
                voice_settings["similarity_boost"] = float(similarity)
            except Exception:
                pass

        body = {"text": text, "model_id": model_id}
        if voice_settings:
            body["voice_settings"] = voice_settings

        response = await self.client.post(
            url,
            headers=headers,
            # PCM WAV content; model and settings included for improved quality
            json=body,
        )
        response.raise_for_status()
        audio_bytes = response.content

        content_type = response.headers.get("Content-Type", "")
        if "audio/wav" not in content_type and "audio/x-wav" not in content_type:
            raise ValueError(f"Unexpected content type: {content_type}")
        if not audio_bytes.startswith(b"RIFF"):
            raise ValueError("ElevenLabs TTS did not return WAV/PCM audio")
        return audio_bytes, voice

    async def _select_fallback_voice(self) -> Optional[str]:
        """Query ElevenLabs for available voices and pick the first one."""
        try:
            headers = {"xi-api-key": self.api_key}
            resp = await self.client.get("https://api.elevenlabs.io/v1/voices", headers=headers)
            resp.raise_for_status()
            data = resp.json()
            voices = data.get("voices") or []
            # Try a small preference list; fall back to first
            preferred = {"Rachel", "Bella", "Adam", "George", "Clyde", "Elli"}
            for v in voices:
                name = v.get("name")
                if name in preferred:
                    return v.get("voice_id")
            if voices:
                return voices[0].get("voice_id")
            return None
        except Exception as exc:  # pragma: no cover
            self.logger.log("ERROR", "Failed to list ElevenLabs voices", str(exc))
            return None
