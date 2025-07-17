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


class CapAgent(NetworkAgent):
    def __init__(self, name):
        super().__init__(name)

    @property
    def capabilities(self):
        return {"foo"}

    async def _handle_capability_request(self, message):
        pass


def test_add_remove_capabilities():
    network = AgentNetwork()
    agent = CapAgent("cap")
    network.register_agent(agent, include_capabilities=False)
    assert "foo" not in network.capability_registry

    network.add_agent_capabilities(agent)
    assert network.capability_registry.get("foo") == ["cap"]

    network.remove_agent_capabilities(agent)
    assert "foo" not in network.capability_registry


class NightCapAgent(NetworkAgent):
    def __init__(self, name):
        super().__init__(name)

    @property
    def capabilities(self):
        return {"bar"}

    async def _handle_capability_request(self, message):
        pass


def test_register_night_agent():
    network = AgentNetwork()
    agent = NightCapAgent("night")
    network.register_night_agent(agent)
    assert agent.name in network.night_agents
    assert "bar" not in network.capability_registry
    assert network.night_capability_registry.get("bar") == ["night"]

    network.add_agent_capabilities(agent)
    assert network.capability_registry.get("bar") == ["night"]

    network.remove_agent_capabilities(agent)
    assert "bar" not in network.capability_registry
