"""Unified lighting agent that supports multiple backends."""

from __future__ import annotations

import asyncio
import functools
from typing import Any, Dict, List, Optional
from ..base import NetworkAgent
from ..message import Message
from ...logging import JarvisLogger
from ...ai_clients.base import BaseAIClient
from .backend import BaseLightingBackend
from .phillips_hue_backend import PhillipsHueBackend
from .yeelight_backend import YeelightBackend
from ..response import AgentResponse, ErrorInfo


class LightingAgent(NetworkAgent):
    """Unified lighting agent supporting multiple backends (Phillips Hue, Yeelight, etc.)."""

    def __init__(
        self,
        backend: BaseLightingBackend,
        ai_client: BaseAIClient,
        logger: JarvisLogger | None = None,
    ) -> None:
        super().__init__("LightingAgent", logger)
        self.backend = backend
        self.ai_client = ai_client
        self.color_map = backend.get_color_map()
        self._is_yeelight = isinstance(backend, YeelightBackend)

        self.intent_map = {
            "turn_on_all_lights": self._turn_on_all_lights,
            "turn_off_all_lights": self._turn_off_all_lights,
            "set_all_brightness": self._set_all_brightness,
            "set_all_color": self._set_all_color,
            "turn_on_light": self._turn_on_light,
            "turn_off_light": self._turn_off_light,
            "toggle_light": self._toggle_light,
            "set_brightness": self._set_brightness,
            "set_color_name": self._set_color_name,
            "list_lights": self._list_lights,
        }

    @property
    def description(self) -> str:
        backend_type = type(self.backend).__name__.replace("Backend", "")
        return f"Unified lighting control agent using {backend_type} backend"

    @property
    def capabilities(self) -> set[str]:
        return {
            "lights_on",
            "lights_off",
            "lights_brightness",
            "lights_color",
            "lights_list",
            "lights_status",
            "lights_toggle",
        }

    async def run_capability(self, capability: str, **kwargs: Any) -> Any:
        """Execute a capability using the agent's function map."""
        func = self.intent_map.get(capability)
        if not func:
            raise NotImplementedError(
                f"{self.__class__.__name__} does not implement capability '{capability}'"
            )

        if asyncio.iscoroutinefunction(func):
            return await func(**kwargs)

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, functools.partial(func, **kwargs))

    def _normalize_brightness(self, brightness: int) -> int:
        """Convert brightness from standard 0-254 range to backend-specific range.

        Standard range: 0-254 (Hue-compatible)
        - Hue: 0-254 (pass through)
        - Yeelight: 1-100 (convert proportionally)
        """
        if self._is_yeelight:
            if brightness == 0:
                return 0
            yeelight_value = round((brightness / 254) * 100)
            return max(1, min(100, yeelight_value))
        return brightness

    def _turn_on_all_lights(self) -> str:
        """Turn on all lights."""
        return self.backend.turn_on_all_lights()

    def _turn_off_all_lights(self) -> str:
        """Turn off all lights."""
        return self.backend.turn_off_all_lights()

    def _set_all_brightness(self, brightness: int) -> str:
        """Set brightness for all lights."""
        normalized = self._normalize_brightness(brightness)
        return self.backend.set_all_brightness(normalized)

    def _set_all_color(self, color_name: str) -> str:
        """Set color for all lights."""
        return self.backend.set_all_color(color_name)

    def _turn_on_light(self, light_name: str) -> str:
        """Turn on a specific light."""
        return self.backend.turn_on_light(light_name)

    def _turn_off_light(self, light_name: str) -> str:
        """Turn off a specific light."""
        return self.backend.turn_off_light(light_name)

    def _toggle_light(self, light_name: str) -> str:
        """Toggle a light on/off."""
        return self.backend.toggle_light(light_name)

    def _set_brightness(self, light_name: str, brightness: int) -> str:
        """Set brightness of a specific light."""
        normalized = self._normalize_brightness(brightness)
        return self.backend.set_brightness(light_name, normalized)

    def _set_color_name(self, light_name: str, color_name: str) -> str:
        """Set color of a specific light."""
        return self.backend.set_color_name(light_name, color_name)

    def _list_lights(self) -> Dict[str, Any]:
        """List all lights."""
        return self.backend.list_lights()

    async def _handle_capability_request(self, message: Message) -> None:
        """Handle incoming capability requests."""
        capability = message.content.get("capability")
        data = message.content.get("data", {})

        if capability not in self.capabilities:
            return

        self.logger.log("INFO", f"Handling capability: {capability}", str(data))

        prompt = data.get("prompt", "")
        if not isinstance(prompt, str):
            await self.send_error(
                message.from_agent, "Invalid or missing prompt", message.request_id
            )
            return

        # Extract context and enhance prompt with previous results from DAG
        context_info = self._extract_context_from_message(message)
        previous_results = context_info.get("previous_results", [])

        if previous_results:
            prompt = self._enhance_prompt_with_context(prompt, previous_results)
            self.logger.log(
                "INFO",
                "Enhanced lighting command with previous results",
                f"Previous steps: {len(previous_results)}",
            )

        try:
            # Process the command based on capability
            if capability == "lights_color":
                result = await self._process_color_command(prompt)
            elif capability == "lights_on":
                result = await self._process_on_command(prompt)
            elif capability == "lights_off":
                result = await self._process_off_command(prompt)
            elif capability == "lights_brightness":
                result = await self._process_brightness_command(prompt)
            elif capability == "lights_toggle":
                result = await self._process_toggle_command(prompt)
            elif capability == "lights_list":
                lights_data = self._list_lights()
                result = AgentResponse.success_response(
                    response=f"Found {len(lights_data.get('lights', []))} lights",
                    data=lights_data,
                ).to_dict()
            elif capability == "lights_status":
                lights_data = self._list_lights()
                result = AgentResponse.success_response(
                    response="Lighting system is online",
                    data={"status": "online", "lights": lights_data},
                ).to_dict()
            else:
                result = AgentResponse.success_response(
                    response=f"Capability {capability} handled",
                    metadata={"capability": capability},
                ).to_dict()

            await self.send_capability_response(
                message.from_agent, result, message.request_id, message.id
            )
        except Exception as e:
            self.logger.log("ERROR", f"Error processing {capability}", str(e))
            error_response = AgentResponse.error_response(
                response=f"Error: {str(e)}", error=ErrorInfo.from_exception(e)
            ).to_dict()
            await self.send_capability_response(
                message.from_agent, error_response, message.request_id, message.id
            )

    async def _process_color_command(self, prompt: str) -> Dict[str, Any]:
        """Process a color command like 'make lights yellow' or 'bright yellow'."""
        # Use AI to extract color and brightness from prompt
        system_prompt = f"""You are a lighting control assistant. Parse the user's color command and extract:
1. Color name (from available colors: {', '.join(self.color_map.keys())})
2. Brightness level if mentioned (bright, dim, etc.)
3. Target (all lights or specific light name)

Return JSON: {{"color": "color_name", "brightness": "normal|bright|dim", "target": "all|light_name"}}
If color not found, use closest match. Default brightness is "normal".
IMPORTANT: When the color is "white", default brightness should be "bright" to achieve
super bright white light like in the Yeelight app."""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ]

        try:
            response = await self.ai_client.weak_chat(messages, [])
            content = (
                response[0].content
                if hasattr(response[0], "content")
                else str(response[0])
            )

            # Parse JSON from response
            from ...utils import extract_json_from_text

            parsed = extract_json_from_text(content)

            if not parsed:
                # Fallback: try to extract color name directly
                color_name = self._extract_color_from_prompt(prompt)
                parsed = {"color": color_name, "brightness": "normal", "target": "all"}

            color_name = parsed.get("color", "").lower()
            brightness_mod = parsed.get("brightness", "normal")
            target = parsed.get("target", "all")

            # Validate color
            if color_name not in self.color_map:
                # Try to find closest match
                color_name = self._find_closest_color(color_name)

            if not color_name or color_name not in self.color_map:
                return {
                    "status": "error",
                    "message": f"Unknown color. Available: {', '.join(self.color_map.keys())}",
                }

            # For white color, default to bright unless explicitly dimmed
            # The backend will handle white specially (color temp + max brightness)
            # but we ensure brightness_mod reflects this for consistency
            if color_name == "white" and brightness_mod == "normal":
                brightness_mod = "bright"

            # Execute the command
            if target == "all" or target is None:
                result_msg = self._set_all_color(color_name)
                # Adjust brightness if requested (for non-white colors or explicit dim)
                # Note: White is already set to max brightness by backend, so only adjust if dimming
                if brightness_mod == "bright" and color_name != "white":
                    # Increase brightness to ~90%
                    brightness_val = int(254 * 0.9)
                    brightness_result = self._set_all_brightness(brightness_val)
                    result_msg += f" {brightness_result}"
                elif brightness_mod == "dim":
                    brightness_val = int(254 * 0.3)
                    brightness_result = self._set_all_brightness(brightness_val)
                    result_msg += f" {brightness_result}"
            else:
                result_msg = self._set_color_name(target, color_name)
                # Adjust brightness if requested (for non-white colors or explicit dim)
                # Note: White is already set to max brightness by backend, so only adjust if dimming
                if brightness_mod == "bright" and color_name != "white":
                    brightness_val = int(254 * 0.9)
                    self._set_brightness(target, brightness_val)
                elif brightness_mod == "dim":
                    brightness_val = int(254 * 0.3)
                    self._set_brightness(target, brightness_val)

            return {
                "status": "success",
                "message": result_msg,
                "color": color_name,
                "brightness": brightness_mod,
            }
        except Exception as e:
            self.logger.log("ERROR", "Error parsing color command", str(e))
            # Fallback: try simple extraction
            color_name = self._extract_color_from_prompt(prompt)
            if color_name:
                result_msg = self._set_all_color(color_name)
                return {"status": "success", "message": result_msg, "color": color_name}
            return {"status": "error", "message": f"Could not parse command: {str(e)}"}

    def _extract_color_from_prompt(self, prompt: str) -> Optional[str]:
        """Simple fallback: extract color name from prompt."""
        prompt_lower = prompt.lower()
        for color in self.color_map.keys():
            if color.lower() in prompt_lower:
                return color
        return None

    def _find_closest_color(self, color_input: str) -> Optional[str]:
        """Find closest matching color name."""
        color_input_lower = color_input.lower()
        # Common variations
        color_variations = {
            "yellow": "yellow",
            "yell": "yellow",
            "yel": "yellow",
            "blu": "blue",
            "bl": "blue",
            "red": "red",
            "grn": "green",
            "gre": "green",
            "whit": "white",
            "purp": "purple",
            "pink": "pink",
            "oran": "orange",
        }

        for variant, color in color_variations.items():
            if variant in color_input_lower and color in self.color_map:
                return color

        return None

    async def _process_on_command(self, prompt: str) -> Dict[str, Any]:
        """Process lights on command."""
        result_msg = self._turn_on_all_lights()
        return {"status": "success", "message": result_msg}

    async def _process_off_command(self, prompt: str) -> Dict[str, Any]:
        """Process lights off command."""
        result_msg = self._turn_off_all_lights()
        return {"status": "success", "message": result_msg}

    async def _process_brightness_command(self, prompt: str) -> Dict[str, Any]:
        """Process brightness command."""
        # Extract brightness value (0-100 or 0-254)
        # Default to 50% if not specified
        brightness = 127  # 50% of 254

        # Try to extract number
        import re

        numbers = re.findall(r"\d+", prompt)
        if numbers:
            brightness_val = int(numbers[0])
            if brightness_val <= 100:
                # Convert from 0-100 to 0-254
                brightness = int((brightness_val / 100) * 254)
            elif brightness_val <= 254:
                brightness = brightness_val

        result_msg = self._set_all_brightness(brightness)
        return {"status": "success", "message": result_msg, "brightness": brightness}

    async def _process_toggle_command(self, prompt: str) -> Dict[str, Any]:
        """Process toggle command."""
        # Simple toggle all lights
        result_msg = "Toggled lights"  # Would need backend support for toggle all
        return {"status": "success", "message": result_msg}


def create_lighting_agent(
    backend_type: str,
    ai_client: BaseAIClient,
    logger: JarvisLogger | None = None,
    **backend_kwargs: Any,
) -> LightingAgent:
    backend: BaseLightingBackend

    if backend_type.lower() == "phillips_hue":
        bridge_ip = backend_kwargs.get("bridge_ip")
        if not bridge_ip:
            raise ValueError("bridge_ip is required for Phillips Hue backend")
        backend = PhillipsHueBackend(
            bridge_ip=bridge_ip,
            username=backend_kwargs.get("username"),
            logger=logger,
        )
    elif backend_type.lower() == "yeelight":
        bulb_ips = backend_kwargs.get("bulb_ips")
        backend = YeelightBackend(bulb_ips=bulb_ips, logger=logger)
    else:
        raise ValueError(
            f"Unsupported backend type: {backend_type}. "
            f"Supported: 'phillips_hue', 'yeelight'"
        )

    return LightingAgent(backend=backend, ai_client=ai_client, logger=logger)
