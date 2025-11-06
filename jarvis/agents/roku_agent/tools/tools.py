# jarvis/agents/roku_agent/tools/tools.py
"""
Tool definitions for Roku agent - defines all functions available to the AI
"""

tools = [
    # ==================== DEVICE INFORMATION ====================
    {
        "type": "function",
        "function": {
            "name": "get_device_info",
            "description": "Get comprehensive information about the Roku device including model, software version, and network details",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_active_app",
            "description": "Get the currently active app or channel on the Roku device",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_apps",
            "description": "List all installed apps and channels on the Roku device",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_player_info",
            "description": "Get current media player state including playback position, duration, and status",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    # ==================== APP/CHANNEL CONTROL ====================
    {
        "type": "function",
        "function": {
            "name": "launch_app_by_name",
            "description": "Launch an app or channel by its name (e.g., Netflix, Hulu, YouTube, Disney+)",
            "parameters": {
                "type": "object",
                "properties": {
                    "app_name": {
                        "type": "string",
                        "description": "The name of the app to launch (e.g., 'Netflix', 'YouTube', 'Hulu')",
                    }
                },
                "required": ["app_name"],
            },
        },
    },
    # ==================== PLAYBACK CONTROL ====================
    {
        "type": "function",
        "function": {
            "name": "play",
            "description": "Resume or play the current media",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "pause",
            "description": "Pause the current media playback",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "rewind",
            "description": "Rewind the current media",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fast_forward",
            "description": "Fast forward the current media",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "instant_replay",
            "description": "Jump back a few seconds in the current media",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    # ==================== NAVIGATION ====================
    {
        "type": "function",
        "function": {
            "name": "home",
            "description": "Go to the Roku home screen",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "back",
            "description": "Go back to the previous screen",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "select",
            "description": "Press the select/OK button",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "navigate",
            "description": "Navigate in a specific direction using the directional pad",
            "parameters": {
                "type": "object",
                "properties": {
                    "direction": {
                        "type": "string",
                        "enum": ["up", "down", "left", "right"],
                        "description": "Direction to navigate",
                    },
                    "count": {
                        "type": "integer",
                        "description": "Number of times to press the direction (default: 1)",
                        "default": 1,
                    },
                },
                "required": ["direction"],
            },
        },
    },
    # ==================== VOLUME AND POWER ====================
    {
        "type": "function",
        "function": {
            "name": "volume_up",
            "description": "Increase the volume",
            "parameters": {
                "type": "object",
                "properties": {
                    "count": {
                        "type": "integer",
                        "description": "Number of times to increase volume (default: 1)",
                        "default": 1,
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "volume_down",
            "description": "Decrease the volume",
            "parameters": {
                "type": "object",
                "properties": {
                    "count": {
                        "type": "integer",
                        "description": "Number of times to decrease volume (default: 1)",
                        "default": 1,
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "volume_mute",
            "description": "Mute or unmute the volume",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "power_off",
            "description": "Turn off the Roku device",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "power_on",
            "description": "Turn on the Roku device",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    # ==================== INPUT SWITCHING ====================
    {
        "type": "function",
        "function": {
            "name": "switch_input",
            "description": "Switch to a different HDMI input or tuner",
            "parameters": {
                "type": "object",
                "properties": {
                    "input_name": {
                        "type": "string",
                        "enum": ["Tuner", "HDMI1", "HDMI2", "HDMI3", "HDMI4", "AV1"],
                        "description": "The input to switch to",
                    }
                },
                "required": ["input_name"],
            },
        },
    },
    # ==================== SEARCH ====================
    {
        "type": "function",
        "function": {
            "name": "search",
            "description": "Search for content on the Roku device",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The search query"}
                },
                "required": ["query"],
            },
        },
    },
]
