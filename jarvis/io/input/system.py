from __future__ import annotations

import asyncio
from typing import Awaitable, Callable, Optional

from .wakeword.base import WakeWordListener
from .transcription.base import SpeechToTextEngine
from ..output.tts.base import TextToSpeechEngine


class VoiceInputSystem:
    """Coordinate wake word detection, speech recognition and TTS."""

    def __init__(
        self,
        wake_listener: WakeWordListener,
        stt_engine: SpeechToTextEngine,
        tts_engine: TextToSpeechEngine,
    ) -> None:
        self.wake_listener = wake_listener
        self.stt_engine = stt_engine
        self.tts_engine = tts_engine
        self._running = False

    async def listen_and_respond(
        self,
        handler: Optional[Callable[[str], Awaitable[str]]] = None,
    ) -> None:
        """Wait for the wake word, then listen for speech and respond."""
        from ...utils.performance import PerfTracker

        tracker = PerfTracker()
        tracker.start()
        try:
            async with tracker.timer(
                "wake_word_to_stt",
                metadata={"listener": type(self.wake_listener).__name__},
            ):
                await self.wake_listener.wait_for_wake_word()

            logger = getattr(self.stt_engine, "logger", None) or getattr(
                self.tts_engine, "logger", None
            )
            if logger:
                logger.log("DEBUG", "Wake word detected, listening for speech")

            async with tracker.timer(
                "stt",
                metadata={"engine": type(self.stt_engine).__name__},
            ):
                text = await self.stt_engine.listen_for_speech(timeout=10.0)
            if not text:
                async with tracker.timer(
                    "tts", metadata={"engine": type(self.tts_engine).__name__}
                ):
                    await self.tts_engine.speak("I didn't catch that, sir.")
                return

            if logger:
                logger.log("DEBUG", "Speech recognized", {"text": text})

            if handler is not None:
                async with tracker.timer("handler"):
                    response = await handler(text)
            else:
                response = f"I heard: {text}"

            async with tracker.timer(
                "tts", metadata={"engine": type(self.tts_engine).__name__}
            ):
                await self.tts_engine.speak(response)

        except Exception as exc:
            logger = getattr(self.stt_engine, "logger", None) or getattr(
                self.tts_engine, "logger", None
            )
            if logger:
                logger.log("ERROR", "Error in listen_and_respond", {"error": str(exc)})
            try:
                await self.tts_engine.speak("I'm having technical difficulties, sir.")
            except Exception:
                pass
        finally:
            tracker.stop()
            tracker.save()
            logger = getattr(self.stt_engine, "logger", None) or getattr(
                self.tts_engine, "logger", None
            )
            if logger:
                logger.log("DEBUG", "Performance summary", tracker.summary())

    async def run_forever(
        self,
        handler: Optional[Callable[[str], Awaitable[str]]] = None,
    ) -> None:
        """Continuously listen for the wake word until cancelled."""
        self._running = True
        consecutive_errors = 0
        max_consecutive_errors = 5

        logger = getattr(self.stt_engine, "logger", None) or getattr(
            self.tts_engine, "logger", None
        )
        while self._running:
            try:
                await self.listen_and_respond(handler)
                consecutive_errors = 0
            except KeyboardInterrupt:
                if logger:
                    logger.log("INFO", "Voice system stopped by user")
                break
            except Exception as exc:
                consecutive_errors += 1
                if logger:
                    logger.log(
                        "ERROR",
                        f"Voice system error ({consecutive_errors}/{max_consecutive_errors})",
                        {"error": str(exc)},
                    )
                if consecutive_errors >= max_consecutive_errors:
                    if logger:
                        logger.log(
                            "ERROR",
                            "Too many consecutive errors, stopping voice system",
                        )
                    break
                await asyncio.sleep(2.0)

    def stop(self) -> None:
        """Stop the run loop."""
        self._running = False
