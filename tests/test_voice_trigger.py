import pytest

from jarvis.protocols.voice_trigger import VoiceTriggerMatcher
from jarvis.protocols.models.protocol import Protocol
from jarvis.protocols.models.argument_definition import ArgumentDefinition, ArgumentType


def make_color_protocol():
    arg_def = ArgumentDefinition(
        name="color",
        type=ArgumentType.CHOICE,
        choices=["red", "blue"],
    )
    return Protocol(
        id="1",
        name="Light Color",
        description="",
        trigger_phrases=["lights {color}"],
        steps=[],
        argument_definitions=[arg_def],
    )


def make_simple_protocol():
    return Protocol(
        id="2",
        name="Shutdown",
        description="",
        trigger_phrases=["shutdown system"],
        steps=[],
    )


def test_exact_match_required_for_parameterized():
    proto = make_color_protocol()
    matcher = VoiceTriggerMatcher({proto.id: proto})

    result = matcher.match_command("lights red")
    assert result is not None
    assert result["arguments"]["color"] == "red"

    assert matcher.match_command("please lights red") is None


def test_exact_match_required_for_simple():
    proto = make_simple_protocol()
    matcher = VoiceTriggerMatcher({proto.id: proto})

    result = matcher.match_command("shutdown system")
    assert result is not None
    assert result["protocol"] == proto

    assert matcher.match_command("please shutdown system") is None
