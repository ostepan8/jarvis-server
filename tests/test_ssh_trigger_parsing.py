"""Tests for SSH trigger phrase parsing and device-targeted mode entry."""

from __future__ import annotations

import pytest

from main import _parse_ssh_trigger


# --- _parse_ssh_trigger ---------------------------------------------------


class TestParseSSHTrigger:
    """Verify the SSH trigger parser extracts device names correctly."""

    @pytest.mark.parametrize(
        "cmd",
        [
            "ssh into my tv",
            "ssh roku",
            "ssh into roku",
            "ssh into my roku",
            "ssh into the tv",
            "ssh tv",
            "connect to my tv",
            "connect to roku",
            "ssh",
            "connect to my roku",
        ],
    )
    def test_generic_triggers_return_empty_string(self, cmd: str) -> None:
        result = _parse_ssh_trigger(cmd)
        assert result == "", f"Expected '' for '{cmd}', got {result!r}"

    @pytest.mark.parametrize(
        "cmd, expected_device",
        [
            ("ssh into bedroom tv", "bedroom"),
            ("ssh into living room tv", "living room"),
            ("ssh bedroom roku", "bedroom"),
            ("ssh living room roku", "living room"),
            ("ssh into my bedroom tv", "bedroom"),
            ("ssh into the bedroom tv", "bedroom"),
            ("connect to bedroom tv", "bedroom"),
            ("connect to living room roku", "living room"),
            ("ssh bedroom", "bedroom"),
            ("ssh living room", "living room"),
            ("connect to bedroom", "bedroom"),
            ("ssh into bedroom", "bedroom"),
        ],
    )
    def test_device_targeted_triggers(self, cmd: str, expected_device: str) -> None:
        result = _parse_ssh_trigger(cmd)
        assert result == expected_device, (
            f"Expected {expected_device!r} for '{cmd}', got {result!r}"
        )

    @pytest.mark.parametrize(
        "cmd",
        [
            "turn on the lights",
            "what's the weather",
            "play music",
            "hello",
            "",
            "search for something",
        ],
    )
    def test_non_triggers_return_none(self, cmd: str) -> None:
        result = _parse_ssh_trigger(cmd)
        assert result is None, f"Expected None for '{cmd}', got {result!r}"


# --- RokuMode target_device -----------------------------------------------


class TestRokuModeTargetDevice:
    """Verify RokuMode accepts and uses target_device."""

    def test_constructor_accepts_target_device(self) -> None:
        from jarvis.cli.modes.roku_mode import RokuMode
        from unittest.mock import MagicMock

        jarvis = MagicMock()
        mode = RokuMode(jarvis, target_device="bedroom")
        assert mode._target_device == "bedroom"

    def test_constructor_defaults_to_none(self) -> None:
        from jarvis.cli.modes.roku_mode import RokuMode
        from unittest.mock import MagicMock

        jarvis = MagicMock()
        mode = RokuMode(jarvis)
        assert mode._target_device is None
