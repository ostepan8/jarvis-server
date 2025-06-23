import asyncio
import pytest

from jarvis.io.input import VoiceInputSystem
from jarvis.io.input.wakeword import MockWakeWordListener
from jarvis.io.output.tts import MockTTSEngine
from jarvis.io.input.transcription.base import SpeechToTextEngine


class DummySTT(SpeechToTextEngine):
    async def listen_for_speech(self, timeout: float = 5.0) -> str:  # noqa: D401
        return "hello"


@pytest.mark.asyncio
async def test_voice_system_uses_mocks():
    wake = MockWakeWordListener()
    tts = MockTTSEngine()
    stt = DummySTT()
    system = VoiceInputSystem(wake, stt, tts)
    await system.listen_and_respond()
    assert wake.triggered
    assert tts.spoken == ["I heard: hello"]


@pytest.mark.asyncio
async def test_voice_system_handler_transforms_input():
    wake = MockWakeWordListener()
    tts = MockTTSEngine()
    stt = DummySTT()
    system = VoiceInputSystem(wake, stt, tts)

    async def handler(text: str) -> str:
        return text.upper()

    await system.listen_and_respond(handler)
    assert tts.spoken == ["HELLO"]

