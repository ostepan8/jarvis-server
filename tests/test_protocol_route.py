import pytest
from types import SimpleNamespace

from server import list_protocols
from jarvis.protocols.registry import ProtocolRegistry
from jarvis.protocols import Protocol


class DummyJarvis:
    def __init__(self, registry):
        self.protocol_registry = registry
        self.network = SimpleNamespace(agents={})

    def list_protocols(self, allowed_agents=None):
        return list(self.protocol_registry.protocols.values())


@pytest.mark.asyncio
async def test_list_protocols(tmp_path):
    registry = ProtocolRegistry(db_path=str(tmp_path / "db.sqlite"))
    proto = Protocol(id="1", name="Test", description="", steps=[])
    registry.register(proto)
    jarvis = DummyJarvis(registry)
    result = await list_protocols(jarvis)
    assert result["protocols"][0]["id"] == "1"
    assert result["protocols"][0]["name"] == "Test"
