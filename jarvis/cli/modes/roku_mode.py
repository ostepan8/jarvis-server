"""Roku TV mode - nvim-style keybinds for direct device control."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from .base import BaseMode, ModeKeybind, mode_registry

if TYPE_CHECKING:
    from jarvis.core.system import JarvisSystem
    from jarvis.services.roku_service import RokuService


class RokuMode(BaseMode):
    """SSH-style direct control mode for Roku TV."""

    def __init__(self, jarvis: JarvisSystem) -> None:
        self._jarvis = jarvis
        self._roku_service: Optional[RokuService] = None

    @property
    def name(self) -> str:
        return "Roku TV"

    @property
    def slug(self) -> str:
        return "roku"

    @property
    def icon(self) -> str:
        return "TV"

    @property
    def description(self) -> str:
        return "Direct TV control with vim-style navigation"

    @property
    def keybinds(self) -> list[ModeKeybind]:
        return [
            # Navigation
            ModeKeybind("h", "Left", "nav_left", "navigation"),
            ModeKeybind("j", "Down", "nav_down", "navigation"),
            ModeKeybind("k", "Up", "nav_up", "navigation"),
            ModeKeybind("l", "Right", "nav_right", "navigation"),
            ModeKeybind("LEFT", "Left", "nav_left", "navigation"),
            ModeKeybind("DOWN", "Down", "nav_down", "navigation"),
            ModeKeybind("UP", "Up", "nav_up", "navigation"),
            ModeKeybind("RIGHT", "Right", "nav_right", "navigation"),
            ModeKeybind("ENTER", "Select/OK", "select", "navigation"),
            ModeKeybind("b", "Back", "back", "navigation"),
            ModeKeybind("H", "Home", "home", "navigation"),
            # Playback
            ModeKeybind(" ", "Play/Pause", "play_pause", "playback"),
            ModeKeybind("r", "Rewind", "rewind", "playback"),
            ModeKeybind("f", "Fast Forward", "fast_forward", "playback"),
            ModeKeybind("R", "Instant Replay", "instant_replay", "playback"),
            # Volume
            ModeKeybind("+", "Volume Up", "vol_up", "volume"),
            ModeKeybind("=", "Volume Up", "vol_up", "volume"),
            ModeKeybind("-", "Volume Down", "vol_down", "volume"),
            ModeKeybind("m", "Mute", "mute", "volume"),
            # Power
            ModeKeybind("P", "Power Off", "power_off", "power"),
            ModeKeybind("O", "Power On", "power_on", "power"),
            # Info
            ModeKeybind("i", "Device Info", "device_info", "info"),
            ModeKeybind("/", "Search", "search", "info"),
            # System
            ModeKeybind("?", "Show Help", "help", "system"),
            ModeKeybind("q", "Exit Mode", "exit", "system"),
            ModeKeybind("ESC", "Exit Mode", "exit", "system"),
        ]

    def _get_roku_service(self) -> Optional[RokuService]:
        """Get the RokuService from the agent network."""
        agents = self._jarvis.network.agents
        roku_agent = agents.get("RokuAgent")
        if roku_agent and hasattr(roku_agent, "roku_service"):
            return roku_agent.roku_service
        return None

    async def on_enter(self) -> bool:
        """Connect to the Roku device."""
        self._roku_service = self._get_roku_service()
        if not self._roku_service:
            raise ConnectionError(
                "RokuAgent not found in agent network. "
                "Is Roku enabled in /config?"
            )

        # Verify device is reachable
        result = await self._roku_service.get_device_info()
        if not result.get("success"):
            error = result.get("error", "unknown error")
            raise ConnectionError(f"Roku device unreachable: {error}")
        return True

    async def on_exit(self) -> None:
        """Cleanup — nothing to do, service is owned by the agent."""
        self._roku_service = None

    async def handle_key(self, key: str) -> Optional[str]:
        """Dispatch a keypress to the Roku service."""
        if not self._roku_service:
            return "Not connected"

        # Build action lookup from keybinds
        action_map = {kb.key: kb.action for kb in self.keybinds}
        action = action_map.get(key)

        if action is None:
            return None  # Unmapped key, ignore silently

        # Dispatch to service
        svc = self._roku_service
        handlers = {
            "nav_left": lambda: svc.navigate("left"),
            "nav_down": lambda: svc.navigate("down"),
            "nav_up": lambda: svc.navigate("up"),
            "nav_right": lambda: svc.navigate("right"),
            "select": svc.select,
            "back": svc.back,
            "home": svc.home,
            "play_pause": svc.play,
            "rewind": svc.rewind,
            "fast_forward": svc.fast_forward,
            "instant_replay": svc.instant_replay,
            "vol_up": svc.volume_up,
            "vol_down": svc.volume_down,
            "mute": svc.volume_mute,
            "power_off": svc.power_off,
            "power_on": svc.power_on,
            "device_info": self._get_device_info,
            "search": self._open_search,
        }

        handler = handlers.get(action)
        if handler is None:
            return None

        result = await handler()

        if action == "device_info":
            return result  # Already formatted string

        if action == "search":
            return result

        # Standard result dict from RokuService
        if isinstance(result, dict):
            if result.get("success"):
                # Find the keybind label for display
                for kb in self.keybinds:
                    if kb.key == key:
                        return kb.label
                return "OK"
            return f"Error: {result.get('error', 'unknown')}"

        return str(result)

    async def _get_device_info(self) -> str:
        """Get formatted device info string."""
        assert self._roku_service is not None
        result = await self._roku_service.get_device_info()
        if not result.get("success"):
            return f"Error: {result.get('error', 'unknown')}"

        active = await self._roku_service.get_active_app()
        app_name = active.get("app_name", "Unknown") if active.get("success") else "Unknown"

        return (
            f"{result.get('device_name', 'Roku')} | "
            f"{result.get('model', '?')} | "
            f"App: {app_name} | "
            f"Power: {result.get('power_mode', '?')}"
        )

    async def _open_search(self) -> str:
        """Open the Roku search screen."""
        assert self._roku_service is not None
        result = await self._roku_service.press_key("Search")
        if result.get("success"):
            return "Search opened"
        return f"Error: {result.get('error', 'unknown')}"


# Register with the global registry
mode_registry.register_with_slug("roku", RokuMode)
