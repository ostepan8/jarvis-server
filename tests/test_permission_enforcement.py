import sqlite3
import httpx
import pytest
from httpx import ASGITransport
from types import SimpleNamespace
from unittest.mock import AsyncMock

import server
from server.dependencies import get_user_allowed_agents, get_current_user, get_auth_db
from jarvis.protocols import Protocol, ProtocolStep
from jarvis.protocols.executor import ProtocolExecutor
from jarvis.protocols.voice_trigger import VoiceTriggerMatcher
from jarvis.protocols.registry import ProtocolRegistry
from jarvis.protocols.runtime import ProtocolRuntime
from jarvis.agents.agent_network import AgentNetwork
from jarvis.agents.base import NetworkAgent
from jarvis.logging import JarvisLogger
from jarvis.core import JarvisSystem, JarvisConfig
from jarvis.core.orchestrator import RequestOrchestrator
from jarvis.core.response_logger import ResponseLogger


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
    server.app.dependency_overrides[server.get_user_jarvis] = override_get_jarvis
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

    proto = Protocol(
        id="1",
        name="Test",
        description="",
        trigger_phrases=["do test"],
        steps=[ProtocolStep(agent="dummy", function="do", parameters={})],
    )

    # Set up protocol runtime with voice matcher
    jarvis.protocol_runtime = ProtocolRuntime(jarvis.network, logger)
    jarvis.protocol_runtime.registry.close()
    jarvis.protocol_runtime.registry = ProtocolRegistry(
        db_path=str(tmp_path / "proto.db"), logger=logger
    )
    jarvis.protocol_runtime.registry.register(proto)
    jarvis.protocol_runtime.voice_matcher = VoiceTriggerMatcher(
        jarvis.protocol_runtime.registry.protocols
    )

    # Set up orchestrator
    response_logger = AsyncMock(spec=ResponseLogger)
    response_logger.log_successful_interaction = AsyncMock()
    response_logger.log_failed_interaction = AsyncMock()
    jarvis._orchestrator = RequestOrchestrator(
        network=jarvis.network,
        protocol_runtime=jarvis.protocol_runtime,
        response_logger=response_logger,
        logger=logger,
        response_timeout=15.0,
    )

    await jarvis.network.start()

    async def override_get_jarvis():
        return jarvis

    async def override_allowed():
        return {"other"}

    async def override_current_user():
        return {"id": 1, "email": "test@test.com"}

    _db = sqlite3.connect(":memory:")
    _db.execute(
        "CREATE TABLE user_profiles (user_id INTEGER PRIMARY KEY, name TEXT, "
        "preferred_personality TEXT, interests TEXT, conversation_style TEXT, "
        "humor_preference TEXT, topics_of_interest TEXT, language_preference TEXT, "
        "interaction_count INTEGER DEFAULT 0, favorite_games TEXT, last_seen TEXT, "
        "required_resources TEXT)"
    )
    _db.commit()

    def override_auth_db():
        return _db

    server.app.dependency_overrides[server.get_jarvis] = override_get_jarvis
    server.app.dependency_overrides[server.get_user_jarvis] = override_get_jarvis
    server.app.dependency_overrides[get_user_allowed_agents] = override_allowed
    server.app.dependency_overrides[get_current_user] = override_current_user
    server.app.dependency_overrides[get_auth_db] = override_auth_db

    server.app.router.on_startup.clear()
    server.app.router.on_shutdown.clear()
    transport = ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/jarvis/", json={"command": "do test"})
        assert resp.status_code == 200
        data = resp.json()
        assert dummy.called == 0
        assert "agent_disallowed" in data["response"]

    await jarvis.network.stop()
    _db.close()
    server.app.dependency_overrides.clear()
