import asyncio
import pytest

from jarvis.core import JarvisSystem
from jarvis.core import JarvisConfig
from jarvis.agents.base import NetworkAgent


class DummyNLU(NetworkAgent):
    def __init__(self):
        super().__init__("nlu")

    @property
    def capabilities(self):
        return {"intent_matching"}

    async def _handle_capability_request(self, message):
        response = {
            "intent": "perform_capability",
            "capability": "nonexistent",
            "target_agent": "",
            "args": {},
            "raw": message.content["data"]["input"],
        }
        await self.send_capability_response(
            message.from_agent, response, message.request_id, message.id
        )

    async def _handle_capability_response(self, message):
        pass


@pytest.mark.asyncio
async def test_missing_capability_returns_error():
    jarvis = JarvisSystem(JarvisConfig(intent_timeout=0.1, response_timeout=0.1))
    nlu = DummyNLU()
    jarvis.nlu_agent = nlu
    jarvis.network.register_agent(nlu)

    await jarvis.network.start()
    try:
        result = await asyncio.wait_for(
            jarvis.process_request("test", "UTC", allowed_agents=None),
            timeout=1.0,
        )
    finally:
        await jarvis.network.stop()

    assert result["response"] == "No agent is available to handle that request."

