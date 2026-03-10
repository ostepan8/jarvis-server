"""Comprehensive tests for LightingAgent."""

import pytest
from unittest.mock import MagicMock, AsyncMock

from jarvis.agents.lights_agent.lighting_agent import LightingAgent, create_lighting_agent
from jarvis.agents.lights_agent.backend import BaseLightingBackend
from jarvis.agents.message import Message
from jarvis.ai_clients.base import BaseAIClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class DummyAIClient(BaseAIClient):
    """AI client that returns a simple JSON-like response for color parsing."""

    def __init__(self, response_text='{"color": "blue", "brightness": "normal", "target": "all"}'):
        self._response_text = response_text

    async def strong_chat(self, messages, tools=None):
        msg = type("Message", (), {"content": self._response_text})()
        return msg, None

    async def weak_chat(self, messages, tools=None):
        msg = type("Message", (), {"content": self._response_text})()
        return msg, None


class MockBackend(BaseLightingBackend):
    """A mock lighting backend for testing."""

    COLOR_MAP = {
        "red": {"hue": 0, "sat": 254},
        "blue": {"hue": 46920, "sat": 254},
        "green": {"hue": 25500, "sat": 254},
        "yellow": {"hue": 12750, "sat": 254},
        "white": {"hue": 0, "sat": 0},
        "purple": {"hue": 56100, "sat": 254},
        "pink": {"hue": 62000, "sat": 254},
        "orange": {"hue": 8000, "sat": 254},
    }

    def __init__(self):
        self.calls = []

    def turn_on_all_lights(self) -> str:
        self.calls.append(("turn_on_all_lights",))
        return "Turned on all 3 lights"

    def turn_off_all_lights(self) -> str:
        self.calls.append(("turn_off_all_lights",))
        return "Turned off all 3 lights"

    def set_all_brightness(self, brightness: int) -> str:
        self.calls.append(("set_all_brightness", brightness))
        return f"Set brightness of all 3 lights to {brightness}"

    def set_all_color(self, color_name: str) -> str:
        self.calls.append(("set_all_color", color_name))
        return f"Set all 3 lights to {color_name}"

    def turn_on_light(self, light_name: str) -> str:
        self.calls.append(("turn_on_light", light_name))
        return f"Turned on {light_name}"

    def turn_off_light(self, light_name: str) -> str:
        self.calls.append(("turn_off_light", light_name))
        return f"Turned off {light_name}"

    def toggle_light(self, light_name: str) -> str:
        self.calls.append(("toggle_light", light_name))
        return f"Toggled {light_name}"

    def set_brightness(self, light_name: str, brightness: int) -> str:
        self.calls.append(("set_brightness", light_name, brightness))
        return f"Set brightness of {light_name} to {brightness}"

    def set_color_name(self, light_name: str, color_name: str) -> str:
        self.calls.append(("set_color_name", light_name, color_name))
        return f"Set {light_name} to {color_name}"

    def list_lights(self):
        self.calls.append(("list_lights",))
        return {
            "lights": [
                {"id": 1, "name": "Desk Lamp", "on": True},
                {"id": 2, "name": "Floor Lamp", "on": False},
            ]
        }

    def get_color_map(self):
        return self.COLOR_MAP.copy()


def _make_lighting_message(capability, prompt="", from_agent="tester",
                           request_id="req-1", context=None):
    """Build a capability_request Message for LightingAgent."""
    data = {"prompt": prompt}
    if context is not None:
        data["context"] = context
    return Message(
        from_agent=from_agent,
        to_agent="LightingAgent",
        message_type="capability_request",
        content={"capability": capability, "data": data},
        request_id=request_id,
    )


# ---------------------------------------------------------------------------
# Tests: metadata & properties
# ---------------------------------------------------------------------------

