import asyncio
import pytest

from jarvis.agents.agent_network import AgentNetwork
from jarvis.agents.memory_agent import MemoryAgent
from jarvis.agents.base import NetworkAgent


class DummyMemoryService:
    def __init__(self):
        self.added = []
        self.queries = []

    async def add_memory(self, text, metadata=None):
        self.added.append((text, metadata))
        return "mem1"

    async def similarity_search(self, query, top_k=3):
        self.queries.append((query, top_k))
        return [{"text": q[0], "metadata": {}} for q in self.added][:top_k]


class DummyAgent(NetworkAgent):
    def __init__(self, name="dummy"):
        super().__init__(name)

    @property
    def capabilities(self):
        return set()

    async def _handle_capability_request(self, message):
        pass

    async def _handle_capability_response(self, message):
        pass


@pytest.mark.asyncio
async def test_memory_agent_routing():
    network = AgentNetwork()
    service = DummyMemoryService()
    memory_agent = MemoryAgent(service)
    user = DummyAgent()

    network.register_agent(memory_agent)
    network.register_agent(user)

    await network.start()

    mem_id = await user.store_memory("hello", {"foo": "bar"})
    assert mem_id == "mem1"
    assert service.added == [("hello", {"foo": "bar"})]

    results = await user.search_memory("hello", top_k=1)
    assert results and results[0]["text"] == "hello"
    assert service.queries == [("hello", 1)]

    await network.stop()
