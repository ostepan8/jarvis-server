# jarvis/services/roku_service.py
"""
RokuService - Interface to Roku External Control Protocol (ECP)
"""
from __future__ import annotations

import httpx
import xml.etree.ElementTree as ET
from typing import Dict, Any, List, Optional


class RokuService:
    """
    Service for controlling Roku devices via the External Control Protocol (ECP).
    Provides methods for device discovery, channel launching, remote control, and querying.
    """

    def __init__(
        self,
        device_ip: str,
        username: Optional[str] = None,
        password: Optional[str] = None,
        timeout: float = 5.0,
    ):
        """
        Initialize the Roku service.

        Args:
            device_ip: IP address of the Roku device
            username: Optional username for authentication
            password: Optional password for authentication
            timeout: HTTP request timeout in seconds
        """
        self.device_ip = device_ip
        self.username = username
        self.password = password
        self.base_url = f"http://{device_ip}:8060"

        # Create client with optional basic auth
        auth = None
        if username and password:
            auth = httpx.BasicAuth(username, password)

        self.client = httpx.AsyncClient(timeout=timeout, auth=auth)

    async def close(self) -> None:
        """Clean up resources."""
        await self.client.aclose()

    # ==================== DEVICE INFORMATION ====================

    async def get_device_info(self) -> Dict[str, Any]:
        """Get comprehensive device information."""
        try:
            response = await self.client.get(f"{self.base_url}/query/device-info")
            response.raise_for_status()

            root = ET.fromstring(response.text)
            info = {}
            for child in root:
                info[child.tag] = child.text

            return {
                "success": True,
                "device_name": info.get(
                    "user-device-name", info.get("friendly-device-name", "Unknown")
                ),
                "model": info.get("model-name", "Unknown"),
                "model_number": info.get("model-number"),
                "serial_number": info.get("serial-number"),
                "software_version": info.get("software-version"),
                "device_id": info.get("device-id"),
                "network_type": info.get("network-type"),
                "power_mode": info.get("power-mode"),
                "supports_ethernet": info.get("supports-ethernet") == "true",
                "supports_wifi": info.get("supports-wifi-5ghz-band") == "true",
                "raw_info": info,
            }
        except Exception as e:
            return {"success": False, "error": f"Failed to get device info: {str(e)}"}

    async def get_active_app(self) -> Dict[str, Any]:
        """Get the currently active app/channel."""
        try:
            response = await self.client.get(f"{self.base_url}/query/active-app")
            response.raise_for_status()

            root = ET.fromstring(response.text)
            app = root.find("app")

            if app is not None:
                return {
                    "success": True,
                    "app_id": app.get("id"),
                    "app_name": app.text,
                    "version": app.get("version"),
                }
            else:
                return {"success": True, "app_name": "Home Screen"}
        except Exception as e:
            return {"success": False, "error": f"Failed to get active app: {str(e)}"}

    async def list_apps(self) -> Dict[str, Any]:
        """List all installed apps/channels."""
        try:
            response = await self.client.get(f"{self.base_url}/query/apps")
            response.raise_for_status()

            root = ET.fromstring(response.text)
            apps = []

            for app in root.findall("app"):
                apps.append(
                    {
                        "id": app.get("id"),
                        "name": app.text,
                        "type": app.get("type"),
                        "version": app.get("version"),
                    }
                )

            return {"success": True, "count": len(apps), "apps": apps}
        except Exception as e:
            return {"success": False, "error": f"Failed to list apps: {str(e)}"}

    async def search_app(self, app_name: str) -> Optional[str]:
        """Search for an app by name and return its ID."""
        apps_result = await self.list_apps()
        if not apps_result.get("success"):
            return None

        app_name_lower = app_name.lower()
        for app in apps_result.get("apps", []):
            if app_name_lower in app.get("name", "").lower():
                return app.get("id")
        return None

    # ==================== APP/CHANNEL CONTROL ====================

    async def launch_app(self, app_id: str) -> Dict[str, Any]:
        """Launch an app/channel by ID."""
        try:
            response = await self.client.post(f"{self.base_url}/launch/{app_id}")
            response.raise_for_status()
            return {"success": True, "message": f"Launched app {app_id}"}
        except Exception as e:
            return {"success": False, "error": f"Failed to launch app: {str(e)}"}

    async def launch_app_by_name(self, app_name: str) -> Dict[str, Any]:
        """Launch an app by its name."""
        app_id = await self.search_app(app_name)
        if not app_id:
            return {"success": False, "error": f"App '{app_name}' not found"}
        return await self.launch_app(app_id)

    # ==================== REMOTE CONTROL KEYS ====================

    async def press_key(self, key: str) -> Dict[str, Any]:
        """
        Send a keypress to the Roku device.

        Valid keys include: Home, Rev, Fwd, Play, Select, Left, Right, Down, Up,
        Back, InstantReplay, Info, Backspace, Search, Enter, VolumeDown, VolumeUp,
        VolumeMute, PowerOff, PowerOn, ChannelUp, ChannelDown, InputTuner, InputHDMI1,
        InputHDMI2, InputHDMI3, InputHDMI4, InputAV1
        """
        try:
            response = await self.client.post(f"{self.base_url}/keypress/{key}")
            response.raise_for_status()
            return {"success": True, "message": f"Pressed key: {key}"}
        except Exception as e:
            return {"success": False, "error": f"Failed to press key: {str(e)}"}

    async def press_multiple_keys(
        self, keys: List[str], delay_ms: int = 100
    ) -> Dict[str, Any]:
        """Press multiple keys in sequence."""
        import asyncio

        results = []
        for key in keys:
            result = await self.press_key(key)
            results.append(result)
            if delay_ms > 0:
                await asyncio.sleep(delay_ms / 1000.0)

        success = all(r.get("success") for r in results)
        return {
            "success": success,
            "message": f"Pressed {len(keys)} keys",
            "results": results,
        }

    # ==================== PLAYBACK CONTROL ====================

    async def play(self) -> Dict[str, Any]:
        """Resume playback."""
        return await self.press_key("Play")

    async def pause(self) -> Dict[str, Any]:
        """Pause playback."""
        return await self.press_key("Play")

    async def rewind(self) -> Dict[str, Any]:
        """Rewind."""
        return await self.press_key("Rev")

    async def fast_forward(self) -> Dict[str, Any]:
        """Fast forward."""
        return await self.press_key("Fwd")

    async def instant_replay(self) -> Dict[str, Any]:
        """Jump back a few seconds."""
        return await self.press_key("InstantReplay")

    # ==================== NAVIGATION ====================

    async def home(self) -> Dict[str, Any]:
        """Go to home screen."""
        return await self.press_key("Home")

    async def back(self) -> Dict[str, Any]:
        """Go back."""
        return await self.press_key("Back")

    async def select(self) -> Dict[str, Any]:
        """Select/OK button."""
        return await self.press_key("Select")

    async def navigate(self, direction: str) -> Dict[str, Any]:
        """Navigate in a direction (up, down, left, right)."""
        direction_map = {"up": "Up", "down": "Down", "left": "Left", "right": "Right"}
        key = direction_map.get(direction.lower())
        if not key:
            return {"success": False, "error": f"Invalid direction: {direction}"}
        return await self.press_key(key)

    # ==================== VOLUME AND POWER ====================

    async def volume_up(self) -> Dict[str, Any]:
        """Increase volume."""
        return await self.press_key("VolumeUp")

    async def volume_down(self) -> Dict[str, Any]:
        """Decrease volume."""
        return await self.press_key("VolumeDown")

    async def volume_mute(self) -> Dict[str, Any]:
        """Mute/unmute volume."""
        return await self.press_key("VolumeMute")

    async def power_off(self) -> Dict[str, Any]:
        """Turn off the device."""
        return await self.press_key("PowerOff")

    async def power_on(self) -> Dict[str, Any]:
        """Turn on the device."""
        return await self.press_key("PowerOn")

    # ==================== INPUT SWITCHING ====================

    async def switch_input(self, input_name: str) -> Dict[str, Any]:
        """
        Switch to a specific input.
        Valid inputs: Tuner, HDMI1, HDMI2, HDMI3, HDMI4, AV1
        """
        input_key = f"Input{input_name}"
        return await self.press_key(input_key)

    # ==================== SEARCH ====================

    async def search(self, query: str) -> Dict[str, Any]:
        """Open search with a query."""
        try:
            # First open search
            await self.press_key("Search")
            # Wait a moment for search to open
            import asyncio

            await asyncio.sleep(0.5)

            # Type the query
            for char in query:
                await self.type_character(char)
                await asyncio.sleep(0.1)

            return {"success": True, "message": f"Searched for: {query}"}
        except Exception as e:
            return {"success": False, "error": f"Failed to search: {str(e)}"}

    async def type_character(self, char: str) -> Dict[str, Any]:
        """Type a single character using the keyboard."""
        try:
            # URL encode the character
            import urllib.parse

            encoded_char = urllib.parse.quote(char)
            response = await self.client.post(
                f"{self.base_url}/keypress/Lit_{encoded_char}"
            )
            response.raise_for_status()
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ==================== PLAYER INFORMATION ====================

    async def get_player_info(self) -> Dict[str, Any]:
        """Get information about media player state."""
        try:
            response = await self.client.get(f"{self.base_url}/query/media-player")
            response.raise_for_status()

            root = ET.fromstring(response.text)

            # Parse player information
            info = {
                "success": True,
                "state": root.get("state"),  # play, pause, close
                "error": root.get("error") == "true",
            }

            # Get plugin info if available
            plugin = root.find("plugin")
            if plugin is not None:
                info["plugin_id"] = plugin.get("id")
                info["plugin_name"] = plugin.get("name")
                info["bandwidth"] = plugin.get("bandwidth")

            # Get format info
            format_elem = root.find("format")
            if format_elem is not None:
                info["audio"] = format_elem.get("audio")
                info["video"] = format_elem.get("video")
                info["captions"] = format_elem.get("captions")

            # Get position and duration
            position = root.find("position")
            duration = root.find("duration")
            if position is not None and position.text:
                # Strip " ms" suffix if present
                position_text = (
                    position.text.strip().replace(" ms", "").replace("ms", "")
                )
                info["position_ms"] = int(position_text) if position_text else 0
            if duration is not None and duration.text:
                # Strip " ms" suffix if present
                duration_text = (
                    duration.text.strip().replace(" ms", "").replace("ms", "")
                )
                info["duration_ms"] = int(duration_text) if duration_text else 0

            return info
        except Exception as e:
            return {"success": False, "error": f"Failed to get player info: {str(e)}"}
