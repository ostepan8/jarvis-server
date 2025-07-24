import asyncio
from types import SimpleNamespace

import httpx
import pytest
from httpx import ASGITransport

import server
from server.dependencies import get_user_allowed_agents
from jarvis.agents.agent_network import AgentNetwork
from jarvis.agents.base import NetworkAgent
from jarvis.logger import JarvisLogger
from jarvis.protocols import Protocol, ProtocolStep
from jarvis.protocols.executor import ProtocolExecutor
from jarvis.protocols.registry import ProtocolRegistry


class DummyAgent(NetworkAgent):
    def __init__(self):
        super().__init__("dummy")
        self.intent_map = {"echo": self.echo}

    @property
    def capabilities(self):
        return {"echo"}

    async def echo(self, **kwargs):
        return {"echo": kwargs}


@pytest.mark.asyncio
async def test_run_protocol_endpoint(tmp_path):
    logger = JarvisLogger()
    network = AgentNetwork(logger)
    agent = DummyAgent()
    network.register_agent(agent)
    executor = ProtocolExecutor(network, logger)
    registry = ProtocolRegistry(db_path=str(tmp_path / "db.sqlite"), logger=logger)
    jarvis = SimpleNamespace(protocol_executor=executor, protocol_registry=registry)

    async def override_get_jarvis():
        return jarvis

    server.app.dependency_overrides[server.get_jarvis] = override_get_jarvis
    server.app.dependency_overrides[get_user_allowed_agents] = lambda: {"dummy"}

    proto = Protocol(
        id="1",
        name="Echo",
        description="",
        steps=[ProtocolStep(agent="dummy", function="echo", parameters={"msg": "hi"})],
    )

    server.app.router.on_startup.clear()
    server.app.router.on_shutdown.clear()
    transport = ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/protocols/run", json={"protocol": proto.to_dict()})
        assert resp.status_code == 200
        data = resp.json()
        assert data["results"]["step_0_echo"]["echo"] == {"msg": "hi"}

    registry.register(proto)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/protocols/run", json={"protocol_name": "Echo"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["results"]["step_0_echo"]["echo"] == {"msg": "hi"}

    server.app.dependency_overrides.clear()
