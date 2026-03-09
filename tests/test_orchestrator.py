"""Tests for request orchestration through the agent network."""

import asyncio
import json
import pytest
from unittest.mock import AsyncMock

from jarvis.agents.agent_network import AgentNetwork
from jarvis.agents.nlu_agent import NLUAgent
from jarvis.agents.base import NetworkAgent
from jarvis.ai_clients.base import BaseAIClient
from jarvis.logging import JarvisLogger
from jarvis.core.orchestrator import RequestOrchestrator
from jarvis.core.response_logger import ResponseLogger


class DummyAIClient(BaseAIClient):
    def __init__(self, responses):
        self.responses = list(responses)

    async def strong_chat(self, messages, tools=None):
        content = self.responses.pop(0) if self.responses else ""
        return (type("Msg", (), {"content": content}), None)

    async def weak_chat(self, messages, tools=None):
        content = self.responses.pop(0) if self.responses else ""
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
            message.from_agent,
            {"success": True, "response": "done", "done": True},
            message.request_id,
            message.id,
        )

    async def _handle_capability_response(self, message):
        pass


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
            message.from_agent,
            {"success": True, "response": "no memories", "memories": []},
            message.request_id,
            message.id,
        )

    async def _handle_capability_response(self, message):
        pass


def _make_mock_response_logger():
    logger = AsyncMock(spec=ResponseLogger)
    logger.log_successful_interaction = AsyncMock()
    logger.log_failed_interaction = AsyncMock()
    return logger


@pytest.mark.asyncio
async def test_orchestrator_sequence():
    """Request flows through NLU to provider agent and back."""
    ai = DummyAIClient([
        json.dumps({"dag": {"dummy_cap": []}}),
    ])
    logger = JarvisLogger()
    network = AgentNetwork(logger)
    nlu = NLUAgent(ai, logger)
    provider = ProviderAgent()
    network.register_agent(nlu)
    network.register_agent(provider)
    await network.start()

    response_logger = _make_mock_response_logger()
    orchestrator = RequestOrchestrator(
        network=network,
        protocol_runtime=None,
        response_logger=response_logger,
        logger=logger,
        response_timeout=5.0,
    )

    result = await orchestrator.process_request("test", "UTC")
    await network.stop()

    assert result is not None
    assert "response" in result
    msg = provider.received.get_nowait()
    assert msg is not None


@pytest.mark.asyncio
async def test_orchestrator_query_memory_plan():
    """Request flows through NLU to memory provider."""
    ai = DummyAIClient([
        json.dumps({"dag": {"query_memory": []}}),
    ])
    logger = JarvisLogger()
    network = AgentNetwork(logger)
    nlu = NLUAgent(ai, logger)
    provider = MemoryProviderAgent()
    network.register_agent(nlu)
    network.register_agent(provider)
    await network.start()

    response_logger = _make_mock_response_logger()
    orchestrator = RequestOrchestrator(
        network=network,
        protocol_runtime=None,
        response_logger=response_logger,
        logger=logger,
        response_timeout=5.0,
    )

    result = await orchestrator.process_request("test", "UTC")
    await network.stop()

    assert result is not None
    assert "response" in result
    msg = provider.received.get_nowait()
    assert msg is not None
