# jarvis/agents/roku_agent/function_registry.py
"""
Function registry for Roku agent - maps capabilities to service methods
"""
from typing import Set, Callable, Any, Optional
from ...services.roku_service import RokuService


class RokuFunctionRegistry:
    """Maps capability names to RokuService methods and manages function lookup."""

    def __init__(self, roku_service: RokuService):
        self.roku_service = roku_service
        self._build_registry()

    def _build_registry(self):
        """Build the mapping of function names to service methods."""
        self.function_map = {
            # Device information
            "get_device_info": self.roku_service.get_device_info,
            "get_active_app": self.roku_service.get_active_app,
            "list_apps": self.roku_service.list_apps,
            "get_player_info": self.roku_service.get_player_info,
            # App control
            "launch_app_by_name": self.roku_service.launch_app_by_name,
            # Playback control
            "play": self.roku_service.play,
            "pause": self.roku_service.pause,
            "rewind": self.roku_service.rewind,
            "fast_forward": self.roku_service.fast_forward,
            "instant_replay": self.roku_service.instant_replay,
            # Navigation
            "home": self.roku_service.home,
            "back": self.roku_service.back,
            "select": self.roku_service.select,
            "navigate": self._navigate_multiple,
            # Volume and power
            "volume_up": self._volume_up_multiple,
            "volume_down": self._volume_down_multiple,
            "volume_mute": self.roku_service.volume_mute,
            "power_off": self.roku_service.power_off,
            "power_on": self.roku_service.power_on,
            # Input switching
            "switch_input": self.roku_service.switch_input,
            # Search
            "search": self.roku_service.search,
        }

    async def _navigate_multiple(self, direction: str, count: int = 1) -> Any:
        """Navigate in a direction multiple times."""
        for _ in range(count):
            result = await self.roku_service.navigate(direction)
            if not result.get("success"):
                return result
        return {"success": True, "message": f"Navigated {direction} {count} times"}

    async def _volume_up_multiple(self, count: int = 1) -> Any:
        """Increase volume multiple times."""
        for _ in range(count):
            result = await self.roku_service.volume_up()
            if not result.get("success"):
                return result
        return {"success": True, "message": f"Increased volume {count} times"}

    async def _volume_down_multiple(self, count: int = 1) -> Any:
        """Decrease volume multiple times."""
        for _ in range(count):
            result = await self.roku_service.volume_down()
            if not result.get("success"):
                return result
        return {"success": True, "message": f"Decreased volume {count} times"}

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
        }

    def get_function(self, function_name: str) -> Optional[Callable]:
        """Get a function by name."""
        return self.function_map.get(function_name)
