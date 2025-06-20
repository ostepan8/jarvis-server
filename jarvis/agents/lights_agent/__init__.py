# jarvis/agents/phillips_hue_agent.py

from __future__ import annotations

import asyncio
import functools
import json
import time
from typing import Any, Dict, List, Optional, Union
from phue import Bridge
from ..base import NetworkAgent
from ..message import Message
from ...logger import JarvisLogger
from ...ai_clients.base import BaseAIClient


class PhillipsHueAgent(NetworkAgent):
    """Agent for controlling Philips Hue lights via the Hue Bridge, using AI to translate
    natural-language commands into discrete tool calls."""

    def __init__(
        self,
        ai_client: BaseAIClient,
        bridge_ip: str,
        username: str | None = None,
        logger: JarvisLogger | None = None,
    ) -> None:
        super().__init__("PhillipsHueAgent", logger)
        self.ai_client = ai_client

        # Connect to the bridge (press link button once if needed)
        if username:
            self.bridge = Bridge(bridge_ip, username=username)
        else:
            self.bridge = Bridge(bridge_ip)
        try:
            self.bridge.connect()
        except Exception:
            pass  # will retry on demand

        # Define available tools/functions - MASSIVELY EXPANDED
        self.tools = [
            # Basic Light Control
            {
                "type": "function",
                "function": {
                    "name": "list_lights",
                    "description": "List all available lights with their IDs and names",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_light_status",
                    "description": "Get detailed status of a specific light (on/off, brightness, color, reachability, etc.)",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "light_name": {
                                "type": "string",
                                "description": "Name of the light",
                            }
                        },
                        "required": ["light_name"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "turn_on_light",
                    "description": "Turn a specific light on",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "light_name": {
                                "type": "string",
                                "description": "Name of the light",
                            }
                        },
                        "required": ["light_name"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "turn_off_light",
                    "description": "Turn a specific light off",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "light_name": {
                                "type": "string",
                                "description": "Name of the light",
                            }
                        },
                        "required": ["light_name"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "toggle_light",
                    "description": "Toggle a light on/off (switch to opposite state)",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "light_name": {
                                "type": "string",
                                "description": "Name of the light",
                            }
                        },
                        "required": ["light_name"],
                    },
                },
            },
            # Brightness Control
            {
                "type": "function",
                "function": {
                    "name": "set_brightness",
                    "description": "Set brightness of a light (0-254, where 0 is off and 254 is maximum)",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "light_name": {"type": "string"},
                            "brightness": {
                                "type": "integer",
                                "description": "Brightness level 0-254",
                            },
                        },
                        "required": ["light_name", "brightness"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "adjust_brightness",
                    "description": "Increase or decrease brightness by a relative amount",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "light_name": {"type": "string"},
                            "adjustment": {
                                "type": "integer",
                                "description": "Amount to change brightness by (positive or negative)",
                            },
                        },
                        "required": ["light_name", "adjustment"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "dim_light",
                    "description": "Dim a light to 25% brightness",
                    "parameters": {
                        "type": "object",
                        "properties": {"light_name": {"type": "string"}},
                        "required": ["light_name"],
                    },
                },
            },
            # Color Control
            {
                "type": "function",
                "function": {
                    "name": "set_color",
                    "description": "Set color of a light using hue/saturation or XY coordinates",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "light_name": {"type": "string"},
                            "hue": {
                                "type": "integer",
                                "description": "Hue value 0-65535",
                            },
                            "sat": {
                                "type": "integer",
                                "description": "Saturation 0-254",
                            },
                            "xy": {
                                "type": "array",
                                "items": {"type": "number"},
                                "description": "[x, y] color coordinates",
                            },
                        },
                        "required": ["light_name"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "set_color_name",
                    "description": "Set light color using common color names (red, blue, green, yellow, purple, orange, pink, white)",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "light_name": {"type": "string"},
                            "color_name": {
                                "type": "string",
                                "description": "Color name (red, blue, green, yellow, purple, orange, pink, white)",
                            },
                        },
                        "required": ["light_name", "color_name"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "set_color_temperature",
                    "description": "Set color temperature in Kelvin (warm to cool white, 2000K-6500K)",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "light_name": {"type": "string"},
                            "kelvin": {
                                "type": "integer",
                                "description": "Color temperature in Kelvin (2000-6500)",
                            },
                        },
                        "required": ["light_name", "kelvin"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "set_warm_white",
                    "description": "Set light to warm white (2700K)",
                    "parameters": {
                        "type": "object",
                        "properties": {"light_name": {"type": "string"}},
                        "required": ["light_name"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "set_cool_white",
                    "description": "Set light to cool white (6500K)",
                    "parameters": {
                        "type": "object",
                        "properties": {"light_name": {"type": "string"}},
                        "required": ["light_name"],
                    },
                },
            },
            # Effects and Alerts
            {
                "type": "function",
                "function": {
                    "name": "flash_light",
                    "description": "Make a light flash/blink briefly",
                    "parameters": {
                        "type": "object",
                        "properties": {"light_name": {"type": "string"}},
                        "required": ["light_name"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "pulse_light",
                    "description": "Make a light pulse continuously for attention",
                    "parameters": {
                        "type": "object",
                        "properties": {"light_name": {"type": "string"}},
                        "required": ["light_name"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "stop_alert",
                    "description": "Stop any alert/effect on a light",
                    "parameters": {
                        "type": "object",
                        "properties": {"light_name": {"type": "string"}},
                        "required": ["light_name"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "set_color_loop",
                    "description": "Start or stop color loop effect on a light",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "light_name": {"type": "string"},
                            "enable": {
                                "type": "boolean",
                                "description": "True to start, False to stop",
                            },
                        },
                        "required": ["light_name", "enable"],
                    },
                },
            },
            # Group Operations
            {
                "type": "function",
                "function": {
                    "name": "list_groups",
                    "description": "List all available groups/rooms",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_group_status",
                    "description": "Get status of all lights in a group",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "group_name": {
                                "type": "string",
                                "description": "Name of the group",
                            }
                        },
                        "required": ["group_name"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "turn_on_group",
                    "description": "Turn on all lights in a group/room",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "group_name": {
                                "type": "string",
                                "description": "Name of the group",
                            }
                        },
                        "required": ["group_name"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "turn_off_group",
                    "description": "Turn off all lights in a group/room",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "group_name": {
                                "type": "string",
                                "description": "Name of the group",
                            }
                        },
                        "required": ["group_name"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "set_group_brightness",
                    "description": "Set brightness for all lights in a group",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "group_name": {"type": "string"},
                            "brightness": {
                                "type": "integer",
                                "description": "Brightness 0-254",
                            },
                        },
                        "required": ["group_name", "brightness"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "set_group_color",
                    "description": "Set color for all lights in a group",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "group_name": {"type": "string"},
                            "color_name": {
                                "type": "string",
                                "description": "Color name",
                            },
                        },
                        "required": ["group_name", "color_name"],
                    },
                },
            },
            # All Lights Operations
            {
                "type": "function",
                "function": {
                    "name": "turn_on_all_lights",
                    "description": "Turn on all lights in the system",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "turn_off_all_lights",
                    "description": "Turn off all lights in the system",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "set_all_brightness",
                    "description": "Set brightness for all lights",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "brightness": {
                                "type": "integer",
                                "description": "Brightness 0-254",
                            }
                        },
                        "required": ["brightness"],
                    },
                },
            },
            # Scene Management
            {
                "type": "function",
                "function": {
                    "name": "list_scenes",
                    "description": "List all available scenes",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "activate_scene",
                    "description": "Activate a specific scene",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "scene_name": {
                                "type": "string",
                                "description": "Name of the scene to activate",
                            }
                        },
                        "required": ["scene_name"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "create_scene",
                    "description": "Create a new scene from current light states",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "scene_name": {
                                "type": "string",
                                "description": "Name for the new scene",
                            },
                            "lights": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "List of light names to include",
                            },
                        },
                        "required": ["scene_name", "lights"],
                    },
                },
            },
            # Light Information and Diagnostics
            {
                "type": "function",
                "function": {
                    "name": "get_light_info",
                    "description": "Get detailed information about a light (model, type, capabilities, firmware)",
                    "parameters": {
                        "type": "object",
                        "properties": {"light_name": {"type": "string"}},
                        "required": ["light_name"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "check_unreachable_lights",
                    "description": "Find all lights that are currently unreachable",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_bridge_info",
                    "description": "Get information about the Hue Bridge",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            },
            # Light Management
            {
                "type": "function",
                "function": {
                    "name": "rename_light",
                    "description": "Rename a light",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "current_name": {
                                "type": "string",
                                "description": "Current name of the light",
                            },
                            "new_name": {
                                "type": "string",
                                "description": "New name for the light",
                            },
                        },
                        "required": ["current_name", "new_name"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "search_new_lights",
                    "description": "Search for new lights to add to the system",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            },
            # Transition Effects
            {
                "type": "function",
                "function": {
                    "name": "fade_light",
                    "description": "Gradually change light brightness over time",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "light_name": {"type": "string"},
                            "target_brightness": {
                                "type": "integer",
                                "description": "Target brightness 0-254",
                            },
                            "duration_seconds": {
                                "type": "integer",
                                "description": "Duration of fade in seconds",
                            },
                        },
                        "required": [
                            "light_name",
                            "target_brightness",
                            "duration_seconds",
                        ],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "sunrise_effect",
                    "description": "Create a sunrise effect on a light (gradually brighten with warm colors)",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "light_name": {"type": "string"},
                            "duration_minutes": {
                                "type": "integer",
                                "description": "Duration of sunrise effect in minutes",
                            },
                        },
                        "required": ["light_name", "duration_minutes"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "sunset_effect",
                    "description": "Create a sunset effect on a light (gradually dim with warm colors)",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "light_name": {"type": "string"},
                            "duration_minutes": {
                                "type": "integer",
                                "description": "Duration of sunset effect in minutes",
                            },
                        },
                        "required": ["light_name", "duration_minutes"],
                    },
                },
            },
            # Schedules and Timers
            {
                "type": "function",
                "function": {
                    "name": "list_schedules",
                    "description": "List all scheduled events",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "create_timer",
                    "description": "Create a timer to turn lights on/off after a delay",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "light_name": {"type": "string"},
                            "action": {
                                "type": "string",
                                "description": "Action: 'on' or 'off'",
                            },
                            "delay_minutes": {
                                "type": "integer",
                                "description": "Delay in minutes",
                            },
                        },
                        "required": ["light_name", "action", "delay_minutes"],
                    },
                },
            },
            # Entertainment and Gaming
            {
                "type": "function",
                "function": {
                    "name": "party_mode",
                    "description": "Start party mode with random colors and effects",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "lights": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "List of lights to include",
                            }
                        },
                        "required": ["lights"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "movie_mode",
                    "description": "Set lights for movie watching (dim warm lighting)",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "lights": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "List of lights to include",
                            }
                        },
                        "required": ["lights"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "focus_mode",
                    "description": "Set bright cool white lighting for concentration",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "lights": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "List of lights to include",
                            }
                        },
                        "required": ["lights"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "relax_mode",
                    "description": "Set warm dim lighting for relaxation",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "lights": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "List of lights to include",
                            }
                        },
                        "required": ["lights"],
                    },
                },
            },
        ]

        # Enhanced system prompt
        self.system_prompt = """
        You are Jarvis, an advanced AI agent that controls Philips Hue smart lighting systems. You have access to comprehensive lighting control functions including:

        BASIC CONTROLS: Turn lights on/off, adjust brightness, set colors
        GROUP OPERATIONS: Control multiple lights by room/group
        SCENES: Activate and create lighting scenes
        EFFECTS: Flash, pulse, color loop, and transition effects
        DIAGNOSTICS: Check light status, find unreachable devices
        SCHEDULES: Set timers and scheduled lighting changes
        MODES: Party, movie, focus, and relaxation lighting modes

        CRITICAL RULES:
        1. ALWAYS list available lights/groups BEFORE attempting to control them
        2. NEVER assume light or group names - verify they exist first
        3. If a user references a light/group that doesn't exist, list what's available and ask for clarification
        4. When given generic commands (e.g., "turn on the lights"), first check what's available

        REQUIRED WORKFLOW:
        - For light commands: First use list_lights() to see available lights
        - For group/room commands: First use list_groups() to see available groups/rooms
        - For scene commands: First use list_scenes() to see available scenes
        - Only proceed with control commands after verifying the target exists

        Given a user's natural-language command, translate it into the appropriate tool calls following the workflow above. Use the minimal set of calls needed to accomplish the goal. Consider context clues like time of day, activity, and mood when selecting appropriate lighting settings.

        Examples with proper workflow:
        - "Turn on the living room" → 
        1. list_groups() to verify "Living room" exists
        2. turn_on_group(group_name="Living room")

        - "Dim the bedroom lights" → 
        1. list_groups() to check if "Bedroom" is a group
        2. If group exists: set_group_brightness(group_name="Bedroom", brightness=64)
        3. If not, list_lights() to find bedroom lights
        4. dim_light(light_name="Bedroom 1") for each bedroom light

        - "Turn on all lights" →
        1. list_lights() to see what's available
        2. turn_on_all_lights() or turn on specific lights

        - "Make it cozy" → 
        1. list_lights() or list_groups() to see what's available
        2. relax_mode(lights=[...]) with discovered lights

        - "Party in the kitchen" →
        1. list_groups() to verify "Kitchen" exists
        2. If exists as group: set_group_color() with rotating colors
        3. If not, list_lights() to find kitchen lights
        4. party_mode(lights=[...]) with kitchen lights

        Remember: ALWAYS discover what's available before trying to control it. This prevents errors and ensures commands work properly.
        """.strip()

        # Color name mappings for easier color control
        self.color_map = {
            "red": {"hue": 0, "sat": 254},
            "orange": {"hue": 8000, "sat": 254},
            "yellow": {"hue": 12750, "sat": 254},
            "green": {"hue": 25500, "sat": 254},
            "blue": {"hue": 46920, "sat": 254},
            "purple": {"hue": 56100, "sat": 254},
            "pink": {"hue": 62000, "sat": 254},
            "white": {"hue": 0, "sat": 0},
        }

        # Map function names to methods
        self.intent_map = {
            # Basic Light Control
            "list_lights": self._list_lights,
            "get_light_status": self._get_light_status,
            "turn_on_light": self._turn_on_light,
            "turn_off_light": self._turn_off_light,
            "toggle_light": self._toggle_light,
            # Brightness Control
            "set_brightness": self._set_brightness,
            "adjust_brightness": self._adjust_brightness,
            "dim_light": self._dim_light,
            # Color Control
            "set_color": self._set_color,
            "set_color_name": self._set_color_name,
            "set_color_temperature": self._set_color_temperature,
            "set_warm_white": self._set_warm_white,
            "set_cool_white": self._set_cool_white,
            # Effects and Alerts
            "flash_light": self._flash_light,
            "pulse_light": self._pulse_light,
            "stop_alert": self._stop_alert,
            "set_color_loop": self._set_color_loop,
            # Group Operations
            "list_groups": self._list_groups,
            "get_group_status": self._get_group_status,
            "turn_on_group": self._turn_on_group,
            "turn_off_group": self._turn_off_group,
            "set_group_brightness": self._set_group_brightness,
            "set_group_color": self._set_group_color,
            # All Lights Operations
            "turn_on_all_lights": self._turn_on_all_lights,
            "turn_off_all_lights": self._turn_off_all_lights,
            "set_all_brightness": self._set_all_brightness,
            # Scene Management
            "list_scenes": self._list_scenes,
            "activate_scene": self._activate_scene,
            "create_scene": self._create_scene,
            # Light Information
            "get_light_info": self._get_light_info,
            "check_unreachable_lights": self._check_unreachable_lights,
            "get_bridge_info": self._get_bridge_info,
            # Light Management
            "rename_light": self._rename_light,
            "search_new_lights": self._search_new_lights,
            # Transition Effects
            "fade_light": self._fade_light,
            "sunrise_effect": self._sunrise_effect,
            "sunset_effect": self._sunset_effect,
            # Schedules and Timers
            "list_schedules": self._list_schedules,
            "create_timer": self._create_timer,
            # Entertainment Modes
            "party_mode": self._party_mode,
            "movie_mode": self._movie_mode,
            "focus_mode": self._focus_mode,
            "relax_mode": self._relax_mode,
        }

    @property
    def description(self) -> str:
        return "Advanced Philips Hue lighting control with comprehensive smart home capabilities"

    @property
    def capabilities(self) -> set[str]:
        return {
            # Main command capability
            "hue_command",
            # Basic light control
            "lights_list",
            "lights_status",
            "lights_on",
            "lights_off",
            "lights_toggle",
            # Brightness control
            "lights_brightness",
            "lights_dim",
            # Color control
            "lights_color",
            "lights_temperature",
            "lights_warm",
            "lights_cool",
            # Effects
            "lights_flash",
            "lights_pulse",
            "lights_colorloop",
            "lights_fade",
            "lights_sunrise",
            "lights_sunset",
            # Group operations
            "group_control",
            "group_list",
            # Scene operations
            "scenes_list",
            "scenes_activate",
            # Entertainment modes
            "mode_party",
            "mode_movie",
            "mode_focus",
            "mode_relax",
        }

    async def _execute_function(
        self, function_name: str, arguments: dict[str, any]
    ) -> dict[str, any]:
        """Run a tool function (potentially blocking) in an executor."""
        func = self.intent_map.get(function_name)
        if not func:
            return {"error": f"Unknown function: {function_name}"}
        try:
            call = functools.partial(func, **arguments)
            result = await asyncio.get_running_loop().run_in_executor(None, call)
            return {"result": result}
        except Exception as exc:
            err = {"error": str(exc), "function": function_name, "args": arguments}
            self.logger.log("ERROR", f"Error {function_name}", json.dumps(err))
            return err

    def _resolve_light_identifier(self, identifier: str) -> Optional[Union[str, int]]:
        """Resolve a light identifier to the correct format for the phue library.

        Args:
            identifier: Either a light name or light ID as string

        Returns:
            Light name (str) or light ID (int) that phue can use, or None if not found
        """
        try:
            # First, try to treat it as a light ID (string digits)
            if identifier.isdigit():
                light_id = int(identifier)
                # Verify this light ID exists
                all_lights = self.bridge.get_light()
                if str(light_id) in all_lights:
                    return light_id

            # If not a valid ID, treat it as a light name
            # Verify the light name exists
            light_names = self.bridge.get_light_objects("name")
            if identifier in light_names:
                return identifier

            # If we get here, the identifier doesn't match any light
            self.logger.log("WARNING", f"Light identifier '{identifier}' not found")
            return None

        except Exception as e:
            self.logger.log(
                "ERROR", f"Error resolving light identifier '{identifier}': {str(e)}"
            )
            return None

    # ==================== BASIC LIGHT CONTROL ====================

    def _list_lights(self) -> Dict[str, Any]:
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

    def _get_light_status(self, light_name: str) -> Dict[str, Any]:
        """Get detailed status of a specific light."""
        try:
            light = self.bridge.get_light(light_name)
            return {
                "name": light_name,
                "on": light["state"]["on"],
                "brightness": light["state"].get("bri", 0),
                "hue": light["state"].get("hue"),
                "saturation": light["state"].get("sat"),
                "xy": light["state"].get("xy"),
                "color_temp": light["state"].get("ct"),
                "alert": light["state"].get("alert", "none"),
                "effect": light["state"].get("effect", "none"),
                "reachable": light["state"].get("reachable", True),
                "model": light.get("modelid"),
                "type": light.get("type"),
                "manufacturer": light.get("manufacturername"),
            }
        except Exception as e:
            return {"error": f"Failed to get light status: {str(e)}"}

    def _turn_on_light(self, light_name: str) -> str:
        """Turn on a specific light."""
        try:
            self.bridge.set_light(light_name, "on", True)
            return f"Turned on {light_name}"
        except Exception as e:
            return f"Failed to turn on {light_name}: {str(e)}"

    def _turn_off_light(self, light_name: str) -> str:
        """Turn off a specific light."""
        try:
            self.bridge.set_light(light_name, "on", False)
            return f"Turned off {light_name}"
        except Exception as e:
            return f"Failed to turn off {light_name}: {str(e)}"

    def _toggle_light(self, light_name: str) -> str:
        """Toggle a light on/off."""
        try:
            current_state = self.bridge.get_light(light_name)["state"]["on"]
            new_state = not current_state
            self.bridge.set_light(light_name, "on", new_state)
            return f"Toggled {light_name} {'on' if new_state else 'off'}"
        except Exception as e:
            return f"Failed to toggle {light_name}: {str(e)}"

    # ==================== BRIGHTNESS CONTROL ====================

    def _set_brightness(self, light_name: str, brightness: int) -> str:
        """Set brightness of a light."""
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

    def _adjust_brightness(self, light_name: str, adjustment: int) -> str:
        """Adjust brightness by a relative amount."""
        try:
            current_state = self.bridge.get_light(light_name)["state"]
            current_bri = current_state.get("bri", 127)
            new_bri = max(0, min(254, current_bri + adjustment))
            return self._set_brightness(light_name, new_bri)
        except Exception as e:
            return f"Failed to adjust brightness: {str(e)}"

    def _dim_light(self, light_name: str) -> str:
        """Dim a light to 25% brightness."""
        dim_brightness = int(254 * 0.25)
        return self._set_brightness(light_name, dim_brightness)

    # ==================== COLOR CONTROL ====================

    def _set_color(
        self,
        light_name: str,
        hue: Optional[int] = None,
        sat: Optional[int] = None,
        xy: Optional[List[float]] = None,
    ) -> str:
        """Set color of a light."""
        try:
            if xy is not None and len(xy) == 2:
                self.bridge.set_light(light_name, "xy", xy)
                return f"Set XY color of {light_name} to {xy}"

            if hue is not None:
                self.bridge.set_light(light_name, "hue", hue)
            if sat is not None:
                self.bridge.set_light(light_name, "sat", sat)

            return f"Set color of {light_name} to hue={hue}, sat={sat}"
        except Exception as e:
            return f"Failed to set color: {str(e)}"

    def _set_color_name(self, light_name: str, color_name: str) -> str:
        """Set light color using common color names."""
        try:
            color_name = color_name.lower()
            if color_name not in self.color_map:
                available_colors = ", ".join(self.color_map.keys())
                return f"Unknown color '{color_name}'. Available colors: {available_colors}"

            color_data = self.color_map[color_name]
            self.bridge.set_light(light_name, "on", True)
            self.bridge.set_light(light_name, "hue", color_data["hue"])
            self.bridge.set_light(light_name, "sat", color_data["sat"])
            return f"Set {light_name} to {color_name}"
        except Exception as e:
            return f"Failed to set color: {str(e)}"

    def _set_color_temperature(self, light_name: str, kelvin: int) -> str:
        """Set color temperature in Kelvin."""
        try:
            # Convert Kelvin to mired (micro reciprocal degrees)
            kelvin = max(2000, min(6500, kelvin))
            mired = int(1000000 / kelvin)
            mired = max(153, min(500, mired))  # Hue range

            self.bridge.set_light(light_name, "on", True)
            self.bridge.set_light(light_name, "ct", mired)
            return f"Set color temperature of {light_name} to {kelvin}K"
        except Exception as e:
            return f"Failed to set color temperature: {str(e)}"

    def _set_warm_white(self, light_name: str) -> str:
        """Set light to warm white."""
        return self._set_color_temperature(light_name, 2700)

    def _set_cool_white(self, light_name: str) -> str:
        """Set light to cool white."""
        return self._set_color_temperature(light_name, 6500)

    # ==================== EFFECTS AND ALERTS ====================

    def _flash_light(self, light_name: str) -> str:
        """Make a light flash briefly."""
        try:
            self.bridge.set_light(light_name, "alert", "select")
            return f"Flashed {light_name}"
        except Exception as e:
            return f"Failed to flash light: {str(e)}"

    def _pulse_light(self, light_name: str) -> str:
        """Make a light pulse continuously."""
        try:
            self.bridge.set_light(light_name, "alert", "lselect")
            return f"Started pulsing {light_name}"
        except Exception as e:
            return f"Failed to pulse light: {str(e)}"

    def _stop_alert(self, light_name: str) -> str:
        """Stop any alert/effect on a light."""
        try:
            self.bridge.set_light(light_name, "alert", "none")
            self.bridge.set_light(light_name, "effect", "none")
            return f"Stopped alert on {light_name}"
        except Exception as e:
            return f"Failed to stop alert: {str(e)}"

    def _set_color_loop(self, light_name: str, enable: bool) -> str:
        """Start or stop color loop effect."""
        try:
            effect = "colorloop" if enable else "none"
            self.bridge.set_light(light_name, "effect", effect)
            action = "Started" if enable else "Stopped"
            return f"{action} color loop on {light_name}"
        except Exception as e:
            return f"Failed to set color loop: {str(e)}"

    # ==================== GROUP OPERATIONS ====================

    def _list_groups(self) -> Dict[str, Any]:
        """List all available groups/rooms."""
        try:
            groups_data = self.bridge.get_group()
            groups = {}
            for group_id, group_info in groups_data.items():
                groups[group_info["name"]] = {
                    "id": group_id,
                    "name": group_info["name"],
                    "type": group_info.get("type", "Unknown"),
                    "lights": group_info.get("lights", []),
                    "all_on": group_info["state"].get("all_on", False),
                    "any_on": group_info["state"].get("any_on", False),
                }
            return groups
        except Exception as e:
            return {"error": f"Failed to list groups: {str(e)}"}

    def _get_group_status(self, group_name: str) -> Dict[str, Any]:
        """Get status of all lights in a group."""
        try:
            groups = self.bridge.get_group()
            group_id = None
            for gid, group_info in groups.items():
                if group_info["name"].lower() == group_name.lower():
                    group_id = gid
                    break

            if not group_id:
                return {"error": f"Group '{group_name}' not found"}

            group_data = groups[group_id]
            return {
                "name": group_name,
                "lights": group_data.get("lights", []),
                "all_on": group_data["state"].get("all_on", False),
                "any_on": group_data["state"].get("any_on", False),
                "brightness": group_data["action"].get("bri"),
                "hue": group_data["action"].get("hue"),
                "saturation": group_data["action"].get("sat"),
            }
        except Exception as e:
            return {"error": f"Failed to get group status: {str(e)}"}

    def _turn_on_group(self, group_name: str) -> str:
        """Turn on all lights in a group."""
        try:
            self.bridge.set_group(group_name, "on", True)
            return f"Turned on group '{group_name}'"
        except Exception as e:
            return f"Failed to turn on group: {str(e)}"

    def _turn_off_group(self, group_name: str) -> str:
        """Turn off all lights in a group."""
        try:
            self.bridge.set_group(group_name, "on", False)
            return f"Turned off group '{group_name}'"
        except Exception as e:
            return f"Failed to turn off group: {str(e)}"

    def _set_group_brightness(self, group_name: str, brightness: int) -> str:
        """Set brightness for all lights in a group."""
        try:
            brightness = max(0, min(254, brightness))
            if brightness == 0:
                return self._turn_off_group(group_name)
            else:
                self.bridge.set_group(group_name, "on", True)
                self.bridge.set_group(group_name, "bri", brightness)
                return f"Set brightness of group '{group_name}' to {brightness}"
        except Exception as e:
            return f"Failed to set group brightness: {str(e)}"

    def _set_group_color(self, group_name: str, color_name: str) -> str:
        """Set color for all lights in a group."""
        try:
            color_name = color_name.lower()
            if color_name not in self.color_map:
                available_colors = ", ".join(self.color_map.keys())
                return f"Unknown color '{color_name}'. Available colors: {available_colors}"

            color_data = self.color_map[color_name]
            self.bridge.set_group(group_name, "on", True)
            self.bridge.set_group(group_name, "hue", color_data["hue"])
            self.bridge.set_group(group_name, "sat", color_data["sat"])
            return f"Set group '{group_name}' to {color_name}"
        except Exception as e:
            return f"Failed to set group color: {str(e)}"

    # ==================== ALL LIGHTS OPERATIONS ====================

    def _turn_on_all_lights(self) -> str:
        """Turn on all lights in the system."""
        try:
            lights = self.bridge.get_light()  # Get all lights by ID
            count = 0
            for light_id in lights.keys():
                self.bridge.set_light(int(light_id), "on", True)
                count += 1
            return f"Turned on all {count} lights"
        except Exception as e:
            return f"Failed to turn on all lights: {str(e)}"

    def _turn_off_all_lights(self) -> str:
        """Turn off all lights in the system."""
        try:
            lights = self.bridge.get_light()  # Get all lights by ID
            count = 0
            for light_id in lights.keys():
                self.bridge.set_light(int(light_id), "on", False)
                count += 1
            return f"Turned off all {count} lights"
        except Exception as e:
            return f"Failed to turn off all lights: {str(e)}"

    def _set_all_brightness(self, brightness: int) -> str:
        """Set brightness for all lights."""
        try:
            brightness = max(0, min(254, brightness))
            lights = self.bridge.get_light()  # Get all lights by ID
            count = 0
            for light_id in lights.keys():
                light_id_int = int(light_id)
                if brightness == 0:
                    self.bridge.set_light(light_id_int, "on", False)
                else:
                    self.bridge.set_light(light_id_int, "on", True)
                    self.bridge.set_light(light_id_int, "bri", brightness)
                count += 1
            return f"Set brightness of all {count} lights to {brightness}"
        except Exception as e:
            return f"Failed to set all brightness: {str(e)}"

    # ==================== SCENE MANAGEMENT ====================

    def _list_scenes(self) -> Dict[str, Any]:
        """List all available scenes."""
        try:
            scenes_data = self.bridge.get_scene()
            scenes = {}
            for scene_id, scene_info in scenes_data.items():
                scenes[scene_info["name"]] = {
                    "id": scene_id,
                    "name": scene_info["name"],
                    "lights": scene_info.get("lights", []),
                    "group": scene_info.get("group"),
                    "recycle": scene_info.get("recycle", False),
                }
            return scenes
        except Exception as e:
            return {"error": f"Failed to list scenes: {str(e)}"}

    def _activate_scene(self, scene_name: str) -> str:
        """Activate a specific scene."""
        try:
            scenes = self.bridge.get_scene()
            scene_id = None
            for sid, scene_info in scenes.items():
                if scene_info["name"].lower() == scene_name.lower():
                    scene_id = sid
                    break

            if not scene_id:
                return f"Scene '{scene_name}' not found"

            # If scene has a group, activate via group
            scene_data = scenes[scene_id]
            if "group" in scene_data:
                self.bridge.set_group(scene_data["group"], "scene", scene_id)
            else:
                # Activate individual lights
                for light_id in scene_data.get("lights", []):
                    self.bridge.activate_scene(
                        scene_data["group"] if "group" in scene_data else "0", scene_id
                    )

            return f"Activated scene '{scene_name}'"
        except Exception as e:
            return f"Failed to activate scene: {str(e)}"

    def _create_scene(self, scene_name: str, lights: List[str]) -> str:
        """Create a new scene from current light states."""
        try:
            # This is a simplified implementation - full scene creation requires more API calls
            return f"Scene creation not fully implemented in phue library. Would create scene '{scene_name}' with lights: {', '.join(lights)}"
        except Exception as e:
            return f"Failed to create scene: {str(e)}"

    # ==================== LIGHT INFORMATION ====================

    def _get_light_info(self, light_name: str) -> Dict[str, Any]:
        """Get detailed information about a light."""
        try:
            light = self.bridge.get_light(light_name)
            return {
                "name": light_name,
                "model": light.get("modelid"),
                "type": light.get("type"),
                "manufacturer": light.get("manufacturername"),
                "software_version": light.get("swversion"),
                "unique_id": light.get("uniqueid"),
                "capabilities": light.get("capabilities", {}),
                "config": light.get("config", {}),
            }
        except Exception as e:
            return {"error": f"Failed to get light info: {str(e)}"}

    def _check_unreachable_lights(self) -> Dict[str, Any]:
        """Find all lights that are currently unreachable."""
        try:
            lights = self.bridge.get_light()
            unreachable = {}
            for light_id, light_data in lights.items():
                if not light_data["state"].get("reachable", True):
                    unreachable[light_data["name"]] = {
                        "id": light_id,
                        "name": light_data["name"],
                        "model": light_data.get("modelid"),
                    }
            return {
                "unreachable_count": len(unreachable),
                "unreachable_lights": unreachable,
            }
        except Exception as e:
            return {"error": f"Failed to check unreachable lights: {str(e)}"}

    def _get_bridge_info(self) -> Dict[str, Any]:
        """Get information about the Hue Bridge."""
        try:
            config = self.bridge.get_api()["config"]
            return {
                "name": config.get("name"),
                "mac": config.get("mac"),
                "ip": config.get("ipaddress"),
                "software_version": config.get("swversion"),
                "api_version": config.get("apiversion"),
                "model": config.get("modelid"),
                "bridge_id": config.get("bridgeid"),
                "timezone": config.get("timezone"),
                "local_time": config.get("localtime"),
            }
        except Exception as e:
            return {"error": f"Failed to get bridge info: {str(e)}"}

    # ==================== LIGHT MANAGEMENT ====================

    def _rename_light(self, current_name: str, new_name: str) -> str:
        """Rename a light."""
        try:
            lights = self.bridge.get_light()
            light_id = None
            for lid, light_data in lights.items():
                if light_data["name"] == current_name:
                    light_id = lid
                    break

            if not light_id:
                return f"Light '{current_name}' not found"

            self.bridge.set_light(light_id, "name", new_name)
            return f"Renamed light from '{current_name}' to '{new_name}'"
        except Exception as e:
            return f"Failed to rename light: {str(e)}"

    def _search_new_lights(self) -> str:
        """Search for new lights to add to the system."""
        try:
            result = self.bridge.api["lights"].new()
            return f"Started search for new lights. Check results in 1-2 minutes."
        except Exception as e:
            return f"Failed to search for new lights: {str(e)}"

    # ==================== TRANSITION EFFECTS ====================

    def _fade_light(
        self, light_name: str, target_brightness: int, duration_seconds: int
    ) -> str:
        """Gradually change light brightness over time."""
        try:
            target_brightness = max(0, min(254, target_brightness))
            transition_time = duration_seconds * 10  # Hue API uses deciseconds

            if target_brightness == 0:
                self.bridge.set_light(
                    light_name, {"on": False, "transitiontime": transition_time}
                )
                return f"Fading {light_name} off over {duration_seconds} seconds"
            else:
                self.bridge.set_light(
                    light_name,
                    {
                        "on": True,
                        "bri": target_brightness,
                        "transitiontime": transition_time,
                    },
                )
                return f"Fading {light_name} to brightness {target_brightness} over {duration_seconds} seconds"
        except Exception as e:
            return f"Failed to fade light: {str(e)}"

    def _sunrise_effect(self, light_name: str, duration_minutes: int) -> str:
        """Create a sunrise effect on a light."""
        try:
            # Start dim and warm, gradually brighten and cool
            duration_deciseconds = duration_minutes * 600  # Convert to deciseconds

            # Phase 1: Start very dim and warm
            self.bridge.set_light(
                light_name,
                {"on": True, "bri": 1, "ct": 500, "transitiontime": 10},  # Very warm
            )

            # Phase 2: Gradually brighten and cool (this is simplified - real implementation would need multiple phases)
            time.sleep(1)  # Brief pause
            self.bridge.set_light(
                light_name,
                {
                    "bri": 254,
                    "ct": 250,  # Cooler white
                    "transitiontime": duration_deciseconds,
                },
            )

            return f"Started {duration_minutes}-minute sunrise effect on {light_name}"
        except Exception as e:
            return f"Failed to create sunrise effect: {str(e)}"

    def _sunset_effect(self, light_name: str, duration_minutes: int) -> str:
        """Create a sunset effect on a light."""
        try:
            duration_deciseconds = duration_minutes * 600

            # Gradually dim and warm
            self.bridge.set_light(
                light_name,
                {
                    "bri": 1,
                    "ct": 500,  # Very warm
                    "transitiontime": duration_deciseconds,
                },
            )

            return f"Started {duration_minutes}-minute sunset effect on {light_name}"
        except Exception as e:
            return f"Failed to create sunset effect: {str(e)}"

    # ==================== SCHEDULES AND TIMERS ====================

    def _list_schedules(self) -> Dict[str, Any]:
        """List all scheduled events."""
        try:
            schedules = self.bridge.get_schedule()
            schedule_info = {}
            for schedule_id, schedule_data in schedules.items():
                schedule_info[schedule_data["name"]] = {
                    "id": schedule_id,
                    "name": schedule_data["name"],
                    "time": schedule_data.get("time"),
                    "status": schedule_data.get("status"),
                    "description": schedule_data.get("description"),
                }
            return schedule_info
        except Exception as e:
            return {"error": f"Failed to list schedules: {str(e)}"}

    def _create_timer(self, light_name: str, action: str, delay_minutes: int) -> str:
        """Create a timer to turn lights on/off after a delay."""
        try:
            # This is a simplified implementation - full timer creation requires schedule API
            return f"Timer creation not fully implemented. Would {action} {light_name} in {delay_minutes} minutes"
        except Exception as e:
            return f"Failed to create timer: {str(e)}"

    # ==================== ENTERTAINMENT MODES ====================

    def _party_mode(self, lights: List[str]) -> str:
        """Start party mode with random colors and effects."""
        try:
            import random

            colors = list(self.color_map.keys())
            results = []

            for light_identifier in lights:
                # Handle both light names and light IDs
                light_id = self._resolve_light_identifier(light_identifier)
                if light_id is None:
                    continue

                color = random.choice(colors)
                color_data = self.color_map[color]
                self.bridge.set_light(light_id, "on", True)
                self.bridge.set_light(light_id, "bri", 254)
                self.bridge.set_light(light_id, "hue", color_data["hue"])
                self.bridge.set_light(light_id, "sat", color_data["sat"])
                self.bridge.set_light(light_id, "effect", "colorloop")
                results.append(f"{light_identifier}: {color}")

            return f"Party mode activated! {', '.join(results)}"
        except Exception as e:
            return f"Failed to activate party mode: {str(e)}"

    def _movie_mode(self, lights: List[str]) -> str:
        """Set lights for movie watching."""
        try:
            results = []
            for light_identifier in lights:
                # Handle both light names and light IDs
                light_id = self._resolve_light_identifier(light_identifier)
                if light_id is None:
                    continue

                self.bridge.set_light(light_id, "on", True)
                self.bridge.set_light(light_id, "bri", 50)  # Very dim
                self.bridge.set_light(light_id, "ct", 450)  # Warm white
                results.append(str(light_identifier))

            return f"Movie mode activated for: {', '.join(results)}"
        except Exception as e:
            return f"Failed to activate movie mode: {str(e)}"

    def _focus_mode(self, lights: List[str]) -> str:
        """Set bright cool white lighting for concentration."""
        try:
            results = []
            for light_identifier in lights:
                # Handle both light names and light IDs
                light_id = self._resolve_light_identifier(light_identifier)
                if light_id is None:
                    continue

                self.bridge.set_light(light_id, "on", True)
                self.bridge.set_light(light_id, "bri", 254)  # Maximum brightness
                self.bridge.set_light(light_id, "ct", 200)  # Cool white
                results.append(str(light_identifier))

            return f"Focus mode activated for: {', '.join(results)}"
        except Exception as e:
            return f"Failed to activate focus mode: {str(e)}"

    def _relax_mode(self, lights: List[str]) -> str:
        """Set warm dim lighting for relaxation."""
        try:
            results = []
            for light_identifier in lights:
                # Handle both light names and light IDs
                light_id = self._resolve_light_identifier(light_identifier)
                if light_id is None:
                    continue

                self.bridge.set_light(light_id, "on", True)
                self.bridge.set_light(light_id, "bri", 100)  # Dim
                self.bridge.set_light(light_id, "ct", 450)  # Warm white
                results.append(str(light_identifier))

            return f"Relax mode activated for: {', '.join(results)}"
        except Exception as e:
            return f"Failed to activate relax mode: {str(e)}"

    # ==================== MAIN PROCESSING METHOD ====================

    async def _process_hue_command(self, command: str) -> dict[str, any]:
        """Turn a natural-language command into tool calls via the AI client."""
        self.logger.log("INFO", "=== STARTING HUE COMMAND PROCESSING ===", command)
        self.logger.log("DEBUG", "System prompt", self.system_prompt)

        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": command},
        ]
        self.logger.log("DEBUG", "Initial messages structure", json.dumps(messages))

        actions_taken: list[dict[str, any]] = []

        iterations = 0
        while True:
            self.logger.log(
                "INFO", f"=== ITERATION {iterations + 1} ===", "Sending request to AI"
            )

            message, tool_calls = await self.ai_client.chat(messages, self.tools)

            self.logger.log(
                "INFO",
                f"AI response (iteration {iterations + 1})",
                message.content if hasattr(message, "content") else str(message),
            )
            self.logger.log(
                "INFO",
                f"Tool calls received",
                f"Count: {len(tool_calls) if tool_calls else 0}",
            )

            if not tool_calls:
                self.logger.log(
                    "INFO",
                    "No more tool calls requested by AI",
                    "Exiting processing loop",
                )
                break

            messages.append(message.model_dump())
            self.logger.log(
                "DEBUG", "Updated message history", f"Message count: {len(messages)}"
            )

            for idx, call in enumerate(tool_calls):
                fn = call.function.name
                args = json.loads(call.function.arguments)
                self.logger.log(
                    "INFO",
                    f"Executing tool call {idx + 1}/{len(tool_calls)}",
                    f"Function: {fn}",
                )
                self.logger.log("DEBUG", f"Tool arguments for {fn}", json.dumps(args))

                execution_start = time.time()
                result = await self._execute_function(fn, args)
                execution_time = time.time() - execution_start

                self.logger.log(
                    "INFO",
                    f"Tool execution completed",
                    f"Function: {fn}, Time: {execution_time:.2f}s",
                )
                self.logger.log("DEBUG", f"Tool result for {fn}", json.dumps(result))

                actions_taken.append(
                    {"function": fn, "arguments": args, "result": result}
                )

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": json.dumps(result),
                    }
                )
                self.logger.log(
                    "DEBUG",
                    "Added tool response to message history",
                    f"Tool: {fn}, Call ID: {call.id}",
                )

            iterations += 1
            self.logger.log(
                "INFO",
                f"Completed iteration {iterations}",
                f"Total actions so far: {len(actions_taken)}",
            )

            if iterations >= 10:
                self.logger.log(
                    "ERROR",
                    "Max iterations reached for hue command",
                    f"Stopped after {iterations} iterations",
                )
                self.logger.log(
                    "WARNING",
                    "Possible infinite loop detected",
                    "Check AI responses for cyclic behavior",
                )
                break

        final_text = message.content if hasattr(message, "content") else str(message)
        self.logger.log(
            "INFO",
            "=== COMMAND PROCESSING COMPLETE ===",
            f"Total iterations: {iterations}",
        )
        self.logger.log("DEBUG", "Final AI response", final_text)
        self.logger.log(
            "INFO", "Actions summary", f"Total actions taken: {len(actions_taken)}"
        )

        return {"response": final_text, "actions": actions_taken}

    async def _handle_capability_request(self, message: Message) -> None:
        """Handle incoming capability requests."""
        capability = message.content.get("capability")
        data = message.content.get("data", {})

        if capability not in self.capabilities:
            return

        self.logger.log("INFO", f"Handling capability: {capability}", str(data))

        cmd = data.get("command")
        if not isinstance(cmd, str):
            await self.send_error(
                message.from_agent, "Invalid or missing command", message.request_id
            )
            return
        result = await self._process_hue_command(cmd)

        await self.send_capability_response(
            message.from_agent, result, message.request_id, message.id
        )

    async def _handle_group_control(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle group control operations."""
        action = data.get("action", "on")
        if action == "on":
            return await self._execute_function("turn_on_group", data)
        elif action == "off":
            return await self._execute_function("turn_off_group", data)
        elif action == "brightness":
            return await self._execute_function("set_group_brightness", data)
        elif action == "color":
            return await self._execute_function("set_group_color", data)
        else:
            return {"error": f"Unknown group action: {action}"}
