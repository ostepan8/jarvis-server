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
        self.intent_map = {"dummy_cap": self.echo}

    @property
    def capabilities(self):
        return {"dummy_cap"}

    async def echo(self, **kwargs):
        return {"echo": kwargs}


@pytest.mark.asyncio
async def test_protocol_execution():
    network = AgentNetwork()
    agent = DummyAgent()
    network.register_agent(agent)
    await network.start()

    logger = JarvisLogger()
    executor = ProtocolExecutor(network, logger)

    step = ProtocolStep(intent="dummy_cap", parameters={"msg": "Hello {name}"})
    proto = Protocol(id="1", name="test", description="", arguments={"name": "world"}, steps=[step])

    result = await executor.execute(proto, {"name": "Jarvis"})
    await network.stop()

    assert result["dummy_cap"]["echo"] == {"name": "Jarvis", "msg": "Hello Jarvis"}