class TestLightingAgentProperties:
    """Test LightingAgent metadata and configuration."""

    def test_name(self):
        agent = LightingAgent(backend=MockBackend(), ai_client=DummyAIClient())
        assert agent.name == "LightingAgent"

    def test_description_includes_backend_type(self):
        agent = LightingAgent(backend=MockBackend(), ai_client=DummyAIClient())
        assert "Mock" in agent.description

    def test_capabilities(self):
        agent = LightingAgent(backend=MockBackend(), ai_client=DummyAIClient())
        expected = {
            "lights_on", "lights_off", "lights_brightness",
            "lights_color", "lights_list", "lights_status", "lights_toggle",
        }
        assert agent.capabilities == expected

    def test_color_map_populated(self):
        agent = LightingAgent(backend=MockBackend(), ai_client=DummyAIClient())
        assert "red" in agent.color_map
        assert "blue" in agent.color_map

    def test_intent_map_keys(self):
        agent = LightingAgent(backend=MockBackend(), ai_client=DummyAIClient())
        expected = {
            "turn_on_all_lights", "turn_off_all_lights",
            "set_all_brightness", "set_all_color",
            "turn_on_light", "turn_off_light", "toggle_light",
            "set_brightness", "set_color_name", "list_lights",
        }
        assert set(agent.intent_map.keys()) == expected


# ---------------------------------------------------------------------------
# Tests: direct method invocations
# ---------------------------------------------------------------------------

class TestLightingAgentDirectMethods:
    """Test synchronous backend method wrappers."""

    def test_turn_on_all_lights(self):
        backend = MockBackend()
        agent = LightingAgent(backend=backend, ai_client=DummyAIClient())
        result = agent._turn_on_all_lights()
        assert "Turned on" in result
        assert ("turn_on_all_lights",) in backend.calls

    def test_turn_off_all_lights(self):
        backend = MockBackend()
        agent = LightingAgent(backend=backend, ai_client=DummyAIClient())
        result = agent._turn_off_all_lights()
        assert "Turned off" in result
        assert ("turn_off_all_lights",) in backend.calls

    def test_set_all_brightness(self):
        backend = MockBackend()
        agent = LightingAgent(backend=backend, ai_client=DummyAIClient())
        result = agent._set_all_brightness(200)
        assert "200" in result
        assert ("set_all_brightness", 200) in backend.calls

    def test_set_all_color(self):
        backend = MockBackend()
        agent = LightingAgent(backend=backend, ai_client=DummyAIClient())
        result = agent._set_all_color("red")
        assert "red" in result
        assert ("set_all_color", "red") in backend.calls

    def test_turn_on_light(self):
        backend = MockBackend()
        agent = LightingAgent(backend=backend, ai_client=DummyAIClient())
        result = agent._turn_on_light("Desk Lamp")
        assert "Desk Lamp" in result

    def test_turn_off_light(self):
        backend = MockBackend()
        agent = LightingAgent(backend=backend, ai_client=DummyAIClient())
        result = agent._turn_off_light("Desk Lamp")
        assert "Desk Lamp" in result

    def test_toggle_light(self):
        backend = MockBackend()
        agent = LightingAgent(backend=backend, ai_client=DummyAIClient())
        result = agent._toggle_light("Desk Lamp")
        assert "Desk Lamp" in result

    def test_set_brightness(self):
        backend = MockBackend()
        agent = LightingAgent(backend=backend, ai_client=DummyAIClient())
        result = agent._set_brightness("Desk Lamp", 150)
        assert "Desk Lamp" in result

    def test_set_color_name(self):
        backend = MockBackend()
        agent = LightingAgent(backend=backend, ai_client=DummyAIClient())
        result = agent._set_color_name("Desk Lamp", "blue")
        assert "Desk Lamp" in result

    def test_list_lights(self):
        backend = MockBackend()
        agent = LightingAgent(backend=backend, ai_client=DummyAIClient())
        result = agent._list_lights()
        assert "lights" in result
        assert len(result["lights"]) == 2


# ---------------------------------------------------------------------------
# Tests: brightness normalization
# ---------------------------------------------------------------------------

