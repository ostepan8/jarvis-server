import pytest

from jarvis.protocols.registry import ProtocolRegistry
from jarvis.protocols import Protocol


def make_protocol(id, name, triggers):
    return Protocol(id=id, name=name, description="", trigger_phrases=triggers, steps=[])


def test_register_unique_protocol(tmp_path):
    registry = ProtocolRegistry(db_path=str(tmp_path / "db.sqlite"))
    proto = make_protocol("1", "Lights Off", ["turn off lights"])
    result = registry.register(proto)
    assert result == {"success": True, "id": "1"}
    assert registry.get("1").name == "Lights Off"
    registry.close()


def test_register_duplicate_name(tmp_path):
    registry = ProtocolRegistry(db_path=str(tmp_path / "db.sqlite"))
    registry.register(make_protocol("1", "Lights Off", ["turn off lights"]))
    result = registry.register(make_protocol("2", " lights off ", ["other"]))
    assert result == {"success": False, "reason": "Duplicate name"}
    assert registry.get("2") is None
    registry.close()


def test_register_duplicate_triggers(tmp_path):
    registry = ProtocolRegistry(db_path=str(tmp_path / "db.sqlite"))
    registry.register(make_protocol("1", "Lights Off", ["turn off lights"]))
    result = registry.register(make_protocol("2", "Something", [" turn off lights "]))
    assert result == {"success": False, "reason": "Duplicate trigger phrases"}
    assert registry.get("2") is None
    registry.close()


def test_find_matching_protocol(tmp_path):
    registry = ProtocolRegistry(db_path=str(tmp_path / "db.sqlite"))
    proto1 = make_protocol("1", "Sleep Mode", ["sleep mode", "goodnight"])
    proto2 = make_protocol("2", "Movie Mode", ["movie mode", "start movie mode"])
    registry.register(proto1)
    registry.register(proto2)

    match = registry.find_matching_protocol("Start movie mode")
    assert match is not None
    assert match.name == "Movie Mode"

    no_match = registry.find_matching_protocol("unknown command")
    assert no_match is None
    registry.close()
