import asyncio
import pytest
from unittest.mock import AsyncMock

from jarvis.core import JarvisSystem
from jarvis.core import JarvisConfig
from jarvis.agents.base import NetworkAgent
from jarvis.core.orchestrator import RequestOrchestrator
from jarvis.core.response_logger import ResponseLogger


class SilentNLUAgent(NetworkAgent):
    def __init__(self):
        super().__init__("nlu")

    @property
    def capabilities(self):
        return {"intent_matching"}

    async def _handle_capability_request(self, message):
        # Do not respond
        return

    async def _handle_capability_response(self, message):
        pass


@pytest.mark.asyncio
async def test_nlu_classification_timeout():
    config = JarvisConfig(intent_timeout=0.05, response_timeout=0.5)
    jarvis = JarvisSystem(config)
    silent = SilentNLUAgent()
    jarvis.network.register_agent(silent)

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
        response_timeout=config.response_timeout,
    )

    result = await jarvis.process_request("hello", "UTC", allowed_agents=None)
    await jarvis.network.stop()

    assert "too long" in result["response"]
