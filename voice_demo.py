"""Example usage of the voice input system."""

import asyncio
import os
from dotenv import load_dotenv

from jarvis.voice import (
    VoiceInputSystem,
    PicovoiceWakeWordListener,
    ElevenLabsTTSEngine,
)

load_dotenv()


async def main() -> None:
    wake_listener = PicovoiceWakeWordListener(
        access_key=os.getenv("PICOVOICE_ACCESS_KEY"),
        keyword_paths=os.getenv("PICOVOICE_KEYWORD_PATHS", "").split(os.pathsep)
        if os.getenv("PICOVOICE_KEYWORD_PATHS")
        else None,
    )
    tts_engine = ElevenLabsTTSEngine(
        default_voice=os.getenv("ELEVEN_VOICE_ID", "ErXwobaYiN019PkySvjV")
    )
    system = VoiceInputSystem(wake_listener, tts_engine)
    await system.listen_and_respond()


if __name__ == "__main__":
    asyncio.run(main())

