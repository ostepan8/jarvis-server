import asyncio
import pytest

from jarvis.agents.agent_network import AgentNetwork
from jarvis.agents.base import NetworkAgent
from jarvis.protocols import Protocol, ProtocolStep
from jarvis.protocols.executor import ProtocolExecutor
from jarvis.logger import JarvisLogger


class DummyAgent(NetworkAgent):
    def __init__(self):
        super().__init__("dummy")
        self.received = asyncio.Queue()

    @property
    def capabilities(self):
        return {"dummy_cap"}

    async def _handle_capability_request(self, message):
        await self.received.put(message)
        await self.send_capability_response(
            message.from_agent,
            {"echo": message.content.get("data")},
            message.request_id,
            message.id,
        )


@pytest.mark.asyncio
async def test_protocol_execution():
    network = AgentNetwork()
    agent = DummyAgent()
    network.register_agent(agent)
    await network.start()

    logger = JarvisLogger()
    executor = ProtocolExecutor(network, logger)

    step = ProtocolStep(intent="dummy_cap", parameters={"foo": "bar"})
    proto = Protocol(id="1", name="test", description="", steps=[step])

    result = await executor.execute(proto)
    await network.stop()

    assert result["dummy_cap"]["echo"] == {"foo": "bar"}
