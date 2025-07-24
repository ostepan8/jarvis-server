import asyncio
import pytest

from jarvis.main_jarvis import JarvisSystem
from jarvis.config import JarvisConfig
from jarvis.agents.base import NetworkAgent

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
    config = JarvisConfig(intent_timeout=0.05)
    jarvis = JarvisSystem(config)
    silent = SilentNLUAgent()
    jarvis.nlu_agent = silent
    jarvis.network.register_agent(silent)

    await jarvis.network.start()
    result = await jarvis.process_request("hello", "UTC", allowed_agents=None)
    await jarvis.network.stop()

    assert "too long" in result["response"]
