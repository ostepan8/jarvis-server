import asyncio
import pytest

from jarvis.voice import VoiceInputSystem, MockWakeWordListener, MockTTSEngine
from jarvis.io.base import InputHandler
class DummyInput(InputHandler):
    async def get_input(self, prompt: str) -> str:
        return "hello"


@pytest.mark.asyncio
async def test_voice_system_uses_mocks():
    wake = MockWakeWordListener()
    tts = MockTTSEngine()
    system = VoiceInputSystem(wake, tts, DummyInput())
    await system.listen_and_respond()
    assert wake.triggered
    assert tts.spoken == ["hello"]


@pytest.mark.asyncio
async def test_voice_system_handler_transforms_input():
    wake = MockWakeWordListener()
    tts = MockTTSEngine()
    system = VoiceInputSystem(wake, tts, DummyInput())

    async def handler(text: str) -> str:
        return text.upper()

    await system.listen_and_respond(handler)
    assert tts.spoken == ["HELLO"]

