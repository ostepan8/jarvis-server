import asyncio
import pytest

from jarvis.agents.agent_network import AgentNetwork
from jarvis.agents.base import NetworkAgent
from jarvis.protocols import Protocol, ProtocolStep
from jarvis.protocols.executor import ProtocolExecutor
from jarvis.logging import JarvisLogger


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

    step = ProtocolStep(agent="dummy", function="dummy_cap", parameters={"msg": "Hello {name}"})
    proto = Protocol(id="1", name="test", description="", arguments={"name": "world"}, steps=[step])

    result = await executor.run_protocol(proto, {"name": "Jarvis"})
    await network.stop()

    assert result["step_0_dummy_cap"]["echo"] == {"msg": "Hello {name}"}
