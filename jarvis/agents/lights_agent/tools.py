"""Tool definitions for PhillipsHueAgent."""
from typing import Any, Dict, List

tools: List[Dict[str, Any]] = [
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
