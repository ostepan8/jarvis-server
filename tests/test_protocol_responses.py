import asyncio
import pytest

from jarvis.core import JarvisSystem
from jarvis.core import JarvisConfig
from jarvis.protocols import Protocol, ProtocolStep, ProtocolResponse, ResponseMode


class DummyAIClient:
    def __init__(self):
        self.messages = None

    async def strong_chat(self, messages, tools=None):
        self.messages = messages
        return type("Msg", (), {"content": "AI reply"}), None

    async def weak_chat(self, messages, tools=None):
        return await self.strong_chat(messages, tools)


class DummyChatAgent:
    def __init__(self):
        self.ai_client = DummyAIClient()


@pytest.mark.asyncio
async def test_static_response():
    jarvis = JarvisSystem(JarvisConfig())
    jarvis.chat_agent = DummyChatAgent()

    proto = Protocol(
        id="1",
        name="lights_on",
        description="",
        steps=[ProtocolStep(agent="a", function="f")],
        response=ProtocolResponse(mode=ResponseMode.STATIC, phrases=["Lights on {room}"]),
    )
    resp = await jarvis._format_protocol_response(proto, {"step_0_f": {}}, {"room": "kitchen"})
    assert resp == "Lights on kitchen"


@pytest.mark.asyncio
async def test_ai_response():
    jarvis = JarvisSystem(JarvisConfig())
    dummy = DummyChatAgent()
    jarvis.chat_agent = dummy

    proto = Protocol(
        id="2",
        name="ai_proto",
        description="",
        steps=[ProtocolStep(agent="a", function="f")],
        response=ProtocolResponse(mode=ResponseMode.AI, prompt="Say hi to {name}"),
    )

    resp = await jarvis._format_protocol_response(proto, {}, {"name": "Tony"})
    assert "Say hi to Tony" in dummy.ai_client.messages[0]["content"]
    assert resp == "AI reply"

