# jarvis/agents/roku_agent/function_registry.py
"""
Function registry for Roku agent - maps capabilities to device-routed service methods.

Every function delegates through the agent's execute_on_device / execute_on_all
methods so that device resolution and failover happen transparently.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, Dict, Optional, Set

if TYPE_CHECKING:
    from .agent import RokuAgent


class RokuFunctionRegistry:
    """Maps capability names to agent-routed device methods and manages function lookup."""

    def __init__(self, agent: "RokuAgent"):
        self.agent = agent
        self._build_registry()

    def _build_registry(self) -> None:
        """Build the mapping — each function delegates to the agent for device routing."""
        self.function_map: Dict[str, Callable[..., Any]] = {}

        # Wrap all standard service methods
        service_methods = [
            "get_device_info",
            "get_active_app",
            "list_apps",
            "get_player_info",
            "launch_app_by_name",
            "play",
            "pause",
            "rewind",
            "fast_forward",
            "instant_replay",
            "home",
            "back",
            "select",
            "volume_mute",
            "power_off",
            "power_on",
            "switch_input",
            "search",
        ]
        for method_name in service_methods:
            self.function_map[method_name] = self._make_device_wrapper(method_name)

        # Custom wrappers for multi-press
        self.function_map["navigate"] = self._navigate_multiple
        self.function_map["volume_up"] = self._volume_up_multiple
        self.function_map["volume_down"] = self._volume_down_multiple

        # Device management functions
        self.function_map["list_devices"] = self._list_devices
        self.function_map["name_device"] = self._name_device
        self.function_map["set_default_device"] = self._set_default_device
        self.function_map["discover_devices"] = self._discover_devices

    # ------------------------------------------------------------------
    # Generic device wrapper
    # ------------------------------------------------------------------

    def _make_device_wrapper(self, method_name: str) -> Callable[..., Any]:
        """Create an async wrapper that routes a service method through the agent."""

        async def wrapper(device: str = "", **kwargs: Any) -> Any:
            if device and device.lower() == "all":
                return await self.agent.execute_on_all(method_name, **kwargs)
            serial = ""
            if device:
                info = self.agent.device_registry.resolve_device(name_hint=device)
                serial = info.serial_number if info else ""
            return await self.agent.execute_on_device(serial, method_name, **kwargs)

        return wrapper

    # ------------------------------------------------------------------
    # Multi-press wrappers
    # ------------------------------------------------------------------

    async def _navigate_multiple(
        self, direction: str, count: int = 1, device: str = ""
    ) -> Any:
        """Navigate in a direction multiple times."""
        if device and device.lower() == "all":
            results = []
            for _ in range(count):
                results.append(
                    await self.agent.execute_on_all("navigate", direction=direction)
                )
            return results[-1] if results else {"success": True}

        serial = ""
        if device:
            info = self.agent.device_registry.resolve_device(name_hint=device)
            serial = info.serial_number if info else ""

        for _ in range(count):
            result = await self.agent.execute_on_device(
                serial, "navigate", direction=direction
            )
            if not result.get("success"):
                return result
        return {"success": True, "message": f"Navigated {direction} {count} times"}

    async def _volume_up_multiple(self, count: int = 1, device: str = "") -> Any:
        """Increase volume multiple times."""
        if device and device.lower() == "all":
            results = []
            for _ in range(count):
                results.append(await self.agent.execute_on_all("volume_up"))
            return results[-1] if results else {"success": True}

        serial = ""
        if device:
            info = self.agent.device_registry.resolve_device(name_hint=device)
            serial = info.serial_number if info else ""

        for _ in range(count):
            result = await self.agent.execute_on_device(serial, "volume_up")
            if not result.get("success"):
                return result
        return {"success": True, "message": f"Increased volume {count} times"}

    async def _volume_down_multiple(self, count: int = 1, device: str = "") -> Any:
        """Decrease volume multiple times."""
        if device and device.lower() == "all":
            results = []
            for _ in range(count):
                results.append(await self.agent.execute_on_all("volume_down"))
            return results[-1] if results else {"success": True}

        serial = ""
        if device:
            info = self.agent.device_registry.resolve_device(name_hint=device)
            serial = info.serial_number if info else ""

        for _ in range(count):
            result = await self.agent.execute_on_device(serial, "volume_down")
            if not result.get("success"):
                return result
        return {"success": True, "message": f"Decreased volume {count} times"}

    # ------------------------------------------------------------------
    # Device management functions
    # ------------------------------------------------------------------

    async def _list_devices(self) -> Dict[str, Any]:
        """List all registered Roku devices."""
        devices = self.agent.device_registry.get_all_devices()
        device_list = []
        for d in devices:
            device_list.append(
                {
                    "serial": d.serial_number,
                    "name": d.friendly_name or d.device_name or d.serial_number,
                    "ip": d.ip_address,
                    "model": d.model,
                    "online": d.is_online,
                    "is_default": d.serial_number
                    == self.agent.device_registry.default_serial,
                }
            )
        return {"success": True, "devices": device_list, "count": len(device_list)}

    def _resolve_device_hint(self, device: str) -> Optional[Any]:
        """Resolve a device hint (serial, friendly name, or device name) to a device.

        Unlike resolve_device(), this does NOT fall back to default/last-used
        when the hint doesn't match.  For explicit operations like naming or
        setting default, silently targeting the wrong device is worse than
        returning None.
        """
        # Try exact serial first
        dev = self.agent.device_registry.get_device_by_serial(device)
        if dev:
            return dev

        # Try name-based matching (exact and fuzzy) without default fallback
        hint_lower = device.lower()
        for d in self.agent.device_registry.devices.values():
            if d.friendly_name and d.friendly_name.lower() == hint_lower:
                return d
        for d in self.agent.device_registry.devices.values():
            if d.friendly_name and hint_lower in d.friendly_name.lower():
                return d
        for d in self.agent.device_registry.devices.values():
            if d.device_name and d.device_name.lower() == hint_lower:
                return d
        for d in self.agent.device_registry.devices.values():
            if d.device_name and hint_lower in d.device_name.lower():
                return d

        return None

    async def _name_device(self, device: str, name: str) -> Dict[str, Any]:
        """Assign a friendly name to a device, resolved by serial, name, or model."""
        dev = self._resolve_device_hint(device)
        if not dev:
            all_devices = self.agent.device_registry.get_all_devices()
            available = [
                f"{d.friendly_name or d.device_name or d.serial_number} (serial: {d.serial_number})"
                for d in all_devices
            ]
            return {
                "success": False,
                "error": f"No device matched '{device}'. Available: {', '.join(available)}",
            }
        self.agent.device_registry.set_friendly_name(dev.serial_number, name)
        return {
            "success": True,
            "message": f"Device '{dev.device_name or dev.serial_number}' named '{name}'",
            "serial": dev.serial_number,
        }

    async def _set_default_device(self, device: str) -> Dict[str, Any]:
        """Set a device as the default, resolved by serial, name, or model."""
        dev = self._resolve_device_hint(device)
        if not dev:
            return {"success": False, "error": f"No device matched '{device}'"}
        self.agent.device_registry.set_default(dev.serial_number)
        return {
            "success": True,
            "message": f"Device '{dev.friendly_name or dev.device_name}' set as default",
            "serial": dev.serial_number,
        }

    async def _discover_devices(self) -> Dict[str, Any]:
        """Trigger SSDP discovery for new Roku devices."""
        newly = await self.agent.discover_devices()
        all_devices = self.agent.device_registry.get_all_devices()
        online = self.agent.device_registry.get_online_devices()
        device_list = [
            {
                "name": d.friendly_name or d.device_name or d.serial_number,
                "ip": d.ip_address,
                "model": d.model,
                "online": d.is_online,
            }
            for d in all_devices
        ]
        return {
            "success": True,
            "new_discovered": len(newly),
            "total_devices": len(all_devices),
            "online_devices": len(online),
            "devices": device_list,
            "message": (
                f"Found {len(newly)} new device(s). "
                f"{len(all_devices)} total device(s) registered, "
                f"{len(online)} online."
            ),
        }

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    @property
    def capabilities(self) -> Set[str]:
        """Return the set of all available capabilities."""
        return {
            # Main command capability
            "roku_command",
            # Device information capabilities
            "roku_device_info",
            "roku_active_app",
            "roku_list_apps",
            "roku_player_info",
            # App control capabilities
            "roku_launch_app",
            # Playback capabilities
            "roku_play",
            "roku_pause",
            "roku_rewind",
            "roku_fast_forward",
            "roku_instant_replay",
            # Navigation capabilities
            "roku_home",
            "roku_back",
            "roku_select",
            "roku_navigate",
            # Volume and power capabilities
            "roku_volume_up",
            "roku_volume_down",
            "roku_volume_mute",
            "roku_power_off",
            "roku_power_on",
            # Input switching capabilities
            "roku_switch_input",
            # Search capabilities
            "roku_search",
            # Device management capabilities
            "roku_list_devices",
            "roku_name_device",
            "roku_set_default",
            "roku_discover_devices",
        }

    def get_function(self, function_name: str) -> Optional[Callable]:
        """Get a function by name."""
        return self.function_map.get(function_name)
