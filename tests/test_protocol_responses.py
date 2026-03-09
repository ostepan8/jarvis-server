import pytest

from jarvis.protocols import Protocol, ProtocolStep, ProtocolResponse, ResponseMode
from jarvis.protocols.runtime import ProtocolRuntime
from jarvis.agents.agent_network import AgentNetwork
from jarvis.logging import JarvisLogger


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

    @property
    def name(self):
        return "ChatAgent"

    @property
    def capabilities(self):
        return set()

    @property
    def description(self):
        return "Chat"

    def set_network(self, network):
        pass


@pytest.mark.asyncio
async def test_static_response():
    logger = JarvisLogger()
    network = AgentNetwork(logger)
    chat = DummyChatAgent()
    network.agents["ChatAgent"] = chat

    runtime = ProtocolRuntime(network, logger)

    proto = Protocol(
        id="1",
        name="lights_on",
        description="",
        steps=[ProtocolStep(agent="a", function="f")],
        response=ProtocolResponse(mode=ResponseMode.STATIC, phrases=["Lights on {room}"]),
    )
    resp = await runtime._format_protocol_response(proto, {"step_0_f": {}}, {"room": "kitchen"})
    assert resp == "Lights on kitchen"


@pytest.mark.asyncio
async def test_ai_response():
    logger = JarvisLogger()
    network = AgentNetwork(logger)
    chat = DummyChatAgent()
    network.agents["ChatAgent"] = chat

    runtime = ProtocolRuntime(network, logger)

    proto = Protocol(
        id="2",
        name="ai_proto",
        description="",
        steps=[ProtocolStep(agent="a", function="f")],
        response=ProtocolResponse(mode=ResponseMode.AI, prompt="Say hi to {name}"),
    )

    resp = await runtime._format_protocol_response(proto, {}, {"name": "Tony"})
    assert "Say hi to Tony" in chat.ai_client.messages[0]["content"]
    assert resp == "AI reply"
