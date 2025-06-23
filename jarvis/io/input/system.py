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
        from ...performance import PerfTracker

        tracker = PerfTracker()
        tracker.start()
        try:
            async with tracker.timer("wake_word_to_stt"):
                await self.wake_listener.wait_for_wake_word()
            print("Wake word detected! Listening...")

            async with tracker.timer("stt"):
                text = await self.stt_engine.listen_for_speech(timeout=10.0)
            if not text:
                async with tracker.timer("tts"):
                    await self.tts_engine.speak("I didn't catch that, sir.")
                return

            print(f"Heard: {text}")

            if handler is not None:
                async with tracker.timer("handler"):
                    response = await handler(text)
            else:
                response = f"I heard: {text}"

            async with tracker.timer("tts"):
                await self.tts_engine.speak(response)

        except Exception as exc:
            print(f"Error in listen_and_respond: {exc}")
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
                logger.log("INFO", "Performance summary", tracker.summary())
            else:
                print("Performance summary:", tracker.summary())

    async def run_forever(
        self,
        handler: Optional[Callable[[str], Awaitable[str]]] = None,
    ) -> None:
        """Continuously listen for the wake word until cancelled."""
        self._running = True
        consecutive_errors = 0
        max_consecutive_errors = 5

        while self._running:
            try:
                await self.listen_and_respond(handler)
                consecutive_errors = 0
            except KeyboardInterrupt:
                print("Voice system stopped by user")
                break
            except Exception as exc:
                consecutive_errors += 1
                print(
                    f"Voice system error ({consecutive_errors}/{max_consecutive_errors}): {exc}"
                )
                if consecutive_errors >= max_consecutive_errors:
                    print("Too many consecutive errors, stopping voice system")
                    break
                await asyncio.sleep(2.0)

    def stop(self) -> None:
        """Stop the run loop."""
        self._running = False
