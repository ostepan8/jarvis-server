import asyncio
import pytest

from jarvis.agents.agent_network import AgentNetwork
from jarvis.agents.base import NetworkAgent

class DummyAgent(NetworkAgent):
    def __init__(self, name):
        super().__init__(name)
        self.received = asyncio.Queue()

    @property
    def capabilities(self):
        return set()

    async def _handle_capability_request(self, message):
        await self.received.put(message)

@pytest.mark.asyncio
async def test_message_routing():
    network = AgentNetwork()
    sender = DummyAgent("sender")
    receiver = DummyAgent("receiver")
    network.register_agent(sender)
    network.register_agent(receiver)

    await network.start()
    await sender.send_message("receiver", "capability_request", {"foo": "bar"}, "1")
    msg = await asyncio.wait_for(receiver.received.get(), timeout=0.5)
    await network.stop()

    assert msg.content == {"foo": "bar"}
    assert msg.from_agent == "sender"
