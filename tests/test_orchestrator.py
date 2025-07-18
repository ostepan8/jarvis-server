import asyncio
import pytest

from jarvis.agents.agent_network import AgentNetwork
from jarvis.agents.orchestrator_agent import OrchestratorAgent
from jarvis.agents.base import NetworkAgent
from jarvis.ai_clients.base import BaseAIClient


class DummyAIClient(BaseAIClient):
    def __init__(self, responses):
        self.responses = list(responses)

    async def strong_chat(self, messages, tools=None):
        content = self.responses.pop(0)
        return (type("Msg", (), {"content": content}), None)

    async def weak_chat(self, messages, tools=None):
        content = self.responses.pop(0)
        return (type("Msg", (), {"content": content}), None)


class ProviderAgent(NetworkAgent):
    def __init__(self):
        super().__init__("provider")
        self.received = asyncio.Queue()

    @property
    def capabilities(self):
        return {"dummy_cap"}

    async def _handle_capability_request(self, message):
        await self.received.put(message)
        await self.send_capability_response(
            message.from_agent, {"done": True}, message.request_id, message.id
        )


class MemoryProviderAgent(NetworkAgent):
    def __init__(self):
        super().__init__("memory_provider")
        self.received = asyncio.Queue()

    @property
    def capabilities(self):
        return {"query_memory"}

    async def _handle_capability_request(self, message):
        await self.received.put(message)
        await self.send_capability_response(
            message.from_agent, {"memories": []}, message.request_id, message.id
        )


@pytest.mark.asyncio
async def test_orchestrator_sequence():
    ai = DummyAIClient(
        [
            '{"intent":"test","capabilities_needed":["dummy_cap"],"dependencies":{}}',
            "All done",
        ]
    )
    network = AgentNetwork()
    orch = OrchestratorAgent(ai, response_timeout=1.0)
    provider = ProviderAgent()
    network.register_agent(orch)
    network.register_agent(provider)
    await network.start()

    result = await orch.process_user_request("test", "UTC")
    await network.stop()

    assert result["success"] is True
    assert not provider.received.empty()


@pytest.mark.asyncio
async def test_orchestrator_query_memory_plan():
    ai = DummyAIClient(
        [
            '{"intent":"test","capabilities_needed":["query_memory"],"dependencies":{}}',
            "All done",
        ]
    )
    network = AgentNetwork()
    orch = OrchestratorAgent(ai, response_timeout=1.0)
    provider = MemoryProviderAgent()
    network.register_agent(orch)
    network.register_agent(provider)
    await network.start()

    result = await orch.process_user_request("test", "UTC")
    await network.stop()

    assert result["success"] is True
    assert not provider.received.empty()
