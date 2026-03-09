import asyncio
import pytest
from unittest.mock import AsyncMock

from jarvis.agents.agent_network import AgentNetwork
from jarvis.agents.memory_agent import MemoryAgent
from jarvis.agents.nlu_agent import NLUAgent
from jarvis.agents.base import NetworkAgent
from jarvis.core import JarvisSystem
from jarvis.core import JarvisConfig
from jarvis.ai_clients.base import BaseAIClient
from jarvis.core.orchestrator import RequestOrchestrator
from jarvis.core.response_logger import ResponseLogger


class DummyMemoryService:
    def __init__(self):
        self.added = []
        self.queries = []
        self.query_calls = []

    async def add_memory(self, text, metadata=None, user_id=None):
        self.added.append((text, metadata, user_id))
        return "mem1"

    async def similarity_search(
        self, query, top_k=3, user_id=None, metadata_filter=None
    ):
        self.queries.append((query, top_k, user_id))
        return [{"text": q[0], "metadata": q[1] or {}} for q in self.added][:top_k]

    async def query_memory(
        self, memory_id=None, metadata=None, limit=None, user_id=None
    ):
        self.query_calls.append((memory_id, metadata, limit, user_id))
        if not self.added:
            return []
        text, meta, uid = self.added[0]
        result = {"id": "mem1", "text": text, "metadata": meta or {}}
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
    memory_agent = MemoryAgent(service, None)
    user = DummyAgent()
    user.memory = service

    network.register_agent(memory_agent)
    network.register_agent(user)

    await network.start()

    # store_memory uses network routing (request_capability + wait_for_response)
    mem_id = await asyncio.wait_for(
        user.store_memory("hello", {"foo": "bar"}), timeout=5.0
    )
    assert mem_id == "mem1"
    assert len(service.added) == 1
    assert service.added[0][0] == "hello"
    assert service.added[0][1] == {"foo": "bar"}

    # search_memory uses the local memory service directly
    results = await user.search_memory("hello", top_k=1)
    assert len(service.queries) == 1
    assert service.queries[0][:2] == ("hello", 1)

    # Test query_memory by id and metadata - use service directly
    query_by_id = await service.query_memory(memory_id=mem_id)
    assert query_by_id and query_by_id[0]["text"] == "hello"
    assert service.query_calls[-1][:3] == (mem_id, None, None)

    query_by_meta = await service.query_memory(metadata={"foo": "bar"})
    assert query_by_meta and query_by_meta[0]["metadata"]["foo"] == "bar"
    assert service.query_calls[-1][:3] == (None, {"foo": "bar"}, None)

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
    import json

    output = json.dumps({"dag": {"store_memory": []}})
    ai_client = DummyAIClient(output)
    jarvis = JarvisSystem(JarvisConfig(response_timeout=3.0))
    service = DummyVectorMemoryService()
    memory_agent = MemoryAgent(service, None, jarvis.logger)
    nlu_agent = NLUAgent(ai_client, jarvis.logger)
    jarvis.network.register_agent(memory_agent)
    jarvis.network.register_agent(nlu_agent)
    await jarvis.network.start()

    # Set up minimal orchestrator
    response_logger = AsyncMock(spec=ResponseLogger)
    response_logger.log_successful_interaction = AsyncMock()
    response_logger.log_failed_interaction = AsyncMock()
    jarvis._orchestrator = RequestOrchestrator(
        network=jarvis.network,
        protocol_runtime=None,
        response_logger=response_logger,
        logger=jarvis.logger,
        response_timeout=jarvis.config.response_timeout,
    )

    result = await asyncio.wait_for(
        jarvis.process_request("remember this", "UTC", allowed_agents=None),
        timeout=5.0,
    )

    await jarvis.network.stop()
    # Test passes if no exceptions occurred
    assert result is not None
    assert "response" in result
