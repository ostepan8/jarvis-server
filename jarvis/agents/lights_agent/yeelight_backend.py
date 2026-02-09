"""Yeelight backend implementation."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Tuple, Optional
from yeelight import Bulb, discover_bulbs
from .backend import BaseLightingBackend
from ...logging import JarvisLogger


class YeelightBackend(BaseLightingBackend):
    """Backend implementation for Yeelight bulbs."""

    COLOR_MAP = {
        "red": {"r": 255, "g": 0, "b": 0},
        "orange": {"r": 255, "g": 165, "b": 0},
        "yellow": {"r": 255, "g": 255, "b": 0},
        "green": {"r": 0, "g": 255, "b": 0},
        "blue": {"r": 0, "g": 0, "b": 255},
        "purple": {"r": 128, "g": 0, "b": 128},
        "pink": {"r": 255, "g": 192, "b": 203},
        "white": {"r": 255, "g": 255, "b": 255},
    }

    def __init__(
        self, bulb_ips: List[str] | None = None, logger: Optional[JarvisLogger] = None
    ):
        self.logger = logger or JarvisLogger()
        self.bulbs: Dict[str, Bulb] = {}
        if bulb_ips:
            for ip in bulb_ips:
                try:
                    bulb = Bulb(ip)
                    bulb.get_properties()
                    self.bulbs[ip] = bulb
                except Exception as e:
                    self.logger.log(
                        "WARNING", f"Failed to connect to Yeelight bulb {ip}", str(e)
                    )
        else:
            try:
                discovered = discover_bulbs(timeout=3)
                for bulb_info in discovered:
                    ip = bulb_info["ip"]
                    try:
                        bulb = Bulb(ip)
                        bulb.get_properties()
                        self.bulbs[ip] = bulb
                    except Exception as e:
                        self.logger.log(
                            "WARNING",
                            f"Failed to connect to discovered bulb {ip}",
                            str(e),
                        )
            except Exception as e:
                self.logger.log("WARNING", "Yeelight auto-discovery failed", str(e))

    def get_color_map(self) -> Dict[str, Dict[str, int]]:
        """Return the color mapping dictionary."""
        return self.COLOR_MAP.copy()

    def _get_bulbs_by_name(
        self, light_name: str | None = None
    ) -> List[Tuple[str, Bulb]]:
        """Return list of (ip, bulb) tuples."""
        if light_name is None:
            return [(ip, bulb) for ip, bulb in self.bulbs.items()]
        if light_name in self.bulbs:
            return [(light_name, self.bulbs[light_name])]
        return [(ip, bulb) for ip, bulb in self.bulbs.items()]

    def _reconnect_bulb(self, ip: str) -> Bulb | None:
        """Attempt to reconnect to a bulb by creating a fresh connection."""
        try:
            new_bulb = Bulb(ip)
            new_bulb.get_properties()  # Test the connection
            self.bulbs[ip] = new_bulb
            self.logger.log("INFO", f"Reconnected to bulb {ip}")
            return new_bulb
        except Exception as e:
            self.logger.log("WARNING", f"Failed to reconnect to bulb {ip}", str(e))
            return None

    def _execute_bulb_operations_parallel(
        self, operation_name: str, bulbs: List[Tuple[str, Bulb]], operation
    ) -> Tuple[int, List[Tuple[str, str]]]:
        """Execute operation on multiple bulbs in parallel using ThreadPoolExecutor.
        Returns (success_count, [(ip, error), ...]).
        
        Automatically attempts reconnection if a bulb connection is stale."""
        if not bulbs:
            return (0, [])

        successes = 0
        failures = []

        def execute_with_retry(ip: str, bulb: Bulb):
            """Execute operation with one reconnection attempt on failure."""
            try:
                operation(bulb)
                return True, None
            except Exception as e:
                error_msg = str(e).lower()
                # Check for connection-related errors that warrant a retry
                if "closed" in error_msg or "connection" in error_msg or "socket" in error_msg:
                    self.logger.log(
                        "INFO", f"Connection lost to {ip}, attempting reconnect..."
                    )
                    new_bulb = self._reconnect_bulb(ip)
                    if new_bulb:
                        try:
                            operation(new_bulb)
                            return True, None
                        except Exception as retry_e:
                            return False, str(retry_e)
                return False, str(e)

        with ThreadPoolExecutor(max_workers=min(len(bulbs), 10)) as executor:
            future_to_ip = {
                executor.submit(execute_with_retry, ip, bulb): ip 
                for ip, bulb in bulbs
            }

            for future in as_completed(future_to_ip):
                ip = future_to_ip[future]
                try:
                    success, error_msg = future.result()
                    if success:
                        successes += 1
                    else:
                        self.logger.log(
                            "WARNING", f"{operation_name} failed for bulb {ip}", error_msg
                        )
                        failures.append((ip, error_msg))
                except Exception as e:
                    error_msg = str(e)
                    self.logger.log(
                        "WARNING", f"{operation_name} failed for bulb {ip}", error_msg
                    )
                    failures.append((ip, error_msg))

        return (successes, failures)

    def turn_on_all_lights(self) -> str:
        """Turn on all lights in the system."""
        try:
            bulbs = self._get_bulbs_by_name(None)
            if not bulbs:
                return "No lights found"

            def turn_on_bulb(bulb: Bulb):
                bulb.turn_on()

            successes, failures = self._execute_bulb_operations_parallel(
                "turn_on", bulbs, turn_on_bulb
            )

            if successes == len(bulbs):
                return f"Turned on all {successes} lights"
            elif successes > 0:
                failure_msg = ", ".join([f"{ip}" for ip, _ in failures])
                return (
                    f"Turned on {successes}/{len(bulbs)} lights (failed: {failure_msg})"
                )
            else:
                failure_details = ", ".join(
                    [f"{ip}: {err[:50]}" for ip, err in failures]
                )
                return f"Failed to turn on all lights: {failure_details}"
        except Exception as e:
            return f"Failed to turn on all lights: {str(e)}"

    def turn_off_all_lights(self) -> str:
        """Turn off all lights in the system."""
        try:
            bulbs = self._get_bulbs_by_name(None)
            if not bulbs:
                return "No lights found"

            def turn_off_bulb(bulb: Bulb):
                bulb.turn_off()

            successes, failures = self._execute_bulb_operations_parallel(
                "turn_off", bulbs, turn_off_bulb
            )

            if successes == len(bulbs):
                return f"Turned off all {successes} lights"
            elif successes > 0:
                failure_msg = ", ".join([f"{ip}" for ip, _ in failures])
                return f"Turned off {successes}/{len(bulbs)} lights (failed: {failure_msg})"
            else:
                failure_details = ", ".join(
                    [f"{ip}: {err[:50]}" for ip, err in failures]
                )
                return f"Failed to turn off all lights: {failure_details}"
        except Exception as e:
            return f"Failed to turn off all lights: {str(e)}"

    def set_all_brightness(self, brightness: int) -> str:
        """Set brightness for all lights."""
        try:
            if brightness == 0:
                return self.turn_off_all_lights()
            brightness = max(1, min(100, brightness))

            bulbs = self._get_bulbs_by_name(None)
            if not bulbs:
                return "No lights found"

            def set_brightness_bulb(bulb: Bulb):
                bulb.set_brightness(brightness)
                bulb.turn_on()

            successes, failures = self._execute_bulb_operations_parallel(
                "set_brightness", bulbs, set_brightness_bulb
            )

            if successes == len(bulbs):
                return f"Set brightness of all {successes} lights to {brightness}"
            elif successes > 0:
                failure_msg = ", ".join([f"{ip}" for ip, _ in failures])
                return f"Set brightness of {successes}/{len(bulbs)} lights to {brightness} (failed: {failure_msg})"
            else:
                failure_details = ", ".join(
                    [f"{ip}: {err[:50]}" for ip, err in failures]
                )
                return f"Failed to set brightness: {failure_details}"
        except Exception as e:
            return f"Failed to set all brightness: {str(e)}"

    def set_all_color(self, color_name: str) -> str:
        """Set color for all lights in the system."""
        color_name = color_name.strip().lower()
        if color_name == "read":
            color_name = "red"

        try:
            if color_name not in self.COLOR_MAP:
                available_colors = ", ".join(self.COLOR_MAP.keys())
                return f"Unknown color '{color_name}'. Available colors: {available_colors}"

            bulbs = self._get_bulbs_by_name(None)
            if not bulbs:
                return "No lights found"

            # For white color, use color temperature mode for bright white light
            # For other colors, use RGB mode
            if color_name == "white":

                def set_color_bulb(bulb: Bulb):
                    bulb.turn_on()
                    # Set to cool white (5000K) for bright white light
                    # Color temp range: 1700K (warm) to 6500K (cool)
                    bulb.set_color_temp(5000)
                    # Set brightness to maximum for super bright white
                    bulb.set_brightness(100)

            else:
                color_data = self.COLOR_MAP[color_name]

                def set_color_bulb(bulb: Bulb):
                    bulb.turn_on()
                    bulb.set_rgb(color_data["r"], color_data["g"], color_data["b"])

            successes, failures = self._execute_bulb_operations_parallel(
                "set_color", bulbs, set_color_bulb
            )

            if successes == len(bulbs):
                return f"Set all {successes} lights to {color_name}"
            elif successes > 0:
                failure_msg = ", ".join([f"{ip}" for ip, _ in failures])
                return f"Set {successes}/{len(bulbs)} lights to {color_name} (failed: {failure_msg})"
            else:
                failure_details = ", ".join(
                    [f"{ip}: {err[:50]}" for ip, err in failures]
                )
                return f"Failed to set all lights color: {failure_details}"
        except Exception as e:
            return f"Failed to set all lights color: {str(e)}"

    def turn_on_light(self, light_name: str) -> str:
        """Turn on a specific light."""
        try:
            bulbs = self._get_bulbs_by_name(light_name)
            if not bulbs:
                return f"Light '{light_name}' not found"

            def turn_on_bulb(bulb: Bulb):
                bulb.turn_on()

            successes, failures = self._execute_bulb_operations_parallel(
                "turn_on", bulbs, turn_on_bulb
            )

            if successes == len(bulbs):
                return f"Turned on {successes} light(s)"
            elif successes > 0:
                failure_msg = ", ".join([f"{ip}" for ip, _ in failures])
                return f"Turned on {successes}/{len(bulbs)} light(s) (failed: {failure_msg})"
            else:
                failure_details = ", ".join(
                    [f"{ip}: {err[:50]}" for ip, err in failures]
                )
                return f"Failed to turn on {light_name}: {failure_details}"
        except Exception as e:
            return f"Failed to turn on {light_name}: {str(e)}"

    def turn_off_light(self, light_name: str) -> str:
        """Turn off a specific light."""
        try:
            bulbs = self._get_bulbs_by_name(light_name)
            if not bulbs:
                return f"Light '{light_name}' not found"

            def turn_off_bulb(bulb: Bulb):
                bulb.turn_off()

            successes, failures = self._execute_bulb_operations_parallel(
                "turn_off", bulbs, turn_off_bulb
            )

            if successes == len(bulbs):
                return f"Turned off {successes} light(s)"
            elif successes > 0:
                failure_msg = ", ".join([f"{ip}" for ip, _ in failures])
                return f"Turned off {successes}/{len(bulbs)} light(s) (failed: {failure_msg})"
            else:
                failure_details = ", ".join(
                    [f"{ip}: {err[:50]}" for ip, err in failures]
                )
                return f"Failed to turn off {light_name}: {failure_details}"
        except Exception as e:
            return f"Failed to turn off {light_name}: {str(e)}"

    def toggle_light(self, light_name: str) -> str:
        """Toggle a light on/off."""
        try:
            bulbs = self._get_bulbs_by_name(light_name)
            if not bulbs:
                return f"Light '{light_name}' not found"

            def toggle_bulb(bulb: Bulb):
                props = bulb.get_properties()
                current_state = props.get("power") == "on"
                if current_state:
                    bulb.turn_off()
                else:
                    bulb.turn_on()

            successes, failures = self._execute_bulb_operations_parallel(
                "toggle", bulbs, toggle_bulb
            )

            if successes == len(bulbs):
                return f"Toggled {successes} light(s)"
            elif successes > 0:
                failure_msg = ", ".join([f"{ip}" for ip, _ in failures])
                return (
                    f"Toggled {successes}/{len(bulbs)} light(s) (failed: {failure_msg})"
                )
            else:
                failure_details = ", ".join(
                    [f"{ip}: {err[:50]}" for ip, err in failures]
                )
                return f"Failed to toggle {light_name}: {failure_details}"
        except Exception as e:
            return f"Failed to toggle {light_name}: {str(e)}"

    def set_brightness(self, light_name: str, brightness: int) -> str:
        """Set brightness of a specific light."""
        try:
            if brightness == 0:
                return self.turn_off_light(light_name)
            brightness = max(1, min(100, brightness))
            bulbs = self._get_bulbs_by_name(light_name)
            if not bulbs:
                return f"Light '{light_name}' not found"

            def set_brightness_bulb(bulb: Bulb):
                bulb.set_brightness(brightness)
                bulb.turn_on()

            successes, failures = self._execute_bulb_operations_parallel(
                "set_brightness", bulbs, set_brightness_bulb
            )

            if successes == len(bulbs):
                return f"Set brightness of {successes} light(s) to {brightness}"
            elif successes > 0:
                failure_msg = ", ".join([f"{ip}" for ip, _ in failures])
                return f"Set brightness of {successes}/{len(bulbs)} light(s) to {brightness} (failed: {failure_msg})"
            else:
                failure_details = ", ".join(
                    [f"{ip}: {err[:50]}" for ip, err in failures]
                )
                return f"Failed to set brightness for {light_name}: {failure_details}"
        except Exception as e:
            return f"Failed to set brightness: {str(e)}"

    def set_color_name(self, light_name: str, color_name: str) -> str:
        """Set light color using common color names."""
        try:
            color_name = color_name.lower()
            if color_name not in self.COLOR_MAP:
                available_colors = ", ".join(self.COLOR_MAP.keys())
                return f"Unknown color '{color_name}'. Available colors: {available_colors}"

            bulbs = self._get_bulbs_by_name(light_name)
            if not bulbs:
                return f"Light '{light_name}' not found"

            # For white color, use color temperature mode for bright white light
            # For other colors, use RGB mode
            if color_name == "white":

                def set_color_bulb(bulb: Bulb):
                    bulb.turn_on()
                    # Set to cool white (5000K) for bright white light
                    # Color temp range: 1700K (warm) to 6500K (cool)
                    bulb.set_color_temp(5000)
                    # Set brightness to maximum for super bright white
                    bulb.set_brightness(100)

            else:
                color_data = self.COLOR_MAP[color_name]

                def set_color_bulb(bulb: Bulb):
                    bulb.turn_on()
                    bulb.set_rgb(color_data["r"], color_data["g"], color_data["b"])

            successes, failures = self._execute_bulb_operations_parallel(
                "set_color", bulbs, set_color_bulb
            )

            if successes == len(bulbs):
                return f"Set {successes} light(s) to {color_name}"
            elif successes > 0:
                failure_msg = ", ".join([f"{ip}" for ip, _ in failures])
                return f"Set {successes}/{len(bulbs)} light(s) to {color_name} (failed: {failure_msg})"
            else:
                failure_details = ", ".join(
                    [f"{ip}: {err[:50]}" for ip, err in failures]
                )
                return f"Failed to set color for {light_name}: {failure_details}"
        except Exception as e:
            return f"Failed to set color: {str(e)}"

    def list_lights(self) -> Dict[str, Any]:
        """List all lights with their IPs and names."""
        try:
            light_info = {}
            for ip, bulb in self.bulbs.items():
                try:
                    props = bulb.get_properties()
                    light_info[ip] = {
                        "id": ip,
                        "name": props.get("name", ip),
                        "on": props.get("power") == "on",
                        "brightness": int(props.get("bright", 0)),
                        "rgb": props.get("rgb"),
                    }
                except Exception:
                    light_info[ip] = {
                        "id": ip,
                        "name": ip,
                        "on": False,
                        "error": "Unable to get properties",
                    }
            return light_info
        except Exception as e:
            return {"error": f"Failed to list lights: {str(e)}"}
