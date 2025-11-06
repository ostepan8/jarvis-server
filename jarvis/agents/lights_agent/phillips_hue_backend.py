"""Phillips Hue backend implementation."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Tuple, Optional
from phue import Bridge
from .backend import BaseLightingBackend
from ...logging import JarvisLogger


class PhillipsHueBackend(BaseLightingBackend):
    COLOR_MAP = {
        "red": {"hue": 0, "sat": 254},
        "orange": {"hue": 8000, "sat": 254},
        "yellow": {"hue": 12750, "sat": 254},
        "green": {"hue": 25500, "sat": 254},
        "blue": {"hue": 46920, "sat": 254},
        "purple": {"hue": 56100, "sat": 254},
        "pink": {"hue": 62000, "sat": 254},
        "white": {"hue": 0, "sat": 0},
    }

    def __init__(
        self,
        bridge_ip: str,
        username: str | None = None,
        logger: Optional[JarvisLogger] = None,
    ):
        """Initialize the Hue bridge connection."""
        self.logger = logger or JarvisLogger()
        if username:
            self.bridge = Bridge(bridge_ip, username=username)
        else:
            self.bridge = Bridge(bridge_ip)
        try:
            self.bridge.connect()
        except Exception as e:
            self.logger.log(
                "WARNING", "Failed to connect to Hue bridge initially", str(e)
            )

    def get_color_map(self) -> Dict[str, Dict[str, int]]:
        """Return the color mapping dictionary."""
        return self.COLOR_MAP.copy()

    def _execute_light_operations_parallel(
        self, operation_name: str, light_ids: List[int], operation
    ) -> Tuple[int, List[Tuple[int, str]]]:
        """Execute operation on multiple lights in parallel using ThreadPoolExecutor.
        Returns (success_count, [(light_id, error), ...])."""
        if not light_ids:
            return (0, [])

        successes = 0
        failures = []

        with ThreadPoolExecutor(max_workers=min(len(light_ids), 10)) as executor:
            future_to_light_id = {
                executor.submit(operation, light_id): light_id for light_id in light_ids
            }

            for future in as_completed(future_to_light_id):
                light_id = future_to_light_id[future]
                try:
                    future.result()
                    successes += 1
                except Exception as e:
                    error_msg = str(e)
                    self.logger.log(
                        "WARNING",
                        f"{operation_name} failed for light {light_id}",
                        error_msg,
                    )
                    failures.append((light_id, error_msg))

        return (successes, failures)

    def turn_on_all_lights(self) -> str:
        """Turn on all lights in the system."""
        try:
            lights = self.bridge.get_light()
            light_ids = [int(light_id) for light_id in lights.keys()]
            if not light_ids:
                return "No lights found"

            def turn_on_light(light_id: int):
                self.bridge.set_light(light_id, "on", True)

            successes, failures = self._execute_light_operations_parallel(
                "turn_on", light_ids, turn_on_light
            )

            if successes == len(light_ids):
                return f"Turned on all {successes} lights"
            elif successes > 0:
                failure_msg = ", ".join([f"light_{lid}" for lid, _ in failures])
                return f"Turned on {successes}/{len(light_ids)} lights (failed: {failure_msg})"
            else:
                failure_details = ", ".join(
                    [f"light_{lid}: {err[:50]}" for lid, err in failures]
                )
                return f"Failed to turn on all lights: {failure_details}"
        except Exception as e:
            return f"Failed to turn on all lights: {str(e)}"

    def turn_off_all_lights(self) -> str:
        """Turn off all lights in the system."""
        try:
            lights = self.bridge.get_light()
            light_ids = [int(light_id) for light_id in lights.keys()]
            if not light_ids:
                return "No lights found"

            def turn_off_light(light_id: int):
                self.bridge.set_light(light_id, "on", False)

            successes, failures = self._execute_light_operations_parallel(
                "turn_off", light_ids, turn_off_light
            )

            if successes == len(light_ids):
                return f"Turned off all {successes} lights"
            elif successes > 0:
                failure_msg = ", ".join([f"light_{lid}" for lid, _ in failures])
                return f"Turned off {successes}/{len(light_ids)} lights (failed: {failure_msg})"
            else:
                failure_details = ", ".join(
                    [f"light_{lid}: {err[:50]}" for lid, err in failures]
                )
                return f"Failed to turn off all lights: {failure_details}"
        except Exception as e:
            return f"Failed to turn off all lights: {str(e)}"

    def set_all_brightness(self, brightness: int) -> str:
        """Set brightness for all lights."""
        try:
            brightness = max(0, min(254, brightness))
            lights = self.bridge.get_light()
            light_ids = [int(light_id) for light_id in lights.keys()]
            if not light_ids:
                return "No lights found"

            def set_brightness_light(light_id: int):
                if brightness == 0:
                    self.bridge.set_light(light_id, "on", False)
                else:
                    self.bridge.set_light(light_id, "on", True)
                    self.bridge.set_light(light_id, "bri", brightness)

            successes, failures = self._execute_light_operations_parallel(
                "set_brightness", light_ids, set_brightness_light
            )

            if successes == len(light_ids):
                return f"Set brightness of all {successes} lights to {brightness}"
            elif successes > 0:
                failure_msg = ", ".join([f"light_{lid}" for lid, _ in failures])
                return (
                    f"Set brightness of {successes}/{len(light_ids)} lights to "
                    f"{brightness} (failed: {failure_msg})"
                )
            else:
                failure_details = ", ".join(
                    [f"light_{lid}: {err[:50]}" for lid, err in failures]
                )
                return f"Failed to set brightness: {failure_details}"
        except Exception as e:
            return f"Failed to set all brightness: {str(e)}"

    def set_all_color(self, color_name: str) -> str:
        """Set color for all lights."""
        color_name = color_name.strip().lower()
        if color_name == "read":
            color_name = "red"

        try:
            if color_name not in self.COLOR_MAP:
                available_colors = ", ".join(self.COLOR_MAP.keys())
                return f"Unknown color '{color_name}'. Available colors: {available_colors}"

            color_data = self.COLOR_MAP[color_name]
            lights = self.bridge.get_light()
            light_ids = [int(light_id) for light_id in lights.keys()]
            if not light_ids:
                return "No lights found"

            def set_color_light(light_id: int):
                self.bridge.set_light(light_id, "on", True)
                self.bridge.set_light(light_id, "hue", color_data["hue"])
                self.bridge.set_light(light_id, "sat", color_data["sat"])

            successes, failures = self._execute_light_operations_parallel(
                "set_color", light_ids, set_color_light
            )

            if successes == len(light_ids):
                return f"Set all {successes} lights to {color_name}"
            elif successes > 0:
                failure_msg = ", ".join([f"light_{lid}" for lid, _ in failures])
                return f"Set {successes}/{len(light_ids)} lights to {color_name} (failed: {failure_msg})"
            else:
                failure_details = ", ".join(
                    [f"light_{lid}: {err[:50]}" for lid, err in failures]
                )
                return f"Failed to set all lights color: {failure_details}"
        except Exception as e:
            return f"Failed to set all lights color: {str(e)}"

    def turn_on_light(self, light_name: str) -> str:
        """Turn on a specific light."""
        try:
            self.bridge.set_light(light_name, "on", True)
            return f"Turned on {light_name}"
        except Exception as e:
            return f"Failed to turn on {light_name}: {str(e)}"

    def turn_off_light(self, light_name: str) -> str:
        """Turn off a specific light."""
        try:
            self.bridge.set_light(light_name, "on", False)
            return f"Turned off {light_name}"
        except Exception as e:
            return f"Failed to turn off {light_name}: {str(e)}"

    def toggle_light(self, light_name: str) -> str:
        """Toggle a light on/off."""
        try:
            current_state = self.bridge.get_light(light_name)["state"]["on"]
            new_state = not current_state
            self.bridge.set_light(light_name, "on", new_state)
            return f"Toggled {light_name} {'on' if new_state else 'off'}"
        except Exception as e:
            return f"Failed to toggle {light_name}: {str(e)}"

    def set_brightness(self, light_name: str, brightness: int) -> str:
        """Set brightness of a specific light."""
        try:
            brightness = max(0, min(254, brightness))
            if brightness == 0:
                self.bridge.set_light(light_name, "on", False)
                return f"Turned off {light_name} (brightness 0)"
            else:
                self.bridge.set_light(light_name, "on", True)
                self.bridge.set_light(light_name, "bri", brightness)
                return f"Set brightness of {light_name} to {brightness}"
        except Exception as e:
            return f"Failed to set brightness: {str(e)}"

    def set_color_name(self, light_name: str, color_name: str) -> str:
        """Set light color using common color names."""
        try:
            color_name = color_name.lower()
            if color_name not in self.COLOR_MAP:
                available_colors = ", ".join(self.COLOR_MAP.keys())
                return f"Unknown color '{color_name}'. Available colors: {available_colors}"

            color_data = self.COLOR_MAP[color_name]
            self.bridge.set_light(light_name, "on", True)
            self.bridge.set_light(light_name, "hue", color_data["hue"])
            self.bridge.set_light(light_name, "sat", color_data["sat"])
            return f"Set {light_name} to {color_name}"
        except Exception as e:
            return f"Failed to set color: {str(e)}"

    def list_lights(self) -> Dict[str, Any]:
        """List all lights with their IDs and names."""
        try:
            lights = self.bridge.get_light_objects("name")
            light_info = {}
            for name, light_obj in lights.items():
                light_info[name] = {
                    "id": light_obj.light_id,
                    "name": name,
                    "on": light_obj.on,
                    "reachable": getattr(light_obj, "reachable", True),
                }
            return light_info
        except Exception as e:
            return {"error": f"Failed to list lights: {str(e)}"}