class TestBrightnessNormalization:
    """Test brightness normalization for different backends."""

    def test_hue_backend_passthrough(self):
        """Non-Yeelight backends pass brightness through unchanged."""
        backend = MockBackend()
        agent = LightingAgent(backend=backend, ai_client=DummyAIClient())
        assert agent._normalize_brightness(254) == 254
        assert agent._normalize_brightness(0) == 0
        assert agent._normalize_brightness(127) == 127

    def test_yeelight_backend_conversion(self):
        """Yeelight backend converts 0-254 range to 1-100."""
        from jarvis.agents.lights_agent.yeelight_backend import YeelightBackend

        backend = MockBackend()
        agent = LightingAgent(backend=backend, ai_client=DummyAIClient())
        # Simulate yeelight by setting the flag
        agent._is_yeelight = True

        assert agent._normalize_brightness(0) == 0
        assert agent._normalize_brightness(254) == 100
        assert 1 <= agent._normalize_brightness(127) <= 100

    def test_yeelight_brightness_min_clamp(self):
        """Yeelight backend clamps minimum to 1 for non-zero values."""
        backend = MockBackend()
        agent = LightingAgent(backend=backend, ai_client=DummyAIClient())
        agent._is_yeelight = True
        # Very low brightness should clamp to 1
        assert agent._normalize_brightness(1) >= 1


# ---------------------------------------------------------------------------
# Tests: run_capability
# ---------------------------------------------------------------------------

class TestRunCapability:
    """Test run_capability dispatching."""

    @pytest.mark.asyncio
    async def test_run_capability_sync_method(self):
        """Sync methods are executed via executor."""
        backend = MockBackend()
        agent = LightingAgent(backend=backend, ai_client=DummyAIClient())
        result = await agent.run_capability("turn_on_all_lights")
        assert "Turned on" in result

    @pytest.mark.asyncio
    async def test_run_capability_unknown(self):
        """Unknown capability raises NotImplementedError."""
        backend = MockBackend()
        agent = LightingAgent(backend=backend, ai_client=DummyAIClient())
        with pytest.raises(NotImplementedError):
            await agent.run_capability("unknown_capability")


# ---------------------------------------------------------------------------
# Tests: _handle_capability_request
# ---------------------------------------------------------------------------

