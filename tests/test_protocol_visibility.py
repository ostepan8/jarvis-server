import pytest

import server
from jarvis.main_jarvis import JarvisSystem, JarvisConfig
from jarvis.protocols import Protocol, ProtocolStep
from jarvis.protocols.registry import ProtocolRegistry
from jarvis.agents.agent_network import AgentNetwork
from jarvis.agents.base import NetworkAgent
from jarvis.logger import JarvisLogger


class DummyAgent(NetworkAgent):
    def __init__(self, name="dummy"):
        super().__init__(name)
        self.intent_map = {"do": self.do}

    @property
    def capabilities(self):
        return {"do"}

    async def do(self, **kwargs):
        return {"done": True}


@pytest.mark.asyncio
async def test_list_protocols_filters_by_agents(tmp_path):
    jarvis = JarvisSystem(JarvisConfig())
    jarvis.logger = JarvisLogger()
    jarvis.network = AgentNetwork(jarvis.logger)
    jarvis.protocol_registry = ProtocolRegistry(db_path=str(tmp_path/"db.sqlite"), logger=jarvis.logger)

    jarvis.network.register_agent(DummyAgent("dummy"))

    proto_allowed = Protocol(
        id="1",
        name="Allowed",
        description="",
        steps=[ProtocolStep(agent="dummy", function="do", parameters={})],
    )
    proto_missing = Protocol(
        id="2",
        name="Missing",
        description="",
        steps=[ProtocolStep(agent="other", function="do", parameters={})],
    )
    jarvis.protocol_registry.register(proto_allowed)
    jarvis.protocol_registry.register(proto_missing)

    result = await server.list_protocols(jarvis)
    names = {p["name"] for p in result["protocols"]}
    assert "Allowed" in names
    assert "Missing" not in names

    result = await server.list_protocols(jarvis, {"dummy"})
    names = [p["name"] for p in result["protocols"]]
    assert names == ["Allowed"]

    result = await server.list_protocols(jarvis, {"other"})
    assert result["protocols"] == []
