from __future__ import annotations

import asyncio
from typing import Awaitable, Callable, Optional

from .wake_word import WakeWordListener
from .text_to_speech import TextToSpeechEngine
from .speech_to_text import SpeechToTextEngine


class VoiceInputSystem:
    """Coordinator that connects wake word detection, speech recognition, and TTS.

    Architecture:
    WakeWordListener -> SpeechToTextEngine -> Handler -> TextToSpeechEngine
    """

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
        """Wait for wake word, then listen for speech and respond."""
        try:
            # 1. Wait for wake word
            await self.wake_listener.wait_for_wake_word()
            print("Wake word detected! Listening...")

            # 2. Listen for speech input
            text = await self.stt_engine.listen_for_speech(timeout=10.0)

            if not text:
                await self.tts_engine.speak("I didn't catch that, sir.")
                return

            print(f"Heard: {text}")

            # 3. Process the input
            if handler is not None:
                response = await handler(text)
            else:
                response = f"I heard: {text}"

            # 4. Speak the response
            await self.tts_engine.speak(response)

        except Exception as exc:
            print(f"Error in listen_and_respond: {exc}")
            # Try to give audio feedback about the error
            try:
                await self.tts_engine.speak("I'm having technical difficulties, sir.")
            except:
                pass  # If TTS also fails, just continue

    async def run_forever(
        self,
        handler: Optional[Callable[[str], Awaitable[str]]] = None,
    ) -> None:
        """Continuously listen for wake word until cancelled."""
        self._running = True
        consecutive_errors = 0
        max_consecutive_errors = 5

        while self._running:
            try:
                await self.listen_and_respond(handler)
                consecutive_errors = 0  # Reset error count on success

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

                # Wait a bit before retrying
                await asyncio.sleep(2.0)

    def stop(self) -> None:
        """Stop the run loop."""
        self._running = False
