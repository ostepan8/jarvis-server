import asyncio
import pytest

from jarvis.agents.agent_network import AgentNetwork
from jarvis.agents.memory_agent import MemoryAgent
from jarvis.agents.nlu_agent import NLUAgent
from jarvis.agents.base import NetworkAgent
from jarvis.main_jarvis import JarvisSystem
from jarvis.config import JarvisConfig
from jarvis.ai_clients.base import BaseAIClient


class DummyMemoryService:
    def __init__(self):
        self.added = []
        self.queries = []
        self.query_calls = []

    async def add_memory(self, text, metadata=None):
        self.added.append((text, metadata))
        return "mem1"

    async def similarity_search(self, query, top_k=3):
        self.queries.append((query, top_k))
        return [{"text": q[0], "metadata": {}} for q in self.added][:top_k]

    async def query_memory(self, memory_id=None, metadata=None, limit=None):
        self.query_calls.append((memory_id, metadata, limit))
        if not self.added:
            return []
        text, meta = self.added[0]
        result = {"id": "mem1", "text": text, "metadata": meta}
        if memory_id and memory_id != "mem1":
            return []
        if metadata:
            for k, v in metadata.items():
                if meta.get(k) != v:
                    return []
        return [result]


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
    assert results == []
    assert service.queries == [("hello", 1)]

    # Test query_memory by id and metadata
    query_by_id = await user.query_memory(memory_id=mem_id)
    assert query_by_id and query_by_id[0]["text"] == "hello"
    assert service.query_calls[-1] == (mem_id, None, None)

    query_by_meta = await user.query_memory(metadata={"foo": "bar"})
    assert query_by_meta and query_by_meta[0]["metadata"]["foo"] == "bar"
    assert service.query_calls[-1] == (None, {"foo": "bar"}, None)

    await network.stop()


class DummyAIClient(BaseAIClient):
    def __init__(self, output: str):
        self.output = output

    async def strong_chat(self, messages, tools=None):
        return (type("Msg", (), {"content": self.output}), None)

    async def weak_chat(self, messages, tools=None):
        return await self.strong_chat(messages, tools)


class DummyVectorMemoryService(DummyMemoryService):
    pass


@pytest.mark.asyncio
async def test_process_request_unknown_intent_memory():
    output = '{"intent": "remember", "capability": "store_memory", "args": {"memory_data": "hello"}}'
    ai_client = DummyAIClient(output)
    jarvis = JarvisSystem(JarvisConfig())
    service = DummyVectorMemoryService()
    jarvis.vector_memory = service
    jarvis.memory_agent = MemoryAgent(service, jarvis.logger)
    jarvis.nlu_agent = NLUAgent(ai_client, jarvis.logger)
    jarvis.network = AgentNetwork(jarvis.logger)
    jarvis.network.register_agent(jarvis.memory_agent)
    jarvis.network.register_agent(jarvis.nlu_agent)
    await jarvis.network.start()

    await jarvis.process_request("remember this", "UTC")

    await jarvis.network.stop()
    assert service.added == [("hello", {})]