class TestLightingCapabilityRequest:
    """Test capability request handling."""

    @pytest.mark.asyncio
    async def test_lights_on_capability(self, monkeypatch):
        """lights_on capability calls _process_on_command."""
        backend = MockBackend()
        agent = LightingAgent(backend=backend, ai_client=DummyAIClient())
        captured = {}

        async def fake_send(to, result, request_id, msg_id):
            captured["result"] = result

        monkeypatch.setattr(agent, "send_capability_response", fake_send)
        msg = _make_lighting_message("lights_on", "turn on the lights")
        await agent._handle_capability_request(msg)

        assert captured["result"]["status"] == "success"
        assert ("turn_on_all_lights",) in backend.calls

    @pytest.mark.asyncio
    async def test_lights_off_capability(self, monkeypatch):
        """lights_off capability turns off all lights."""
        backend = MockBackend()
        agent = LightingAgent(backend=backend, ai_client=DummyAIClient())
        captured = {}

        async def fake_send(to, result, request_id, msg_id):
            captured["result"] = result

        monkeypatch.setattr(agent, "send_capability_response", fake_send)
        msg = _make_lighting_message("lights_off", "turn off lights")
        await agent._handle_capability_request(msg)

        assert captured["result"]["status"] == "success"
        assert ("turn_off_all_lights",) in backend.calls

    @pytest.mark.asyncio
    async def test_lights_list_capability(self, monkeypatch):
        """lights_list capability returns available lights."""
        backend = MockBackend()
        agent = LightingAgent(backend=backend, ai_client=DummyAIClient())
        captured = {}

        async def fake_send(to, result, request_id, msg_id):
            captured["result"] = result

        monkeypatch.setattr(agent, "send_capability_response", fake_send)
        msg = _make_lighting_message("lights_list")
        await agent._handle_capability_request(msg)

        assert captured["result"]["success"] is True
        assert "2 lights" in captured["result"]["response"]

    @pytest.mark.asyncio
    async def test_lights_status_capability(self, monkeypatch):
        """lights_status capability returns online status."""
        backend = MockBackend()
        agent = LightingAgent(backend=backend, ai_client=DummyAIClient())
        captured = {}

        async def fake_send(to, result, request_id, msg_id):
            captured["result"] = result

        monkeypatch.setattr(agent, "send_capability_response", fake_send)
        msg = _make_lighting_message("lights_status")
        await agent._handle_capability_request(msg)

        assert captured["result"]["success"] is True
        assert "online" in captured["result"]["response"].lower()

    @pytest.mark.asyncio
    async def test_lights_brightness_capability_with_number(self, monkeypatch):
        """lights_brightness capability extracts number from prompt."""
        backend = MockBackend()
        agent = LightingAgent(backend=backend, ai_client=DummyAIClient())
        captured = {}

        async def fake_send(to, result, request_id, msg_id):
            captured["result"] = result

        monkeypatch.setattr(agent, "send_capability_response", fake_send)
        msg = _make_lighting_message("lights_brightness", "set brightness to 75")
        await agent._handle_capability_request(msg)

        assert captured["result"]["status"] == "success"
        # 75% of 254 = ~190
        brightness = captured["result"]["brightness"]
        assert 180 <= brightness <= 200

    @pytest.mark.asyncio
    async def test_lights_brightness_default_value(self, monkeypatch):
        """lights_brightness defaults to 50% when no number in prompt."""
        backend = MockBackend()
        agent = LightingAgent(backend=backend, ai_client=DummyAIClient())
        captured = {}

        async def fake_send(to, result, request_id, msg_id):
            captured["result"] = result

        monkeypatch.setattr(agent, "send_capability_response", fake_send)
        msg = _make_lighting_message("lights_brightness", "set brightness")
        await agent._handle_capability_request(msg)

        assert captured["result"]["brightness"] == 127  # 50% default

    @pytest.mark.asyncio
    async def test_lights_toggle_capability(self, monkeypatch):
        """lights_toggle capability returns success."""
        backend = MockBackend()
        agent = LightingAgent(backend=backend, ai_client=DummyAIClient())
        captured = {}

        async def fake_send(to, result, request_id, msg_id):
            captured["result"] = result

        monkeypatch.setattr(agent, "send_capability_response", fake_send)
        msg = _make_lighting_message("lights_toggle", "toggle lights")
        await agent._handle_capability_request(msg)

        assert captured["result"]["status"] == "success"

    @pytest.mark.asyncio
    async def test_lights_color_capability(self, monkeypatch):
        """lights_color capability parses color from AI response."""
        backend = MockBackend()
        ai = DummyAIClient('{"color": "red", "brightness": "normal", "target": "all"}')
        agent = LightingAgent(backend=backend, ai_client=ai)
        captured = {}

        async def fake_send(to, result, request_id, msg_id):
            captured["result"] = result

        monkeypatch.setattr(agent, "send_capability_response", fake_send)
        msg = _make_lighting_message("lights_color", "make the lights red")
        await agent._handle_capability_request(msg)

        assert captured["result"]["status"] == "success"
        assert captured["result"]["color"] == "red"

    @pytest.mark.asyncio
    async def test_unknown_capability_ignored(self, monkeypatch):
        """Unknown capabilities are silently ignored."""
        backend = MockBackend()
        agent = LightingAgent(backend=backend, ai_client=DummyAIClient())
        captured = {}

        async def fake_send(to, result, request_id, msg_id):
            captured["sent"] = True

        monkeypatch.setattr(agent, "send_capability_response", fake_send)
        msg = _make_lighting_message("weather_forecast")
        await agent._handle_capability_request(msg)

        assert "sent" not in captured

    @pytest.mark.asyncio
    async def test_invalid_prompt_type(self, monkeypatch):
        """Non-string prompt sends error."""
        backend = MockBackend()
        agent = LightingAgent(backend=backend, ai_client=DummyAIClient())
        errors = []

        async def fake_error(to, err, request_id):
            errors.append(err)

        monkeypatch.setattr(agent, "send_error", fake_error)
        msg = Message(
            from_agent="tester",
            to_agent="LightingAgent",
            message_type="capability_request",
            content={"capability": "lights_on", "data": {"prompt": 42}},
            request_id="req-1",
        )
        await agent._handle_capability_request(msg)
        assert len(errors) == 1


# ---------------------------------------------------------------------------
# Tests: color command processing
# ---------------------------------------------------------------------------

