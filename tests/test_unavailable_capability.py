import asyncio
import pytest
from unittest.mock import AsyncMock

from jarvis.core import JarvisSystem
from jarvis.core import JarvisConfig
from jarvis.agents.base import NetworkAgent
from jarvis.core.orchestrator import RequestOrchestrator
from jarvis.core.response_logger import ResponseLogger


class DummyNLU(NetworkAgent):
    def __init__(self):
        super().__init__("nlu")

    @property
    def capabilities(self):
        return {"intent_matching"}

    async def _handle_capability_request(self, message):
        response = {
            "success": False,
            "response": "No agent is available to handle that request.",
        }
        await self.send_capability_response(
            message.from_agent, response, message.request_id, message.id
        )

    async def _handle_capability_response(self, message):
        pass


@pytest.mark.asyncio
async def test_missing_capability_returns_error():
    jarvis = JarvisSystem(JarvisConfig(intent_timeout=0.1, response_timeout=1.0))
    nlu = DummyNLU()
    jarvis.network.register_agent(nlu)

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

    try:
        result = await asyncio.wait_for(
            jarvis.process_request("test", "UTC", allowed_agents=None),
            timeout=3.0,
        )
    finally:
        await jarvis.network.stop()

    assert result["response"] == "No agent is available to handle that request."
