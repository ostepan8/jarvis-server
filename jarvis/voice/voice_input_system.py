from __future__ import annotations

import asyncio

from typing import Awaitable, Callable, Optional

from ..io.base import ConsoleInput, InputHandler


class VoiceInputSystem:
    """Coordinator that connects a wake word listener and a TTS engine.

    Architecture:

    WakeWordListener -> VoiceInputSystem -> TextToSpeechEngine
                             ^                    |
                             |                    v
                           InputHandler ----------"
    """

    def __init__(
        self,
        wake_listener: WakeWordListener,
        tts_engine: TextToSpeechEngine,
        input_handler: InputHandler | None = None,
    ) -> None:
        self.wake_listener = wake_listener
        self.tts_engine = tts_engine
        self.input_handler = input_handler or ConsoleInput()
        self._running = False

    async def listen_and_respond(
        self,
        handler: Optional[Callable[[str], Awaitable[str]]] = None,
    ) -> None:
        """Wait for the wake word then prompt the user and speak the response."""
        await self.wake_listener.wait_for_wake_word()
        text = await self.input_handler.get_input("Speak> ")
        if handler is not None:
            text = await handler(text)
        await self.tts_engine.speak(text)

    async def run_forever(
        self,
        handler: Optional[Callable[[str], Awaitable[str]]] = None,
    ) -> None:
        """Continuously listen for the wake word until cancelled."""
        self._running = True
        while self._running:
            await self.listen_and_respond(handler)
            await asyncio.sleep(0.1)

    def stop(self) -> None:
        """Stop the run loop."""
        self._running = False