class TestColorCommandProcessing:
    """Test the _process_color_command method."""

    @pytest.mark.asyncio
    async def test_color_command_bright_modifier(self, monkeypatch):
        """Bright modifier increases brightness."""
        backend = MockBackend()
        ai = DummyAIClient('{"color": "blue", "brightness": "bright", "target": "all"}')
        agent = LightingAgent(backend=backend, ai_client=ai)

        result = await agent._process_color_command("bright blue")
        assert result["status"] == "success"
        assert result["brightness"] == "bright"
        # Should have called set_all_color + set_all_brightness
        color_calls = [c for c in backend.calls if c[0] == "set_all_color"]
        brightness_calls = [c for c in backend.calls if c[0] == "set_all_brightness"]
        assert len(color_calls) >= 1
        assert len(brightness_calls) >= 1

    @pytest.mark.asyncio
    async def test_color_command_dim_modifier(self, monkeypatch):
        """Dim modifier decreases brightness."""
        backend = MockBackend()
        ai = DummyAIClient('{"color": "green", "brightness": "dim", "target": "all"}')
        agent = LightingAgent(backend=backend, ai_client=ai)

        result = await agent._process_color_command("dim green")
        assert result["status"] == "success"
        assert result["brightness"] == "dim"

    @pytest.mark.asyncio
    async def test_color_command_specific_target(self, monkeypatch):
        """Color command targeting a specific light."""
        backend = MockBackend()
        ai = DummyAIClient('{"color": "red", "brightness": "normal", "target": "Desk Lamp"}')
        agent = LightingAgent(backend=backend, ai_client=ai)

        result = await agent._process_color_command("make desk lamp red")
        assert result["status"] == "success"
        color_calls = [c for c in backend.calls if c[0] == "set_color_name"]
        assert len(color_calls) >= 1
        assert color_calls[0][1] == "Desk Lamp"

    @pytest.mark.asyncio
    async def test_color_command_white_defaults_to_bright(self, monkeypatch):
        """White color defaults to bright when brightness is normal."""
        backend = MockBackend()
        ai = DummyAIClient('{"color": "white", "brightness": "normal", "target": "all"}')
        agent = LightingAgent(backend=backend, ai_client=ai)

        result = await agent._process_color_command("white lights")
        assert result["status"] == "success"
        assert result["brightness"] == "bright"

    @pytest.mark.asyncio
    async def test_color_command_unknown_color_fallback(self, monkeypatch):
        """Unknown color triggers fallback extraction."""
        backend = MockBackend()
        ai = DummyAIClient('{"color": "magenta", "brightness": "normal", "target": "all"}')
        agent = LightingAgent(backend=backend, ai_client=ai)

        # "magenta" is not in the color map, fallback should try to extract
        result = await agent._process_color_command("set lights to magenta")
        # The fallback should fail since magenta isn't in the map either
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_color_command_ai_parse_failure_fallback(self, monkeypatch):
        """When AI returns unparseable JSON, fallback extraction is used."""
        backend = MockBackend()
        ai = DummyAIClient("I don't understand")
        agent = LightingAgent(backend=backend, ai_client=ai)

        result = await agent._process_color_command("make lights blue please")
        # Fallback should find "blue" in the prompt
        assert result["status"] == "success"
        assert result.get("color") == "blue"


# ---------------------------------------------------------------------------
# Tests: color extraction helpers
# ---------------------------------------------------------------------------

class TestColorExtractionHelpers:
    """Test helper methods for color extraction."""

    def test_extract_color_from_prompt_found(self):
        backend = MockBackend()
        agent = LightingAgent(backend=backend, ai_client=DummyAIClient())
        assert agent._extract_color_from_prompt("make it red") == "red"
        assert agent._extract_color_from_prompt("I want blue lights") == "blue"
        assert agent._extract_color_from_prompt("set to green") == "green"

    def test_extract_color_from_prompt_not_found(self):
        backend = MockBackend()
        agent = LightingAgent(backend=backend, ai_client=DummyAIClient())
        assert agent._extract_color_from_prompt("turn on the lights") is None
        assert agent._extract_color_from_prompt("make it brighter") is None

    def test_find_closest_color_common_variations(self):
        backend = MockBackend()
        agent = LightingAgent(backend=backend, ai_client=DummyAIClient())
        assert agent._find_closest_color("yell") == "yellow"
        assert agent._find_closest_color("blu") == "blue"
        assert agent._find_closest_color("purp") == "purple"
        assert agent._find_closest_color("grn") == "green"
        assert agent._find_closest_color("oran") == "orange"

    def test_find_closest_color_no_match(self):
        backend = MockBackend()
        agent = LightingAgent(backend=backend, ai_client=DummyAIClient())
        assert agent._find_closest_color("magenta") is None
        assert agent._find_closest_color("xyz") is None


