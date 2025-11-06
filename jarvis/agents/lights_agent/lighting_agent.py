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
        result = {"status": "capability_handled", "capability": capability}

        await self.send_capability_response(
            message.from_agent, result, message.request_id, message.id
        )


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
