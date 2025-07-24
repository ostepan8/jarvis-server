import asyncio
import httpx
import pytest
from httpx import ASGITransport
from types import SimpleNamespace

import server
from server.dependencies import get_user_allowed_agents
from jarvis.protocols import Protocol, ProtocolStep
from jarvis.protocols.executor import ProtocolExecutor
from jarvis.protocols.voice_trigger import VoiceTriggerMatcher
from jarvis.agents.agent_network import AgentNetwork
from jarvis.agents.base import NetworkAgent
from jarvis.logger import JarvisLogger
from jarvis.main_jarvis import JarvisSystem, JarvisConfig
from jarvis.protocols.registry import ProtocolRegistry


class DummyAgent(NetworkAgent):
    def __init__(self, name="dummy"):
        super().__init__(name)
        self.intent_map = {"echo": self.echo, "do": self.echo}
        self.called = 0

    @property
    def capabilities(self):
        return {"echo", "do"}

    async def echo(self, **kwargs):
        self.called += 1
        return {"echo": True}


@pytest.mark.asyncio
async def test_protocol_run_disallowed_agent(tmp_path):
    logger = JarvisLogger()
    network = AgentNetwork(logger)
    agent = DummyAgent()
    network.register_agent(agent)
    executor = ProtocolExecutor(network, logger)
    registry = ProtocolRegistry(db_path=str(tmp_path / "db.sqlite"), logger=logger)
    jarvis = SimpleNamespace(protocol_executor=executor, protocol_registry=registry)

    async def override_get_jarvis():
        return jarvis

    async def override_allowed():
        return {"other"}

    server.app.dependency_overrides[server.get_jarvis] = override_get_jarvis
    server.app.dependency_overrides[get_user_allowed_agents] = override_allowed

    proto = Protocol(
        id="1",
        name="Echo",
        description="",
        steps=[ProtocolStep(agent="dummy", function="echo", parameters={})],
    )

    server.app.router.on_startup.clear()
    server.app.router.on_shutdown.clear()
    transport = ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/protocols/run", json={"protocol": proto.to_dict()})
        assert resp.status_code == 200
        data = resp.json()
        assert data["results"]["step_0_echo"]["error"] == "agent_disallowed"
        assert agent.called == 0

    server.app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_voice_trigger_disallowed_agent(tmp_path):
    logger = JarvisLogger()
    jarvis = JarvisSystem(JarvisConfig())
    dummy = DummyAgent()
    jarvis.network.register_agent(dummy)
    nlu = DummyAgent("nlu")
    jarvis.network.register_agent(nlu)
    jarvis.nlu_agent = nlu
    jarvis.protocol_executor = ProtocolExecutor(jarvis.network, logger)

    proto = Protocol(
        id="1",
        name="Test",
        description="",
        trigger_phrases=["do test"],
        steps=[ProtocolStep(agent="dummy", function="do", parameters={})],
    )
    jarvis.voice_matcher = VoiceTriggerMatcher({proto.id: proto})

    async def override_get_jarvis():
        return jarvis

    async def override_allowed():
        return {"other"}

    server.app.dependency_overrides[server.get_jarvis] = override_get_jarvis
    server.app.dependency_overrides[get_user_allowed_agents] = override_allowed

    server.app.router.on_startup.clear()
    server.app.router.on_shutdown.clear()
    transport = ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/jarvis/", json={"command": "do test"})
        assert resp.status_code == 200
        data = resp.json()
        assert dummy.called == 0
        assert "agent_disallowed" in data["response"]

    server.app.dependency_overrides.clear()
