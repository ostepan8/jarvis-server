from __future__ import annotations

import asyncio
import os
from typing import Optional, Tuple

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

    async def speak(
        self, text: str, voice_id: Optional[str] = None
    ) -> None:  # noqa: D401
        """Convert ``text`` to speech and play it.

        If the provided/default voice is unauthorized (403), attempt to
        discover an available voice from the account and retry once.
        """
        tracker = get_tracker()
        voice = voice_id or self.default_voice
        try:
            audio_bytes, used_voice, content_type = await self._synthesize(text, voice)
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
                        audio_bytes, used_voice, content_type = await self._synthesize(
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

        # Play audio - handle MP3 format differently
        is_mp3 = "audio/mpeg" in content_type or "audio/mp3" in content_type
        if is_mp3:
            if tracker and tracker.enabled:
                async with tracker.timer(
                    "audio_playback",
                    metadata={
                        "engine": "elevenlabs_tts",
                        "voice": used_voice,
                        "format": "mp3",
                    },
                ):
                    await self._play_mp3_using_sdk(audio_bytes)
            else:
                await self._play_mp3_using_sdk(audio_bytes)
        else:
            # WAV or other format - use standard playback
            if tracker and tracker.enabled:
                async with tracker.timer(
                    "audio_playback",
                    metadata={"engine": "elevenlabs_tts", "voice": used_voice},
                ):
                    await asyncio.to_thread(play_audio_bytes, audio_bytes)
            else:
                await asyncio.to_thread(play_audio_bytes, audio_bytes)

    async def _synthesize(self, text: str, voice: str) -> Tuple[bytes, str, str]:
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

        # Request WAV format explicitly (pcm_44100 returns raw PCM, pcm_22050 is lower quality)
        # If pcm_44100 doesn't work, try removing output_format or using mp3_44100_128
        output_format = os.getenv("ELEVEN_OUTPUT_FORMAT", "pcm_44100")
        body = {"text": text, "model_id": model_id, "output_format": output_format}
        if voice_settings:
            body["voice_settings"] = voice_settings

        response = await self.client.post(
            url,
            headers=headers,
            json=body,
        )
        response.raise_for_status()
        audio_bytes = response.content
        content_type = response.headers.get("Content-Type", "")

        # Validate format
        is_mp3 = "audio/mpeg" in content_type or "audio/mp3" in content_type
        is_wav = "audio/wav" in content_type or "audio/x-wav" in content_type

        if is_wav:
            # Verify WAV format by checking RIFF header
            if not audio_bytes.startswith(b"RIFF"):
                # If output_format was pcm_44100, it might return raw PCM without WAV header
                # In that case, we might need to wrap it, but for now just warn
                self.logger.log(
                    "WARNING",
                    "WAV content type but no RIFF header",
                    "Audio might be raw PCM format",
                )
        elif is_mp3:
            # MP3 format - log and handle in speak method
            self.logger.log(
                "INFO",
                "ElevenLabs returned MP3 format",
                "Will use ElevenLabs SDK play function for MP3 playback",
            )
        elif content_type:
            # Unknown format - log warning but try to play anyway
            self.logger.log(
                "WARNING",
                "Unexpected audio format from ElevenLabs",
                f"Content-Type: {content_type}. Attempting playback anyway.",
            )

        return audio_bytes, voice, content_type

    async def _play_mp3_using_sdk(self, mp3_bytes: bytes) -> None:
        """Play MP3 audio using ElevenLabs SDK if available, or convert using pydub."""
        try:
            from elevenlabs import play
            import io

            # Try using ElevenLabs SDK's play function with bytes
            # The play function may accept bytes directly, or we can use BytesIO
            audio_stream = io.BytesIO(mp3_bytes)
            await asyncio.to_thread(play, audio_stream)
        except (ImportError, Exception) as e:
            # Fallback: try to convert MP3 to WAV using pydub
            try:
                from pydub import AudioSegment
                import io as io_module
                from ...utils.audio import play_audio_bytes

                audio = AudioSegment.from_mp3(io_module.BytesIO(mp3_bytes))
                wav_buffer = io_module.BytesIO()
                audio.export(wav_buffer, format="wav")
                await asyncio.to_thread(play_audio_bytes, wav_buffer.getvalue())
            except ImportError:
                raise ImportError(
                    "Either elevenlabs SDK (pip install elevenlabs) or pydub "
                    "(pip install pydub) is required to play MP3 audio. "
                    f"Original error: {e}"
                )
            except Exception as conv_error:
                self.logger.log(
                    "ERROR",
                    "Failed to play or convert MP3 audio",
                    f"Error: {conv_error}",
                )
                raise

    async def _select_fallback_voice(self) -> Optional[str]:
        """Query ElevenLabs for available voices and pick the first one."""
        try:
            headers = {"xi-api-key": self.api_key}
            resp = await self.client.get(
                "https://api.elevenlabs.io/v1/voices", headers=headers
            )
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