# ---------------------------------------------------------------------------
# Tests: brightness command processing
# ---------------------------------------------------------------------------

class TestBrightnessCommandProcessing:
    """Test _process_brightness_command."""

    @pytest.mark.asyncio
    async def test_brightness_percentage(self):
        """Percentage values (0-100) are converted to 0-254 range."""
        backend = MockBackend()
        agent = LightingAgent(backend=backend, ai_client=DummyAIClient())
        result = await agent._process_brightness_command("set to 100")
        assert result["brightness"] == 254

    @pytest.mark.asyncio
    async def test_brightness_raw_value(self):
        """Values > 100 and <= 254 are used as raw brightness."""
        backend = MockBackend()
        agent = LightingAgent(backend=backend, ai_client=DummyAIClient())
        result = await agent._process_brightness_command("set to 200")
        assert result["brightness"] == 200

    @pytest.mark.asyncio
    async def test_brightness_zero(self):
        """Zero brightness effectively turns off."""
        backend = MockBackend()
        agent = LightingAgent(backend=backend, ai_client=DummyAIClient())
        result = await agent._process_brightness_command("brightness 0")
        assert result["brightness"] == 0


# ---------------------------------------------------------------------------
# Tests: create_lighting_agent factory
# ---------------------------------------------------------------------------

class TestCreateLightingAgent:
    """Test the factory function for creating agents."""

    def test_unsupported_backend_type(self):
        """Unsupported backend type raises ValueError."""
        with pytest.raises(ValueError, match="Unsupported backend type"):
            create_lighting_agent("unknown_backend", ai_client=DummyAIClient())

    def test_phillips_hue_missing_bridge_ip(self):
        """Phillips Hue without bridge_ip raises ValueError."""
        with pytest.raises(ValueError, match="bridge_ip is required"):
            create_lighting_agent("phillips_hue", ai_client=DummyAIClient())


# ---------------------------------------------------------------------------
# Tests: error handling in capability request
# ---------------------------------------------------------------------------

class TestLightingAgentErrors:
    """Test error handling in capability requests."""

    @pytest.mark.asyncio
    async def test_exception_in_processing_returns_error_response(self, monkeypatch):
        """Exceptions during processing return an error AgentResponse."""
        backend = MockBackend()
        agent = LightingAgent(backend=backend, ai_client=DummyAIClient())

        # Make _process_on_command raise
        async def fail(*args, **kwargs):
            raise RuntimeError("Hardware failure")

        monkeypatch.setattr(agent, "_process_on_command", fail)
        captured = {}

        async def fake_send(to, result, request_id, msg_id):
            captured["result"] = result

        monkeypatch.setattr(agent, "send_capability_response", fake_send)
        msg = _make_lighting_message("lights_on", "turn on")
        await agent._handle_capability_request(msg)

        assert captured["result"]["success"] is False
        assert "Hardware failure" in captured["result"]["response"]

    @pytest.mark.asyncio
    async def test_context_enhancement_with_previous_results(self, monkeypatch):
        """Previous results from DAG execution enhance the prompt."""
        backend = MockBackend()
        agent = LightingAgent(backend=backend, ai_client=DummyAIClient())
        captured_prompts = []

        original_process = agent._process_on_command

        async def spy_process(prompt):
            captured_prompts.append(prompt)
            return await original_process(prompt)

        monkeypatch.setattr(agent, "_process_on_command", spy_process)

        async def fake_send(to, result, request_id, msg_id):
            pass

        monkeypatch.setattr(agent, "send_capability_response", fake_send)
        context = {
            "previous_results": [
                {
                    "capability": "weather",
                    "from_agent": "SearchAgent",
                    "result": {"response": "It's sunny"},
                }
            ]
        }
        msg = _make_lighting_message("lights_on", "turn on lights", context=context)
        await agent._handle_capability_request(msg)

        # The prompt should be enhanced with context
        assert len(captured_prompts) == 1
        assert "sunny" in captured_prompts[0].lower() or "previous" in captured_prompts[0].lower()
